"""Shared lifecycle for native monitors owned by a worker thread."""

import asyncio
import logging
import queue
import threading
from abc import abstractmethod

from .._base import AudioDeviceMonitor, Callback
from .._debounce import Debouncer


class _WorkerState:
    def __init__(self, debouncer: Debouncer):
        self.debouncer = debouncer
        self.stopped = threading.Event()
        self.ready = threading.Event()
        self.events = queue.SimpleQueue()
        self.error: Exception | None = None

    def stop(self) -> None:
        self.stopped.set()
        self.events.put(None)


class ThreadedAudioDeviceMonitor(AudioDeviceMonitor):
    """Serialize start/stop and keep each worker's resources isolated."""

    _startup_timeout = 5.0
    _shutdown_timeout = 2.0

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop | None = None,
        debounce_ms: int = 200,
        logger: logging.Logger | None = None,
    ):
        super().__init__(loop=loop, debounce_ms=debounce_ms, logger=logger)
        self._lifecycle_lock = threading.Lock()
        self._monitor_thread = None
        self._worker_state = None

    def start(self, on_change: Callback) -> None:
        """Wait for native setup, propagating failures to the caller."""
        with self._lifecycle_lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                raise RuntimeError(
                    "Audio monitor worker still active; call stop() first"
                )
            self._initialize_debouncer(on_change)
            state = _WorkerState(self._debouncer)
            self._worker_state = state

            def worker():
                try:
                    self._run(state)
                except Exception as error:
                    # Tracebacks can retain native objects past COM teardown.
                    state.error = error.with_traceback(None)
                    self._logger.error("Audio monitor worker failed: %s", str(error))
                finally:
                    self._cancel_debouncer()
                    state.ready.set()

            thread = threading.Thread(
                target=worker, daemon=True, name="AudioDeviceMonitor"
            )
            self._monitor_thread = thread
            try:
                thread.start()
                if not state.ready.wait(self._startup_timeout):
                    raise TimeoutError("Audio monitor initialization timed out")
                if state.error is not None:
                    raise state.error
            except Exception:
                state.stop()
                self._cancel_debouncer()
                if thread.ident is not None:
                    thread.join(self._shutdown_timeout)
                raise

    def stop(self) -> None:
        """Disable callbacks and wait for native cleanup; safe to retry."""
        with self._lifecycle_lock:
            self._cancel_debouncer()
            if self._worker_state is not None:
                self._worker_state.stop()
            thread = self._monitor_thread
            if thread is not None and thread.ident is not None:
                thread.join(self._shutdown_timeout)
                if thread.is_alive():
                    self._logger.warning(
                        "Audio monitor worker has not stopped; call stop() to retry"
                    )
                    return
            self._monitor_thread = None
            self._worker_state = None
            self._debouncer = None

    @abstractmethod
    def _run(self, state: _WorkerState) -> None:
        """Initialize, set ready, process events, then release native resources."""
