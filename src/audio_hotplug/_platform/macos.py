"""macOS audio device monitor using CoreAudio framework."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

from typing_extensions import override

if TYPE_CHECKING:
    from CoreAudio import AudioObjectPropertyAddress

from .._base import AudioDeviceMonitor, Callback
from .._debounce import Debouncer

# CoreAudio holds a C pointer, not a Python reference. Keep registered closures
# alive even if the caller drops its monitor, including after a failed removal.
_NativeCallback = Callable[[int, int, object, object], int]
_REGISTERED_CALLBACKS: set[_NativeCallback] = set()


class _ListenerState:
    """Gate native notifications independently of the monitor lifecycle lock."""

    def __init__(self, debouncer: Debouncer, logger: logging.Logger) -> None:
        self.debouncer = debouncer
        self.logger = logger
        self.lock = threading.Lock()
        self.active = True

    def changed(self) -> None:
        # Serialize triggering with cancellation so a late callback cannot
        # create a timer after stop(). Never take this lock around CoreAudio.
        with self.lock:
            if self.active:
                self.debouncer.trigger()

    def cancel(self) -> None:
        with self.lock:
            self.active = False
            self.debouncer.cancel()


class MacOSAudioDeviceMonitor(AudioDeviceMonitor):
    """macOS audio device monitor using CoreAudio property listeners."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop | None = None,
        debounce_ms: int = 200,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(loop=loop, debounce_ms=debounce_ms, logger=logger)
        self._lifecycle_lock = threading.Lock()
        self._callback_ref: _NativeCallback | None = None
        self._property_address: AudioObjectPropertyAddress | None = None
        self._listener_state: _ListenerState | None = None

    @override
    def start(self, on_change: Callback) -> None:
        """Start monitoring. Stop the existing listener before starting again."""
        with self._lifecycle_lock:
            if self._callback_ref is not None:
                raise RuntimeError(
                    "macOS audio listener already registered; call stop() first"
                )
            self._start(on_change)

    def _start(self, on_change: Callback) -> None:
        try:
            import objc
            from CoreAudio import (
                AudioObjectAddPropertyListener,
                AudioObjectPropertyAddress,
                kAudioHardwarePropertyDevices,
                kAudioObjectPropertyElementMaster,
                kAudioObjectPropertyScopeGlobal,
                kAudioObjectSystemObject,
            )

            property_address = AudioObjectPropertyAddress(
                kAudioHardwarePropertyDevices,
                kAudioObjectPropertyScopeGlobal,
                kAudioObjectPropertyElementMaster,
            )
            debouncer = self._initialize_debouncer(on_change)
            state = _ListenerState(debouncer, self._logger)
            self._listener_state = state

            # CoreAudio retains this callback, so it needs a persistent C closure.
            @objc.callbackFor(AudioObjectAddPropertyListener)
            def device_list_changed_callback(
                obj_id: int, num_addresses: int, addresses: object, client_data: object
            ) -> int:
                try:
                    state.changed()
                except Exception:
                    # Python exceptions must not unwind through the native callback.
                    state.logger.exception("Error handling macOS audio device change")
                return 0

            status = AudioObjectAddPropertyListener(
                kAudioObjectSystemObject,
                property_address,
                device_list_changed_callback,
                None,
            )
            if status != 0:
                raise RuntimeError(
                    f"AudioObjectAddPropertyListener failed: OSStatus {status}"
                )

            _REGISTERED_CALLBACKS.add(device_list_changed_callback)
            self._property_address = property_address
            self._callback_ref = device_list_changed_callback
        except Exception:
            self._cancel_debouncer()
            if self._listener_state is not None:
                self._listener_state.cancel()
            self._listener_state = None
            self._debouncer = None
            self._callback = None
            self._logger.exception("Failed to start macOS audio device monitor")
            raise

        self._logger.info("macOS audio device monitor started")

    @override
    def stop(self) -> None:
        """Stop monitoring; failed native removal can be retried with stop()."""
        with self._lifecycle_lock:
            self._cancel_debouncer()
            if self._listener_state is not None:
                self._listener_state.cancel()

            if self._callback_ref is None:
                return

            assert self._property_address is not None
            try:
                from CoreAudio import (
                    AudioObjectRemovePropertyListener,
                    kAudioObjectSystemObject,
                )

                status = AudioObjectRemovePropertyListener(
                    kAudioObjectSystemObject,
                    self._property_address,
                    self._callback_ref,
                    None,
                )
                if status != 0:
                    raise RuntimeError(
                        f"AudioObjectRemovePropertyListener failed: OSStatus {status}"
                    )
            except Exception:
                # Preserve the closure and registration details until removal
                # succeeds. Releasing them could leave CoreAudio a dangling pointer.
                self._logger.warning("Error stopping macOS monitor", exc_info=True)
                return

            _REGISTERED_CALLBACKS.discard(self._callback_ref)
            self._callback_ref = None
            self._property_address = None
            self._listener_state = None
            self._debouncer = None
            self._callback = None
            self._logger.info("macOS audio device monitor stopped")
