"""Audio device hotplug detection library.

Detects when audio devices are added, removed, or changed on
Windows, macOS, and Linux. Provides a simple callback-based API
with debouncing to prevent event storms.
"""

from ._base import AudioDeviceMonitor
from .monitor import create_monitor

__version__ = "0.2.1"  # x-release-please-version
__all__ = ["create_monitor", "AudioDeviceMonitor"]
