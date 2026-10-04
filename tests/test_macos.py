"""Regression tests for CoreAudio listener callbacks."""

import asyncio
import gc
import sys
import threading
import weakref
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from audio_hotplug._platform.macos import MacOSAudioDeviceMonitor


@pytest.fixture
def core_audio(monkeypatch):
    """Model native registration without retaining Python callbacks."""
    closures = weakref.WeakSet()

    def add_listener(obj_id, address, callback, client_data):
        if callback not in closures:
            raise TypeError("Callable argument is not a PyObjC closure")
        return 0

    core_audio = SimpleNamespace(
        AudioObjectAddPropertyListener=Mock(side_effect=add_listener),
        AudioObjectRemovePropertyListener=Mock(return_value=0),
        AudioObjectPropertyAddress=Mock(return_value=object()),
        kAudioHardwarePropertyDevices=1,
        kAudioObjectPropertyScopeGlobal=2,
        kAudioObjectPropertyElementMaster=0,
        kAudioObjectSystemObject=1,
    )

    def callback_for(api):
        assert api is core_audio.AudioObjectAddPropertyListener

        def decorate(callback):
            closures.add(callback)
            return callback

        return decorate

    monkeypatch.setitem(sys.modules, "CoreAudio", core_audio)
    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(callbackFor=callback_for))
    return core_audio


def test_listener_uses_persistent_closure(core_audio):
    """Require a bridged callback and reuse it when removing the listener."""
    monitor = MacOSAudioDeviceMonitor()
    monitor.start(Mock())
    try:
        callback = monitor._callback_ref
        address = monitor._property_address
        core_audio.AudioObjectAddPropertyListener.assert_called_once_with(
            core_audio.kAudioObjectSystemObject, address, callback, None
        )
        with patch.object(monitor._debouncer, "trigger") as trigger:
            assert (
                callback(core_audio.kAudioObjectSystemObject, 1, [address], None) == 0
            )
            trigger.assert_called_once_with()
    finally:
        monitor.stop()

    core_audio.AudioObjectRemovePropertyListener.assert_called_once_with(
        core_audio.kAudioObjectSystemObject, address, callback, None
    )


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires macOS CoreAudio")
def test_native_listener_registration():
    """Exercise the real PyObjC bridge on macOS without changing audio devices."""
    import objc

    monitor = MacOSAudioDeviceMonitor()
    try:
        monitor.start(Mock())
        assert objc.callbackPointer(monitor._callback_ref) is not None
    finally:
        monitor.stop()
    assert monitor._callback_ref is None


def test_duplicate_start_preserves_registration(core_audio):
    monitor = MacOSAudioDeviceMonitor()
    original = Mock()
    monitor.start(original)
    callback = monitor._callback_ref
    debouncer = monitor._debouncer
    try:
        with pytest.raises(RuntimeError, match="already registered"):
            monitor.start(Mock())
        assert monitor._callback_ref is callback
        assert monitor._debouncer is debouncer
        assert core_audio.AudioObjectAddPropertyListener.call_count == 1
    finally:
        monitor.stop()


@pytest.mark.parametrize("failure", [-50, RuntimeError("bridge failure")])
def test_registration_failure_can_retry(core_audio, failure):
    core_audio.AudioObjectAddPropertyListener.side_effect = (
        failure if isinstance(failure, Exception) else None
    )
    core_audio.AudioObjectAddPropertyListener.return_value = failure
    monitor = MacOSAudioDeviceMonitor()
    with pytest.raises(RuntimeError):
        monitor.start(Mock())
    assert not monitor._running
    assert monitor._callback_ref is None
    assert monitor._debouncer is None
    monitor.stop()
    core_audio.AudioObjectRemovePropertyListener.assert_not_called()

    core_audio.AudioObjectAddPropertyListener.side_effect = None
    core_audio.AudioObjectAddPropertyListener.return_value = 0
    monitor.start(Mock())
    monitor.stop()


@pytest.mark.parametrize("failure", [-50, RuntimeError("bridge failure")])
def test_removal_failure_keeps_closure_for_retry(core_audio, failure, caplog):
    monitor = MacOSAudioDeviceMonitor()
    monitor.start(Mock())
    callback = monitor._callback_ref
    debouncer = monitor._debouncer
    core_audio.AudioObjectRemovePropertyListener.side_effect = (
        failure if isinstance(failure, Exception) else None
    )
    core_audio.AudioObjectRemovePropertyListener.return_value = failure
    try:
        monitor.stop()
        assert "Error stopping macOS monitor" in caplog.text
        assert monitor._callback_ref is callback
        assert not monitor._running
        with patch.object(debouncer, "trigger") as trigger:
            assert callback(1, 1, [], None) == 0
            trigger.assert_not_called()
        with pytest.raises(RuntimeError, match="already registered"):
            monitor.start(Mock())
    finally:
        core_audio.AudioObjectRemovePropertyListener.side_effect = None
        core_audio.AudioObjectRemovePropertyListener.return_value = 0
        monitor.stop()
    assert monitor._callback_ref is None
    monitor.stop()
    assert core_audio.AudioObjectRemovePropertyListener.call_count == 2


def test_old_notifications_ignored_after_restart(core_audio):
    monitor = MacOSAudioDeviceMonitor()
    monitor.stop()
    monitor.start(Mock())
    old_callback = monitor._callback_ref
    monitor.stop()
    monitor.start(Mock())
    try:
        with patch.object(monitor._debouncer, "trigger") as trigger:
            assert old_callback(1, 1, [], None) == 0
            trigger.assert_not_called()
            assert monitor._callback_ref(1, 1, [], None) == 0
            trigger.assert_called_once_with()
    finally:
        monitor.stop()


def test_native_callback_contains_python_exception(core_audio, caplog):
    monitor = MacOSAudioDeviceMonitor()
    monitor.start(Mock())
    try:
        with patch.object(
            monitor._debouncer, "trigger", side_effect=RuntimeError("timer failed")
        ):
            assert monitor._callback_ref(1, 1, [], None) == 0
        assert "timer failed" in caplog.text
    finally:
        monitor.stop()


def test_registered_closure_survives_gc_and_is_released_on_stop(core_audio):
    monitor = MacOSAudioDeviceMonitor()
    monitor.start(Mock())
    monitor_ref = weakref.ref(monitor)
    callback_ref = weakref.ref(monitor._callback_ref)
    # Mocks otherwise retain the Python callback through call_args.
    core_audio.AudioObjectAddPropertyListener.reset_mock()
    del monitor
    gc.collect()
    assert callback_ref() is not None
    assert monitor_ref() is not None
    monitor_ref().stop()
    core_audio.AudioObjectRemovePropertyListener.reset_mock()
    gc.collect()
    assert callback_ref() is None
    assert monitor_ref() is None


def test_stop_cancels_timer_created_by_inflight_notification(core_audio):
    monitor = MacOSAudioDeviceMonitor()
    monitor.start(Mock())
    entered = threading.Event()
    release = threading.Event()
    stopped = threading.Event()
    debouncer = monitor._debouncer
    calls = []

    def trigger():
        entered.set()
        assert release.wait(2)
        calls.append("trigger")

    def stop():
        monitor.stop()
        stopped.set()

    with (
        patch.object(debouncer, "trigger", side_effect=trigger),
        patch.object(debouncer, "cancel", side_effect=lambda: calls.append("cancel")),
    ):
        notification = threading.Thread(
            target=monitor._callback_ref, args=(1, 1, [], None)
        )
        stopping = threading.Thread(target=stop)
        try:
            notification.start()
            assert entered.wait(2)
            stopping.start()
        finally:
            release.set()
            notification.join(2)
            if stopping.ident is not None:
                stopping.join(2)
        assert stopped.is_set()
        assert calls == ["trigger", "cancel"]


@pytest.mark.parametrize("async_callback", [False, True])
def test_queued_notification_ignored_after_stop_and_restart(core_audio, async_callback):
    loop = asyncio.new_event_loop()
    original = Mock()

    async def async_original():
        original()

    monitor = MacOSAudioDeviceMonitor(loop=loop)
    try:
        monitor.start(async_original if async_callback else original)
        monitor._debouncer._invoke_callback()
        monitor.stop()
        monitor.start(Mock())
        loop.run_until_complete(asyncio.sleep(0))
        original.assert_not_called()
    finally:
        monitor.stop()
        loop.close()


@pytest.mark.parametrize("async_callback", [False, True])
def test_active_notification_delivers_user_callback(core_audio, async_callback):
    loop = asyncio.new_event_loop()
    received = Mock()

    async def async_received():
        received()

    monitor = MacOSAudioDeviceMonitor(loop=loop)
    try:
        monitor.start(async_received if async_callback else received)
        monitor._debouncer._invoke_callback()
        loop.run_until_complete(asyncio.sleep(0))
        received.assert_called_once_with()
    finally:
        monitor.stop()
        loop.close()


def test_native_removal_can_wait_for_callback(core_audio):
    monitor = MacOSAudioDeviceMonitor()
    monitor.start(Mock())
    completed = threading.Event()

    def remove_listener(obj_id, address, callback, client_data):
        def notify():
            callback(obj_id, 1, [address], client_data)
            completed.set()

        worker = threading.Thread(target=notify, daemon=True)
        worker.start()
        worker.join(2)
        assert completed.is_set(), "Removal deadlocked with native callback"
        return 0

    core_audio.AudioObjectRemovePropertyListener.side_effect = remove_listener
    try:
        monitor.stop()
        assert completed.is_set()
        assert monitor._callback_ref is None
    finally:
        core_audio.AudioObjectRemovePropertyListener.side_effect = None
        monitor.stop()


def test_missing_pyobjc_leaves_monitor_stopped(monkeypatch):
    monkeypatch.setitem(sys.modules, "objc", None)
    monitor = MacOSAudioDeviceMonitor()
    with pytest.raises(ImportError):
        monitor.start(Mock())
    assert not monitor._running
    assert monitor._debouncer is None
    monitor.stop()
