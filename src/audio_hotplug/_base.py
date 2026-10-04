"""Abstract base class for audio device monitors."""

import asyncio
import inspect
import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from ._debounce import Debouncer

Callback = Callable[[], None | Awaitable[None]]


class AudioDeviceMonitor(ABC):
    """Abstract base class for platform-specific audio device monitors.

    Monitors system audio device changes (add/remove/state changes) and
    invokes a user callback when changes are detected.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop | None = None,
        debounce_ms: int = 200,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize the monitor.

        Args:
            loop: Event loop for callback scheduling. If None,
                attempts to get running loop.
            debounce_ms: Milliseconds to wait before invoking
                callback after last change.
            logger: Logger instance. If None, creates a logger for this class.
        """
        self._loop = loop
        self._debounce_ms = debounce_ms
        self._logger = logger or logging.getLogger(self.__class__.__name__)
        self._callback: Callback | None = None
        self._debouncer: Debouncer | None = None
        self._running = False
        self._callback_stop_event = threading.Event()

    @abstractmethod
    def start(self, on_change: Callback) -> None:
        """Start monitoring for device changes.

        Args:
            on_change: Callback to invoke when device changes detected.
                      Can be a sync function, async function, or callable
                      returning an awaitable.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop monitoring. Safe to call multiple times."""
        pass

    def _initialize_debouncer(self, on_change: Callback) -> Debouncer:
        """Initialize the debouncer with the user callback.

        Call this at the start of your platform's start() implementation.

        Args:
            on_change: The user's callback to debounce.
        """
        # Capture the loop on the caller's thread, before native notifications
        # arrive on a worker without a running asyncio loop.
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        stopped = threading.Event()
        self._callback_stop_event = stopped
        if inspect.iscoroutinefunction(on_change):

            async def guarded_callback() -> None:
                if not stopped.is_set():
                    await on_change()

        else:

            def guarded_callback() -> None | Awaitable[None]:
                if not stopped.is_set():
                    return on_change()
                return None

        self._callback = guarded_callback
        self._running = True
        # Debouncer will call _notify when triggered
        self._debouncer = Debouncer(
            lambda: self._notify(guarded_callback), delay_ms=self._debounce_ms
        )
        return self._debouncer

    def _cancel_debouncer(self) -> None:
        """Disable this run, including notifications already queued on a loop."""
        self._running = False
        self._callback_stop_event.set()
        if self._debouncer is not None:
            self._debouncer.close()
        self._callback = None

    def _notify(self, callback: Callback) -> None:
        """Schedule callback on the event loop thread safely.

        Args:
            callback: The callback to invoke.
        """
        if not callback:
            return

        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, call sync callback directly
                if inspect.iscoroutinefunction(callback):
                    self._logger.error(
                        "Async callback provided but no event loop available"
                    )
                    return
                try:
                    self._safe_sync_callback(callback)
                except Exception as e:
                    self._logger.error(f"Error in callback: {e}", exc_info=True)
                return

        # Schedule on loop thread
        if inspect.iscoroutinefunction(callback):
            coroutine = self._safe_async_callback(callback)
            try:
                asyncio.run_coroutine_threadsafe(coroutine, loop)
            except RuntimeError:
                coroutine.close()
                self._logger.warning("Cannot schedule audio callback on a closed loop")
        else:
            try:
                loop.call_soon_threadsafe(self._safe_sync_callback, callback)
            except RuntimeError:
                self._logger.warning("Cannot schedule audio callback on a closed loop")

    def _safe_sync_callback(self, callback: Callback) -> None:
        """Invoke a callback and schedule any returned awaitable safely."""
        try:
            result = callback()
            # Callable instances and ordinary functions can return awaitables
            # without being recognized by iscoroutinefunction().
            if result is not None:
                loop = self._loop
                if loop is None:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        if inspect.iscoroutine(result):
                            result.close()
                        self._logger.error(
                            "Async callback provided but no event loop available"
                        )
                        return
                coroutine = self._safe_async_callback(lambda: result)
                try:
                    asyncio.run_coroutine_threadsafe(coroutine, loop)
                except RuntimeError:
                    coroutine.close()
                    if inspect.iscoroutine(result):
                        result.close()
                    self._logger.warning(
                        "Cannot schedule audio callback on a closed loop"
                    )
        except Exception as e:
            self._logger.error(f"Error in sync callback: {e}", exc_info=True)

    async def _safe_async_callback(
        self, callback: Callable[[], Awaitable[None]]
    ) -> None:
        """Wrap async callback with error handling."""
        try:
            await callback()
        except Exception as e:
            self._logger.error(f"Error in async callback: {e}", exc_info=True)
