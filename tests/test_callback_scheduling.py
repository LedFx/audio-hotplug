"""Test callback scheduling (sync and async)."""

import asyncio
import inspect
import threading
import time
from collections.abc import Awaitable

import pytest

from audio_hotplug._base import AudioDeviceMonitor


@pytest.mark.asyncio
@pytest.mark.parametrize("callable_instance", [False, True])
async def test_awaitable_returning_callback(callable_instance: bool) -> None:
    """The Callback contract includes functions and objects returning awaitables."""
    monitor = MockMonitor()
    received = asyncio.Event()
    loop_thread = threading.get_ident()
    callback_threads = []

    async def delivered() -> None:
        callback_threads.append(threading.get_ident())
        received.set()

    def callback() -> Awaitable[None]:
        return delivered()

    class AsyncCallable:
        async def __call__(self) -> None:
            await delivered()

    on_change = AsyncCallable() if callable_instance else callback
    assert not inspect.iscoroutinefunction(on_change)
    debouncer = monitor._initialize_debouncer(on_change)
    try:
        worker = threading.Thread(target=debouncer._invoke_callback)
        worker.start()
        worker.join()
        await asyncio.wait_for(received.wait(), timeout=2)
        assert callback_threads == [loop_thread]
    finally:
        monitor._cancel_debouncer()


@pytest.mark.parametrize("closed_loop", [False, True])
def test_unschedulable_returned_coroutine_is_closed(
    closed_loop: bool, caplog: pytest.LogCaptureFixture
) -> None:
    loop = asyncio.new_event_loop() if closed_loop else None
    if loop is not None:
        loop.close()
    monitor = MockMonitor(loop=loop)

    async def callback() -> None:
        raise AssertionError("Must never run without a usable loop")

    coroutine = callback()
    monitor._safe_sync_callback(lambda: coroutine)
    assert coroutine.cr_frame is None
    assert "loop" in caplog.text


class MockMonitor(AudioDeviceMonitor):
    """Mock monitor for testing base class functionality."""

    def start(self, on_change):
        self._callback = on_change

    def stop(self):
        pass

    def trigger_from_thread(self):
        """Simulate triggering callback from background thread."""
        if self._callback:
            self._notify(self._callback)


class TestCallbackScheduling:
    """Test cases for callback scheduling in AudioDeviceMonitor."""

    def test_sync_callback_with_loop(self):
        """Test sync callback invoked on event loop."""
        loop = asyncio.new_event_loop()
        callback_invoked = {"value": False}

        def callback():
            callback_invoked["value"] = True

        monitor = MockMonitor(loop=loop)
        monitor.start(callback)

        # Trigger from different thread
        thread = threading.Thread(target=monitor.trigger_from_thread)
        thread.start()
        thread.join()

        # Run loop briefly to process callback
        loop.run_until_complete(asyncio.sleep(0.01))

        assert callback_invoked["value"]
        loop.close()

    def test_async_callback_with_loop(self):
        """Test async callback scheduled on event loop."""
        loop = asyncio.new_event_loop()
        callback_invoked = {"value": False}

        async def async_callback():
            await asyncio.sleep(0.01)
            callback_invoked["value"] = True

        monitor = MockMonitor(loop=loop)
        monitor.start(async_callback)

        # Trigger from different thread
        thread = threading.Thread(target=monitor.trigger_from_thread)
        thread.start()
        thread.join()

        # Run loop to completion
        loop.run_until_complete(asyncio.sleep(0.05))

        assert callback_invoked["value"]
        loop.close()

    def test_sync_callback_no_loop_direct_call(self):
        """Test sync callback without loop calls directly."""
        callback_invoked = {"value": False}

        def callback():
            callback_invoked["value"] = True

        monitor = MockMonitor(loop=None)
        monitor.start(callback)
        monitor.trigger_from_thread()

        # Give it a moment
        time.sleep(0.01)

        assert callback_invoked["value"]

    def test_async_callback_no_loop_error(self):
        """Test async callback without loop logs error."""

        async def async_callback():
            pass

        monitor = MockMonitor(loop=None)
        monitor.start(async_callback)

        # Should not raise, but should log error
        monitor.trigger_from_thread()
        time.sleep(0.01)
        # No assertion - just verify no crash

    def test_sync_callback_exception_caught(self):
        """Test exceptions in sync callback are caught and logged."""
        callback_invoked = {"value": False}

        def failing_callback():
            callback_invoked["value"] = True
            raise ValueError("Test exception")

        loop = asyncio.new_event_loop()
        monitor = MockMonitor(loop=loop)
        monitor.start(failing_callback)

        # Should not propagate exception
        thread = threading.Thread(target=monitor.trigger_from_thread)
        thread.start()
        thread.join()

        loop.run_until_complete(asyncio.sleep(0.01))

        assert callback_invoked["value"]
        loop.close()

    def test_async_callback_exception_caught(self):
        """Test exceptions in async callback are caught and logged."""
        callback_invoked = {"value": False}

        async def failing_async_callback():
            callback_invoked["value"] = True
            raise ValueError("Test exception")

        loop = asyncio.new_event_loop()
        monitor = MockMonitor(loop=loop)
        monitor.start(failing_async_callback)

        thread = threading.Thread(target=monitor.trigger_from_thread)
        thread.start()
        thread.join()

        loop.run_until_complete(asyncio.sleep(0.05))

        assert callback_invoked["value"]
        loop.close()

    def test_running_loop_detection(self):
        """Test that running loop is detected when none provided."""
        callback_invoked = {"value": False}

        async def test_with_running_loop():
            def callback():
                callback_invoked["value"] = True

            # Don't pass loop, should detect running loop
            monitor = MockMonitor(loop=None)
            monitor.start(callback)

            # Trigger from different thread
            thread = threading.Thread(target=monitor.trigger_from_thread)
            thread.start()
            thread.join()

            await asyncio.sleep(0.01)

        asyncio.run(test_with_running_loop())
        assert callback_invoked["value"]

    def test_multiple_rapid_callbacks(self):
        """Test multiple rapid callback invocations."""
        loop = asyncio.new_event_loop()
        callback_count = {"count": 0}

        def callback():
            callback_count["count"] += 1

        monitor = MockMonitor(loop=loop)
        monitor.start(callback)

        # Trigger multiple times
        for _ in range(10):
            thread = threading.Thread(target=monitor.trigger_from_thread)
            thread.start()
            thread.join(timeout=0.01)

        loop.run_until_complete(asyncio.sleep(0.05))

        # All callbacks should be invoked
        assert callback_count["count"] == 10
        loop.close()


@pytest.mark.asyncio
async def test_async_context():
    """Test callback within async context using pytest-asyncio."""
    callback_invoked = {"value": False}

    async def async_callback():
        await asyncio.sleep(0.01)
        callback_invoked["value"] = True

    loop = asyncio.get_event_loop()
    monitor = MockMonitor(loop=loop)
    monitor.start(async_callback)

    thread = threading.Thread(target=monitor.trigger_from_thread)
    thread.start()
    thread.join()

    await asyncio.sleep(0.05)

    assert callback_invoked["value"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


@pytest.mark.asyncio
async def test_initialize_captures_loop_for_native_thread():
    """Implicit loop detection must happen before a worker sends events."""
    monitor = MockMonitor()
    received = asyncio.Event()

    async def callback():
        received.set()

    monitor._initialize_debouncer(callback)
    try:
        assert monitor._loop is asyncio.get_running_loop()
        thread = threading.Thread(target=monitor._debouncer._invoke_callback)
        thread.start()
        thread.join()
        await asyncio.wait_for(received.wait(), timeout=1)
    finally:
        monitor._cancel_debouncer()


@pytest.mark.parametrize("is_async", [False, True])
def test_closed_loop_does_not_leak_coroutine(is_async, caplog):
    from unittest.mock import Mock, patch

    loop = asyncio.new_event_loop()
    loop.close()
    monitor = MockMonitor(loop=loop)

    async def async_callback():
        pass

    if is_async:
        coroutine = monitor._safe_async_callback(async_callback)
        with patch.object(
            monitor, "_safe_async_callback", new=Mock(return_value=coroutine)
        ):
            monitor._notify(async_callback)
        assert coroutine.cr_frame is None
    else:
        monitor._notify(Mock())
    assert "closed loop" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("async_callback", [False, True])
async def test_implicit_loop_from_debounce_thread(async_callback):
    """Debounced callbacks return to the loop that started the monitor."""
    monitor = MockMonitor(debounce_ms=1)
    called = asyncio.Event()
    loop_thread = threading.get_ident()
    callback_threads = []

    def callback():
        callback_threads.append(threading.get_ident())
        called.set()

    async def coroutine_callback():
        callback()

    monitor._initialize_debouncer(coroutine_callback if async_callback else callback)
    try:
        monitor._debouncer.trigger()
        await asyncio.wait_for(called.wait(), timeout=2)
        assert callback_threads == [loop_thread]
    finally:
        monitor._debouncer.cancel()
