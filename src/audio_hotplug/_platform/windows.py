"""Windows audio device monitor using Core Audio API (pycaw)."""

from typing_extensions import override

from .._base import Callback
from ._threaded import ThreadedAudioDeviceMonitor, _WorkerState


class WindowsAudioDeviceMonitor(ThreadedAudioDeviceMonitor):
    """Own the notification client and enumerator in one COM apartment."""

    @override
    def start(self, on_change: Callback) -> None:
        # comtypes initializes the importing thread's apartment. Import here so
        # its default STA initialization cannot conflict with our worker's MTA.
        import comtypes  # noqa: F401

        super().start(on_change)

    @override
    def _run(self, state: _WorkerState) -> None:
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator, IMMNotificationClient
        from pycaw.constants import CLSID_MMDeviceEnumerator

        class DeviceNotificationClient(comtypes.COMObject):
            # Use pycaw's ABI, notably PROPERTYKEY passed by value.
            _com_interfaces_ = [IMMNotificationClient]

            def OnDeviceAdded(self, device_id: str | None) -> int:  # noqa: N802
                state.events.put(True)
                return 0

            def OnDeviceRemoved(self, device_id: str | None) -> int:  # noqa: N802
                state.events.put(True)
                return 0

            def OnDeviceStateChanged(
                self, device_id: str | None, new_state: int
            ) -> int:  # noqa: N802
                state.events.put(True)
                return 0

            def OnDefaultDeviceChanged(
                self, flow: int, role: int, device_id: str | None
            ) -> int:  # noqa: N802
                return 0

            def OnPropertyValueChanged(self, device_id: str | None, key: object) -> int:  # noqa: N802
                return 0

        # A dedicated MTA worker needs no STA message pump. Callbacks only enqueue
        # work; they never wait for timers, cleanup, or user callbacks.
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        enumerator = None
        client = None
        registered = False
        failure = None
        try:
            enumerator = comtypes.CoCreateInstance(
                CLSID_MMDeviceEnumerator,
                IMMDeviceEnumerator,
                comtypes.CLSCTX_INPROC_SERVER,
            )
            client = DeviceNotificationClient()
            enumerator.RegisterEndpointNotificationCallback(client)
            registered = True
            state.ready.set()
            self._logger.info("Windows audio device monitor started")
            while not state.stopped.is_set():
                state.events.get()
                if not state.stopped.is_set():
                    state.debouncer.trigger()
        except Exception as error:
            # A native-call traceback may retain the enumerator/client. Drop
            # those frames before releasing the apartment's resources below.
            failure = error.with_traceback(None)
        finally:
            self._cancel_debouncer()
            if registered:
                assert enumerator is not None and client is not None
                # Do not drop the callback or tear down COM after failed removal:
                # Windows still holds its pointer. Retry on the next stop request.
                while True:
                    try:
                        enumerator.UnregisterEndpointNotificationCallback(client)
                        break
                    except Exception as error:
                        self._logger.warning(
                            "Failed to unregister Windows audio listener: %s; "
                            "call stop() to retry",
                            str(error),
                        )
                        # Consume pending notifications until another stop request.
                        # The first stop token may still be queued; retrying once
                        # immediately is harmless and does not busy-loop.
                        while state.events.get() is not None:
                            pass
            # Release apartment-owned pointers before uninitializing COM.
            client = None
            enumerator = None
            comtypes.CoUninitialize()
        if failure is not None:
            raise failure
