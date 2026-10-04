"""Thread-safe debouncer for coalescing rapid events."""

import threading
import time
from collections.abc import Callable


class Debouncer:
    """Invoke a callback after a quiet period, with one pending timer per burst."""

    def __init__(self, callback: Callable[[], None], delay_ms: int = 200) -> None:
        self._callback = callback
        self._delay_s = delay_ms / 1000.0
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._deadline = 0.0
        self._generation = 0
        self._closed = False

    def trigger(self) -> None:
        """Extend the quiet period without spawning a thread for every event."""
        with self._lock:
            if self._closed:
                return
            self._deadline = time.monotonic() + self._delay_s
            if self._timer is None:
                self._schedule(max(0.0, self._delay_s))

    def _schedule(self, delay: float) -> None:
        timer = threading.Timer(delay, self._expire, args=(self._generation,))
        timer.daemon = True
        self._timer = timer
        try:
            timer.start()
        except Exception:
            self._timer = None
            raise

    def _expire(self, generation: int) -> None:
        with self._lock:
            if self._closed or generation != self._generation:
                return
            self._timer = None
            remaining = self._deadline - time.monotonic()
            if remaining > 0:
                self._schedule(remaining)
                return
        self._invoke_callback()

    def _invoke_callback(self) -> None:
        """Invoke outside the lock so a callback can stop its own monitor."""
        try:
            self._callback()
        except Exception:
            # Monitor callbacks handle their own error logging.
            pass

    def cancel(self) -> None:
        """Cancel pending work; subsequent triggers are allowed."""
        with self._lock:
            self._cancel()

    def _cancel(self) -> None:
        self._generation += 1
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def close(self) -> None:
        """Permanently disable this debouncer, including late native events."""
        with self._lock:
            self._closed = True
            self._cancel()
