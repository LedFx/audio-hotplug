# Audio-Hotplug Migration Quick Start

## Prerequisites

- [x] GitHub account with LedFx organization access
- [x] PyPI account (create at https://pypi.org/account/register/)
- [x] Git installed
- [x] Python 3.10+ installed

## Quick Steps

### 1. Extract Repository (5 minutes)

```powershell
# Install git-filter-repo if needed
pip install git-filter-repo

# Create working directory
cd C:\mine\development\ledfx
New-Item -ItemType Directory -Path "audio-hotplug-extraction" -Force
cd audio-hotplug-extraction

# Clone and extract
git clone --no-hardlinks C:\mine\development\ledfx\LedFx temp-repo
cd temp-repo
git checkout audio-device-hotswap
git filter-repo --path audio-hotplug/ --path-rename audio-hotplug/:
```

### 2. Create GitHub Repository (2 minutes)

1. Go to https://github.com/LedFx/
2. Click "New repository"
3. Name: `audio-hotplug`
4. Description: "Cross-platform audio device hotplug detection library"
5. Public
6. **Don't** initialize with README
7. Create

### 3. Push to GitHub (1 minute)

```powershell
# Still in temp-repo directory
git remote add origin git@github.com:LedFx/audio-hotplug.git
git branch -M main
git push -u origin main
```

### 4. Copy GitHub Actions Workflows (1 minute)

```powershell
# Copy .github directory from LedFx/audio-hotplug to temp-repo
Copy-Item -Path "C:\mine\development\ledfx\LedFx\audio-hotplug\.github" -Destination "." -Recurse -Force

# Copy .pre-commit-config.yaml
Copy-Item -Path "C:\mine\development\ledfx\LedFx\audio-hotplug\.pre-commit-config.yaml" -Destination "." -Force

# Copy MANIFEST.in
Copy-Item -Path "C:\mine\development\ledfx\LedFx\audio-hotplug\MANIFEST.in" -Destination "." -Force

# Commit and push
git add .
git commit -m "ci: Add GitHub Actions workflows and pre-commit config"
git push
```

### 5. Set Up PyPI (5 minutes)

#### Create API Tokens

1. **PyPI Production**:
   - Go to https://pypi.org/manage/account/token/
   - Click "Add API token"
   - Token name: `audio-hotplug-ci`
   - Scope: "Entire account" (or project-specific after first upload)
   - Click "Add token"
   - **COPY THE TOKEN** (starts with `pypi-`)

2. **TestPyPI** (optional but recommended):
   - Go to https://test.pypi.org/manage/account/token/
   - Same steps
   - Token name: `audio-hotplug-test-ci`
   - **COPY THE TOKEN**

#### Add Tokens to GitHub

1. Go to https://github.com/LedFx/audio-hotplug/settings/secrets/actions
2. Click "New repository secret"
3. Add `PYPI_API_TOKEN`:
   - Name: `PYPI_API_TOKEN`
   - Secret: Paste production token
   - Click "Add secret"
4. Add `TEST_PYPI_API_TOKEN`:
   - Name: `TEST_PYPI_API_TOKEN`
   - Secret: Paste test token
   - Click "Add secret"

### 6. Test Build Locally (5 minutes)

```powershell
# Install build tools
pip install build twine

# Build
python -m build

# Check
python -m twine check dist/*

# Should see:
# Checking dist/audio_hotplug-0.1.0-py3-none-any.whl: PASSED
# Checking dist/audio_hotplug-0.1.0.tar.gz: PASSED
```

### 7. Publish to TestPyPI (3 minutes)

```powershell
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*
# Enter username: __token__
# Enter password: (paste TEST_PYPI_API_TOKEN)

# Test install in a new environment
python -m venv test_env
test_env\Scripts\activate
pip install --index-url https://test.pypi.org/simple/ --no-deps audio-hotplug

# Test import
python -c "from audio_hotplug import create_monitor; print('Success!')"

# Cleanup
deactivate
```

### 8. Publish to PyPI via GitHub (2 minutes)

```powershell
# Create and push release tag
git tag v0.1.0
git push origin v0.1.0

# OR: Create release on GitHub
# Go to https://github.com/LedFx/audio-hotplug/releases/new
# Tag: v0.1.0
# Title: v0.1.0 - Initial Release
# Description: First public release
# Click "Publish release"
```

GitHub Actions will automatically:
- Run tests on Windows/Linux/macOS
- Build the package
- Publish to PyPI

### 9. Verify PyPI Publication (1 minute)

1. Check https://pypi.org/project/audio-hotplug/
2. Test install:
   ```powershell
   pip install audio-hotplug
   python -c "from audio_hotplug import create_monitor; print('Success!')"
   ```

### 10. Create Clean LedFx PR (10 minutes)

```powershell
cd C:\mine\development\ledfx\LedFx

# Update main
git checkout main
git pull upstream main

# Create new branch
git checkout -b feat/audio-hotplug-pypi-integration
```

Edit `pyproject.toml`:
```toml
dependencies = [
    # ... existing deps ...
    "audio-hotplug>=0.1.0",  # Add this
]

# Remove these sections:
# [tool.uv.workspace]
# members = ["audio-hotplug"]
#
# [tool.uv.sources]
# audio-hotplug = { workspace = true }
```

Remove directory and update lock:
```powershell
Remove-Item -Recurse -Force audio-hotplug
uv lock --upgrade-package audio-hotplug
uv sync
```

Test:
```powershell
uv run python -m ledfx --offline -vv
# Test audio device changes
```

Commit:
```powershell
git add .
git commit -m "feat: Integrate audio-hotplug from PyPI

- Replace workspace dependency with PyPI package (audio-hotplug>=0.1.0)
- Remove audio-hotplug workspace directory
- Audio device monitoring now uses published package"

git push origin feat/audio-hotplug-pypi-integration
```

Create PR on GitHub - should show **~10 files changed**!

## Total Time: ~35 minutes

## Troubleshooting

### "git filter-repo: command not found"
```powershell
pip install git-filter-repo
```

### PyPI upload asks for username
Use `__token__` as username and your API token as password.

### Tests fail in CI
Check logs at https://github.com/LedFx/audio-hotplug/actions

### Module not found after install
Package name has hyphen (`audio-hotplug`) but imports with underscore:
```python
import audio_hotplug  # Correct
```

## Next Steps

- [ ] Add badges to README (build, coverage, PyPI)
- [ ] Set up Read the Docs
- [ ] Enable pre-commit.ci bot
- [ ] Add CHANGELOG.md
- [ ] Tag additional releases as needed

## Support

If you encounter issues:
1. Check the detailed [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
2. Open an issue on GitHub
3. Contact maintainers on Discord
