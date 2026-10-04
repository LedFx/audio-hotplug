"""The CoreAudio listener API used by this project (PyObjC's C bridge).

Reference: pyobjc-framework-CoreAudio/PyObjCTest/test_audiohardware.py
in https://github.com/ronaldoussoren/pyobjc.
"""

from collections.abc import Callable

class AudioObjectPropertyAddress:
    mSelector: int
    mScope: int
    mElement: int
    def __init__(self, mSelector: int, mScope: int, mElement: int) -> None: ...

# The opaque callback arguments are never dereferenced by this package.
AudioObjectPropertyListenerProc = Callable[[int, int, object, object], int]
kAudioHardwarePropertyDevices: int
kAudioObjectPropertyElementMaster: int
kAudioObjectPropertyScopeGlobal: int
kAudioObjectSystemObject: int

def AudioObjectAddPropertyListener(
    object_id: int,
    address: AudioObjectPropertyAddress,
    listener: AudioObjectPropertyListenerProc,
    client_data: None,
) -> int: ...
def AudioObjectRemovePropertyListener(
    object_id: int,
    address: AudioObjectPropertyAddress,
    listener: AudioObjectPropertyListenerProc,
    client_data: None,
) -> int: ...
