"""Linux audio device monitor using udev."""

from typing_extensions import override

from ._threaded import ThreadedAudioDeviceMonitor, _WorkerState


class LinuxAudioDeviceMonitor(ThreadedAudioDeviceMonitor):
    """Linux audio device monitor using pyudev."""

    @override
    def _run(self, state: _WorkerState) -> None:
        import pyudev

        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem="sound")
        # Subscribe before start() returns, and surface setup errors to callers.
        monitor.start()
        state.ready.set()
        self._logger.info("Linux audio device monitor started")
        while not state.stopped.is_set():
            device = monitor.poll(timeout=1.0)
            if state.stopped.is_set():
                break
            if device is not None and device.action in ("add", "remove"):
                state.debouncer.trigger()
