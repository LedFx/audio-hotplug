# audio-hotplug

Cross-platform audio device hotplug detection with debouncing for Windows, macOS, and Linux.

[![PyPI version](https://badge.fury.io/py/audio-hotplug.svg)](https://pypi.org/project/audio-hotplug/)
[![Python versions](https://img.shields.io/pypi/pyversions/audio-hotplug.svg)](https://pypi.org/project/audio-hotplug/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 🔌 **Cross-platform**: Works on Windows, macOS, and Linux
- ⚡ **Debouncing**: Coalesces rapid device changes to prevent callback storms
- 🔄 **Async-ready**: Supports both sync and async callbacks
- 🎯 **Focused**: Does one thing well - detects audio device topology changes
- 🪶 **Lightweight**: Minimal dependencies, platform-specific imports only when needed

## Installation

```bash
# Install with uv
uv pip install audio-hotplug

# Or with pip
pip install audio-hotplug
```

Platform-specific dependencies are installed automatically based on your OS.

## Quick Start

```python
import asyncio
from audio_hotplug import create_monitor


def on_audio_devices_changed():
    print("Audio devices changed!")


async def main():
    loop = asyncio.get_running_loop()

    # Create monitor with 200ms debounce
    monitor = create_monitor(loop=loop, debounce_ms=200)

    if monitor:
        monitor.start(on_audio_devices_changed)
        # Your application code here...
        await asyncio.sleep(60)
        monitor.stop()


asyncio.run(main())
```

## Usage

### Basic Usage (Sync Callback)

```python
from audio_hotplug import create_monitor


def handle_change():
    # Refresh your audio device list here
    print("Device list changed!")


monitor = create_monitor()
if monitor:
    monitor.start(handle_change)
```

### Async Callback

```python
import asyncio
from audio_hotplug import create_monitor


async def handle_change():
    # Async operations supported
    await notify_websocket_clients()
    print("Device list changed!")


async def main():
    loop = asyncio.get_running_loop()
    monitor = create_monitor(loop=loop)
    if monitor:
        monitor.start(handle_change)
        await asyncio.sleep(3600)
        monitor.stop()


asyncio.run(main())
```

### Custom Debouncing

```python
# Adjust debounce time (milliseconds)
monitor = create_monitor(debounce_ms=500)  # Wait 500ms after last change
```

### Custom Logging

```python
import logging

logger = logging.getLogger("my_app.audio")
monitor = create_monitor(logger=logger)
```

## How It Works

The library monitors OS-level audio device notifications:

- **Windows**: Uses Core Audio API (`IMMNotificationClient`) via `pycaw`
- **macOS**: Uses CoreAudio property listeners via `pyobjc-framework-CoreAudio`
- **Linux**: Uses `udev` subsystem monitoring via `pyudev`

When devices are added, removed, or change state, the library:

1. Detects the OS notification
2. Triggers the debouncer
3. Coalesces multiple rapid changes
4. Invokes your callback once after the debounce period

## API Reference

### `create_monitor()`

Creates a platform-specific audio device monitor.

**Parameters:**
- `loop` (optional): `asyncio.AbstractEventLoop` - Event loop for callback scheduling
- `debounce_ms` (optional): `int` - Milliseconds to wait before invoking callback (default: 200)
- `logger` (optional): `logging.Logger` - Custom logger instance

**Returns:**
- `AudioDeviceMonitor` instance or `None` if platform unsupported

### `AudioDeviceMonitor`

Abstract base class for platform monitors.

**Methods:**
- `start(on_change: Callback)` - Start monitoring, call `on_change` when devices change
- `stop()` - Stop monitoring (safe to call multiple times)

Call `stop()` before starting an existing monitor again. `start()` reports native
initialization failures to the caller; Linux and Windows wait up to five seconds
for their worker to initialize. `stop()` disables pending notifications and waits
up to two seconds for a Linux or Windows worker to exit. A callback already
executing is allowed to finish.

If native cleanup fails or a worker has not exited, the monitor logs a warning
and retains the resources needed for safe cleanup. Call `stop()` again to retry;
restarting is rejected until the previous registration or worker is gone.

**Callback signature:**
```python
# Sync callback
def on_change() -> None: ...


# Or async callback
async def on_change() -> None: ...
```

## Platform Support

| Platform | Dependency | Auto-installed |
|----------|-----------|----------------|
| Windows  | `pycaw`, `comtypes` | ✅ |
| macOS    | `pyobjc-framework-CoreAudio` | ✅ |
| Linux    | `pyudev` | ✅ |

Platform-specific dependencies are only installed on the relevant OS using package markers.

## Development

This project uses `uv` for development:

```bash
# Clone the repository
git clone https://github.com/LedFx/audio-hotplug.git
cd audio-hotplug

# Install with dev dependencies
uv sync --locked

# Run strict type checking for all platform modules
uv run pyrefly check

# Run tests
uv run pytest

# Run example
uv run python examples/monitor_print.py

# Build package
uv build
```

## Testing

```bash
# Run all tests
uv run pytest -v

# Run with coverage
uv run pytest --cov=audio_hotplug --cov-report=html

# Run specific test
uv run pytest tests/test_debounce.py
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

Extracted from [LedFx](https://github.com/LedFx/LedFx) to provide a reusable, focused library for audio device hotplug detection.

## Related Projects

- [LedFx](https://github.com/LedFx/LedFx) - Real-time LED visualization system
- [sounddevice](https://github.com/spatialaudio/python-sounddevice) - Audio I/O library
- [PortAudio](http://www.portaudio.com/) - Cross-platform audio I/O library

## Development and releases

Python 3.10 and newer is supported. CI tests Linux, Windows, and macOS on
Python 3.10–3.15 (including the current 3.15 prerelease). Native audio hardware
notifications still need manual platform testing; the automated suite covers
callback scheduling, debouncing, and monitor construction.

Run `uv sync --locked`, `uv run pytest`, `uv run pyrefly check`, and
`uvx prek run --all-files`.
Pyrefly uses its strict preset, checks Python 3.10 compatibility and every
platform backend, and rejects explicit `Any` and missing return annotations.
The focused stubs in `typings/` describe only the native APIs used here; keep
them aligned with upstream signatures when updating native dependencies. They
are development-only and are not shipped in the wheel.

Development tools live in dependency groups: `dev` includes `test` and `typing`;
`build` contains the distribution validator. CI installs only the group each
job needs. The platform extras remain available as compatibility aliases,
with OS markers preventing installation of another OS's native packages.

The same lint and strict type checks run before CI tests and distribution builds. Renovate uses
the shared LedFx configuration, and autofix.ci applies supported lint fixes.
Use a Conventional Commit PR title so release-please can generate the changelog.

Releases use the LedFx automation app (`AUTOMATION_APP_CLIENT_ID` and
`AUTOMATION_APP_PRIVATE_KEY` organisation secrets, accessible to this repository).
Merging the release-please PR updates package and lockfile versions and creates
a version tag plus draft GitHub release. Tag CI checks version consistency,
runs the full test matrix, and builds the distributions before publishing to
PyPI, then attaches those distributions and publishes the GitHub draft last.
The caller uses the SHA-pinned [shared release transaction](https://github.com/LedFx/release-ci)
and `.github/release-policy.json`, preserving the `publish.yml`/`pypi` identity.
The queued job verifies exact wheel/sdist metadata, SHA-256 and GitHub attestations
before finalization with its scoped App token. Matching partial uploads can retry
from the original run; conflicting files fail rather than using `--clobber`.
An existing release-please draft is required. Higher stable drafts/releases veto
latest promotion; an abandoned newer draft can delay latest without preventing
immutable version publication. Snapshots and provenance bundles are retained;
see the shared recovery guide before rerunning failed jobs.

The PyPI Trusted Publisher is not configured yet; this migration can pass PR CI,
but actual package publication remains blocked until an administrator configures it.
Configure PyPI Trusted Publishing for
owner `LedFx`, repository `audio-hotplug`, workflow `publish.yml`, and environment
`pypi`. Keep the GitHub `pypi` environment approval rules in place. The previous
API-token publishing path is replaced by OIDC; a manual workflow run validates
CI without publishing. Set the branch's required check to `CI passed` (and
`Conventional PR title`) instead of the retired individual workflows.
