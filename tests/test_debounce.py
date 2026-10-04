"""Test the debouncer implementation."""

import threading
import time

import pytest

from audio_hotplug._debounce import Debouncer


class TestDebouncer:
    """Test cases for the Debouncer class."""

    def test_single_trigger(self):
        """Test that single trigger invokes callback once."""
        callback_count = {"count": 0}

        def callback():
            callback_count["count"] += 1

        debouncer = Debouncer(callback, delay_ms=50)
        debouncer.trigger()

        # Wait for debounce period + buffer (4x for CI)
        time.sleep(0.2)

        assert callback_count["count"] == 1

    def test_multiple_rapid_triggers_coalesced(self):
        """Test that rapid triggers result in single callback."""
        callback_count = {"count": 0}

        def callback():
            callback_count["count"] += 1

        debouncer = Debouncer(callback, delay_ms=100)

        # Trigger 10 times rapidly
        for _ in range(10):
            debouncer.trigger()
            time.sleep(0.01)  # 10ms between triggers

        # Wait for debounce period + buffer (3x for CI)
        time.sleep(0.3)

        # Should only fire once despite 10 triggers
        assert callback_count["count"] == 1

    def test_separate_bursts(self):
        """Test that separated bursts each result in callbacks."""
        callback_count = {"count": 0}

        def callback():
            callback_count["count"] += 1

        debouncer = Debouncer(callback, delay_ms=50)

        # First burst
        debouncer.trigger()
        debouncer.trigger()
        time.sleep(0.2)  # Wait for first callback (4x for CI)

        # Second burst
        debouncer.trigger()
        debouncer.trigger()
        time.sleep(0.2)  # Wait for second callback (4x for CI)

        assert callback_count["count"] == 2

    def test_thread_safety(self):
        """Test that debouncer is thread-safe."""
        callback_count = {"count": 0}
        lock = threading.Lock()

        def callback():
            with lock:
                callback_count["count"] += 1

        debouncer = Debouncer(callback, delay_ms=50)

        # Trigger from multiple threads simultaneously
        threads = []
        for _ in range(5):
            thread = threading.Thread(
                target=lambda: [debouncer.trigger() for _ in range(10)]
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Wait for debounce (4x for CI)
        time.sleep(0.2)

        # Should still only fire once despite multi-threaded triggers
        assert callback_count["count"] == 1

    def test_cancel(self):
        """Test that cancel prevents callback."""
        callback_count = {"count": 0}

        def callback():
            callback_count["count"] += 1

        debouncer = Debouncer(callback, delay_ms=200)
        debouncer.trigger()

        # Cancel immediately (before debounce period expires)
        time.sleep(0.01)
        debouncer.cancel()

        # Wait past debounce period with extra margin
        time.sleep(0.3)

        assert callback_count["count"] == 0

    def test_callback_exception_handled(self):
        """Test that exceptions in callback don't crash debouncer."""
        callback_count = {"count": 0}

        def failing_callback():
            callback_count["count"] += 1
            raise ValueError("Test exception")

        debouncer = Debouncer(failing_callback, delay_ms=50)

        # Should not raise despite callback exception
        debouncer.trigger()
        time.sleep(0.1)

        # Verify callback was called
        assert callback_count["count"] == 1

    def test_varying_delays(self):
        """Test different debounce delays."""
        for delay_ms in [10, 50, 100, 200]:
            callback_count = {"count": 0}

            def callback():
                callback_count["count"] += 1

            debouncer = Debouncer(callback, delay_ms=delay_ms)
            debouncer.trigger()

            # Wait for delay + generous buffer for macOS threading overhead
            time.sleep((delay_ms / 1000.0) + 0.15)

            assert callback_count["count"] == 1, f"Failed for delay_ms={delay_ms}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_burst_reuses_timer_and_reschedules_remaining_delay(monkeypatch):
    """An event burst should not create one OS thread per event."""
    from unittest.mock import Mock

    timers = []
    now = [10.0]

    class Timer:
        def __init__(self, delay, callback, args):
            self.delay, self.callback, self.args = delay, callback, args
            self.cancelled = False
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

        def fire(self):
            self.callback(*self.args)

    monkeypatch.setattr("audio_hotplug._debounce.threading.Timer", Timer)
    monkeypatch.setattr("audio_hotplug._debounce.time.monotonic", lambda: now[0])
    callback = Mock()
    debouncer = Debouncer(callback, delay_ms=100)
    debouncer.trigger()
    now[0] = 10.05
    for _ in range(1000):
        debouncer.trigger()
    assert len(timers) == 1
    now[0] = 10.1
    timers[0].fire()
    assert len(timers) == 2
    assert timers[1].delay == pytest.approx(0.05)
    callback.assert_not_called()
    now[0] = 10.2
    timers[1].fire()
    callback.assert_called_once_with()
    assert debouncer._timer is None


def test_cancel_invalidates_timer_and_close_rejects_late_events(monkeypatch):
    from unittest.mock import Mock

    timers = []

    def make_timer(delay, callback, args):
        timer = Mock()
        timer.fire = lambda: callback(*args)
        timers.append(timer)
        return timer

    monkeypatch.setattr("audio_hotplug._debounce.threading.Timer", make_timer)
    callback = Mock()
    debouncer = Debouncer(callback, delay_ms=0)
    debouncer.trigger()
    debouncer.cancel()
    debouncer.trigger()
    timers[0].fire()  # Simulate a cancelled timer already entering its callback.
    callback.assert_not_called()
    timers[1].fire()
    callback.assert_called_once_with()
    debouncer.close()
    debouncer.trigger()
    assert len(timers) == 2


def test_timer_start_failure_allows_retry(monkeypatch):
    from unittest.mock import Mock

    timer = Mock()
    timer.start.side_effect = RuntimeError("no thread available")
    monkeypatch.setattr(
        "audio_hotplug._debounce.threading.Timer", Mock(return_value=timer)
    )
    debouncer = Debouncer(Mock())
    with pytest.raises(RuntimeError):
        debouncer.trigger()
    assert debouncer._timer is None
    timer.start.side_effect = None
    debouncer.trigger()
    assert timer.start.call_count == 2
    debouncer.close()
