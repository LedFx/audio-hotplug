"""Signature-preserving PyObjC callback decorator used for CoreAudio."""

from collections.abc import Callable
from typing import ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")

def callbackFor(
    function: object, argIndex: int = ...
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...
