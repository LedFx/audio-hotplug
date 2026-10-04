"""Subset of comtypes used here; native COM pointers expose interface methods.

Reference: https://github.com/enthought/comtypes (CoCreateInstance and COMObject).
"""

from typing import TypeVar

class GUID: ...
class IUnknown: ...

class COMObject:
    _com_interfaces_: list[type[IUnknown]]

_Interface = TypeVar("_Interface", bound=IUnknown)
COINIT_MULTITHREADED: int
CLSCTX_INPROC_SERVER: int

def CoInitializeEx(flags: int) -> None: ...
def CoUninitialize() -> None: ...
def CoCreateInstance(
    clsid: GUID, interface: type[_Interface], clsctx: int
) -> _Interface: ...
