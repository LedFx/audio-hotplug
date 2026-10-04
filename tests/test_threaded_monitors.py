"""Worker lifecycle tests using native API doubles on every host platform."""

import asyncio
import queue
import sys
import threading
import weakref
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from audio_hotplug._platform.linux import LinuxAudioDeviceMonitor
from audio_hotplug._platform.windows import WindowsAudioDeviceMonitor


@pytest.fixture(params=["linux", "windows"])
def backend(request, monkeypatch):
    native = SimpleNamespace(
        platform=request.param,
        calls=[],
        events=queue.Queue(),
        clients=[],
        fail_setup=False,
        fail_cleanup=False,
        setup_gate=threading.Event(),
        setup_entered=threading.Event(),
        cleanup_entered=threading.Event(),
    )
    native.setup_gate.set()

    def record(name):
        native.calls.append((name, threading.get_ident()))

    def setup():
        record("setup")
        native.setup_entered.set()
        assert native.setup_gate.wait(3)
        if native.fail_setup:
            raise RuntimeError("native setup failed")

    if request.param == "linux":

        class UdevMonitor:
            def filter_by(self, **kwargs):
                assert kwargs == {"subsystem": "sound"}

            def start(self):
                setup()

            def poll(self, timeout):
                try:
                    result = native.events.get(timeout=min(timeout, 0.02))
                except queue.Empty:
                    return None
                if isinstance(result, Exception):
                    raise result
                return result

        monkeypatch.setitem(
            sys.modules,
            "pyudev",
            SimpleNamespace(
                Context=object,
                Monitor=SimpleNamespace(from_netlink=lambda context: UdevMonitor()),
            ),
        )
        monitor = LinuxAudioDeviceMonitor()
        native.emit = lambda: native.events.put(SimpleNamespace(action="add"))
    else:

        class Enumerator:
            def RegisterEndpointNotificationCallback(self, client):  # noqa: N802
                setup()
                native.clients.append(weakref.ref(client))

            def UnregisterEndpointNotificationCallback(self, client):  # noqa: N802
                record("unregister")
                native.cleanup_entered.set()
                assert native.clients[-1]() is client
                if native.fail_cleanup:
                    raise RuntimeError("native cleanup failed")

            def __del__(self):
                record("release")

        def initialize(flags):
            assert flags == 0
            record("initialize")

        monkeypatch.setitem(
            sys.modules,
            "comtypes",
            SimpleNamespace(
                COMObject=object,
                COINIT_MULTITHREADED=0,
                CLSCTX_INPROC_SERVER=1,
                CoInitializeEx=initialize,
                CoUninitialize=lambda: record("uninitialize"),
                CoCreateInstance=lambda *args: Enumerator(),
            ),
        )
        monkeypatch.setitem(sys.modules, "pycaw", SimpleNamespace())
        monkeypatch.setitem(sys.modules, "pycaw.api", SimpleNamespace())
        monkeypatch.setitem(
            sys.modules,
            "pycaw.api.mmdeviceapi",
            SimpleNamespace(
                IMMDeviceEnumerator=object,
                IMMNotificationClient=object,
            ),
        )
        monkeypatch.setitem(
            sys.modules,
            "pycaw.constants",
            SimpleNamespace(
                CLSID_MMDeviceEnumerator=object(),
            ),
        )
        monitor = WindowsAudioDeviceMonitor()
        native.emit = lambda: native.clients[-1]().OnDeviceAdded("test-device")

    native.monitor = monitor
    yield native
    native.fail_cleanup = False
    native.setup_gate.set()
    monitor.stop()


def test_registration_duplicate_start_stop_and_restart(backend):
    monitor = backend.monitor
    monitor.stop()
    monitor.start(Mock())
    thread = monitor._monitor_thread
    state = monitor._worker_state
    assert backend.setup_entered.is_set()
    with pytest.raises(RuntimeError, match="still active"):
        monitor.start(Mock())
    assert monitor._worker_state is state
    monitor.stop()
    assert not thread.is_alive()
    assert not monitor._running
    monitor.stop()
    monitor.start(Mock())
    assert monitor._worker_state is not state


def test_setup_failure_reaches_caller_and_can_retry(backend):
    monitor = backend.monitor
    backend.fail_setup = True
    with pytest.raises(RuntimeError, match="native setup failed"):
        monitor.start(Mock())
    assert not monitor._running
    assert not monitor._monitor_thread.is_alive()
    backend.fail_setup = False
    monitor.start(Mock())
    assert monitor._running


def test_setup_timeout_blocks_restart_until_original_worker_exits(backend):
    monitor = backend.monitor
    monitor._startup_timeout = 0.02
    monitor._shutdown_timeout = 0.02
    backend.setup_gate.clear()
    with pytest.raises(TimeoutError):
        monitor.start(Mock())
    old_thread = monitor._monitor_thread
    with pytest.raises(RuntimeError, match="still active"):
        monitor.start(Mock())
    backend.setup_gate.set()
    old_thread.join(2)
    assert not old_thread.is_alive()
    monitor._startup_timeout = 1
    monitor.start(Mock())


def test_event_delivery_and_no_late_notifications(backend):
    monitor = backend.monitor
    monitor._debounce_ms = 0
    received = threading.Event()
    monitor.start(received.set)
    backend.emit()
    assert received.wait(2)
    debouncer = monitor._debouncer
    monitor.stop()
    received.clear()
    debouncer.trigger()
    assert debouncer._timer is None
    if backend.platform == "windows":
        assert backend.clients[-1]() is None


def test_thread_start_failure_leaves_monitor_stopped(backend):
    monitor = backend.monitor
    with patch("threading.Thread.start", side_effect=RuntimeError("thread failed")):
        with pytest.raises(RuntimeError, match="thread failed"):
            monitor.start(Mock())
    assert not monitor._running
    monitor.stop()
    monitor.start(Mock())


@pytest.mark.parametrize("async_callback", [False, True])
def test_queued_callbacks_do_not_cross_restart(backend, async_callback):
    monitor = backend.monitor
    loop = asyncio.new_event_loop()
    monitor._loop = loop
    original = Mock()

    async def callback():
        original()

    try:
        monitor.start(callback if async_callback else original)
        monitor._debouncer._invoke_callback()
        monitor.stop()
        monitor.start(Mock())
        loop.run_until_complete(asyncio.sleep(0))
        original.assert_not_called()
    finally:
        monitor.stop()
        loop.close()


def test_linux_poll_failure_stops_worker_and_allows_restart(backend):
    if backend.platform != "linux":
        pytest.skip("Linux poll failure")
    monitor = backend.monitor
    monitor.start(Mock())
    thread = monitor._monitor_thread
    backend.events.put(RuntimeError("poll failed"))
    thread.join(2)
    assert not thread.is_alive()
    assert not monitor._running
    monitor.start(Mock())


def test_windows_com_cleanup_runs_on_owner_thread(backend):
    if backend.platform != "windows":
        pytest.skip("Windows COM ownership")
    monitor = backend.monitor
    monitor.start(Mock())
    thread = monitor._monitor_thread
    monitor.stop()
    assert [name for name, _ in backend.calls] == [
        "initialize",
        "setup",
        "unregister",
        "release",
        "uninitialize",
    ]
    assert {ident for _, ident in backend.calls} == {thread.ident}
    assert thread.ident != threading.get_ident()


def test_windows_failed_removal_retains_client_and_retries(backend):
    if backend.platform != "windows":
        pytest.skip("Windows registration lifetime")
    monitor = backend.monitor
    monitor._shutdown_timeout = 0.03
    monitor.start(Mock())
    thread = monitor._monitor_thread
    backend.fail_cleanup = True
    monitor.stop()
    assert backend.cleanup_entered.wait(1)
    assert thread.is_alive()
    assert backend.clients[-1]() is not None
    assert "uninitialize" not in [name for name, _ in backend.calls]
    with pytest.raises(RuntimeError, match="still active"):
        monitor.start(Mock())
    backend.fail_cleanup = False
    monitor._shutdown_timeout = 1
    monitor.stop()
    assert not thread.is_alive()
    assert backend.clients[-1]() is None


def test_windows_native_callback_only_enqueues(backend):
    if backend.platform != "windows":
        pytest.skip("Windows callback dispatch")
    monitor = backend.monitor
    monitor.start(Mock())
    client = backend.clients[-1]()
    triggered = threading.Event()
    owner = []

    def trigger():
        owner.append(threading.get_ident())
        triggered.set()

    with patch.object(monitor._debouncer, "trigger", side_effect=trigger):
        assert client.OnPropertyValueChanged("device", object()) == 0
        assert client.OnDefaultDeviceChanged(0, 0, "device") == 0
        assert client.OnDeviceStateChanged("device", 1) == 0
        assert triggered.wait(2)
    assert owner == [monitor._monitor_thread.ident]


@pytest.mark.skipif(sys.platform != "win32", reason="Requires Windows Core Audio")
def test_native_windows_registration():
    monitor = WindowsAudioDeviceMonitor()
    try:
        monitor.start(Mock())
        assert monitor._running
    finally:
        monitor.stop()
    assert monitor._monitor_thread is None


def test_windows_com_initialization_failure_does_not_uninitialize(backend, monkeypatch):
    if backend.platform != "windows":
        pytest.skip("Windows COM initialization")
    comtypes = sys.modules["comtypes"]
    monkeypatch.setattr(
        comtypes, "CoInitializeEx", Mock(side_effect=RuntimeError("COM init failed"))
    )
    with pytest.raises(RuntimeError, match="COM init failed"):
        backend.monitor.start(Mock())
    assert "uninitialize" not in [name for name, _ in backend.calls]
    assert not backend.monitor._running


def test_windows_registration_failure_releases_com_resources(backend):
    if backend.platform != "windows":
        pytest.skip("Windows COM registration")
    backend.fail_setup = True
    with pytest.raises(RuntimeError, match="native setup failed"):
        backend.monitor.start(Mock())
    assert [name for name, _ in backend.calls] == [
        "initialize",
        "setup",
        "release",
        "uninitialize",
    ]
