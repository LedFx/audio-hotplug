# Audio-Hotplug Repository Migration Guide

This guide walks through extracting audio-hotplug into its own repository and publishing to PyPI.

## Phase 1: Extract Repository with History

### Step 1: Create New Repository on GitHub

1. Go to https://github.com/LedFx (or your org)
2. Click "New repository"
3. Name: `audio-hotplug`
4. Description: "Cross-platform audio device hotplug detection library"
5. Public repository
6. **Don't** initialize with README (we have one)
7. Create repository

### Step 2: Extract audio-hotplug Subdirectory

Run these commands in a temporary directory:

```powershell
# Create temporary working directory
cd C:\mine\development\ledfx
New-Item -ItemType Directory -Path "audio-hotplug-extraction" -Force
cd audio-hotplug-extraction

# Clone the repository locally
git clone --no-hardlinks C:\mine\development\ledfx\LedFx temp-repo
cd temp-repo

# Checkout the branch with audio-hotplug
git checkout audio-device-hotswap

# Extract only audio-hotplug subdirectory with history
git filter-repo --path audio-hotplug/ --path-rename audio-hotplug/:

# This creates a repo with ONLY audio-hotplug files and their history
# Verify it worked
git log --oneline | Select-Object -First 10
ls

# Add new remote
git remote add origin git@github.com:LedFx/audio-hotplug.git

# Push to new repository
git push -u origin main
```

**Note**: If `git filter-repo` is not installed:
```powershell
pip install git-filter-repo
```

### Alternative Method (if filter-repo doesn't work)

```powershell
# Using git subtree split
cd C:\mine\development\ledfx\LedFx
git checkout audio-device-hotswap

# Create new branch with only audio-hotplug
git subtree split --prefix=audio-hotplug -b audio-hotplug-only

# Create new repo
cd C:\mine\development\ledfx\audio-hotplug-extraction
git init
git remote add origin git@github.com:LedFx/audio-hotplug.git

# Pull the subtree branch
git pull C:\mine\development\ledfx\LedFx audio-hotplug-only

# Push to GitHub
git branch -M main
git push -u origin main
```

## Phase 2: Set Up Repository

### Step 1: Verify Repository Contents

After pushing, verify the repository has:
- `src/audio_hotplug/` - Source code
- `tests/` - Test files
- `examples/` - Example scripts
- `pyproject.toml` - Build configuration
- `README.md` - Documentation
- `LICENSE` - GPL-3.0 license
- `TESTING.md` - Testing guide

### Step 2: Add GitHub Actions Workflows

The workflows are already prepared in `.github/workflows/` (see files created below)

### Step 3: Set Up PyPI Publishing

1. **Create PyPI account** (if you don't have one):
   - Go to https://pypi.org/account/register/
   - Verify email

2. **Create API token**:
   - Go to https://pypi.org/manage/account/token/
   - Create token named "audio-hotplug-ci"
   - Scope: "Entire account" or specific to audio-hotplug project
   - **Copy the token** (starts with `pypi-...`)

3. **Add token to GitHub Secrets**:
   - Go to repository Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `PYPI_API_TOKEN`
   - Value: Paste the token
   - Click "Add secret"

4. **Optional: TestPyPI token** (for testing):
   - Go to https://test.pypi.org/manage/account/token/
   - Create token named "audio-hotplug-test"
   - Add as `TEST_PYPI_API_TOKEN` in GitHub Secrets

## Phase 3: Test Publishing

### Step 1: Test Build Locally

```powershell
cd C:\mine\development\ledfx\audio-hotplug-extraction\temp-repo

# Install build tools
pip install build twine

# Build the package
python -m build

# This creates:
# - dist/audio_hotplug-0.1.0-py3-none-any.whl
# - dist/audio_hotplug-0.1.0.tar.gz

# Verify the package
python -m twine check dist/*
```

### Step 2: Test Publish to TestPyPI

```powershell
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Test install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ --no-deps audio-hotplug

# Test the installation
python -c "from audio_hotplug import create_monitor; print('Success!')"
```

### Step 3: Publish to Production PyPI

Once TestPyPI works:

```powershell
# Upload to production PyPI
python -m twine upload dist/*

# Or use GitHub Actions - just create a release tag:
git tag v0.1.0
git push origin v0.1.0
```

## Phase 4: Create Clean LedFx Integration PR

### Step 1: Create Fresh Branch from Main

```powershell
cd C:\mine\development\ledfx\LedFx

# Make sure main is up to date
git checkout main
git pull upstream main

# Create new clean branch
git checkout -b feat/audio-hotplug-pypi-integration
```

### Step 2: Update pyproject.toml

Replace workspace dependency with PyPI package:

```toml
# Remove workspace configuration
# [tool.uv.workspace]
# members = [
#     "audio-hotplug",
# ]

# [tool.uv.sources]
# audio-hotplug = { workspace = true }

# In dependencies, change:
dependencies = [
    # ... other deps ...
    "audio-hotplug>=0.1.0",  # From PyPI
]
```

### Step 3: Remove audio-hotplug Directory

```powershell
# Remove the workspace copy
Remove-Item -Recurse -Force audio-hotplug
```

### Step 4: Update Integration Code

The integration code in `ledfx/core.py` is already correct:

```python
from audio_hotplug import create_monitor

# In LedFx class __init__:
self._audio_monitor = create_monitor(
    on_devices_changed=self._on_audio_devices_changed
)
```

### Step 5: Update Documentation

Update `docs/apis/websocket.md` (already done in previous PR)

### Step 6: Update uv.lock

```powershell
# Regenerate lock file with PyPI dependency
uv lock --upgrade-package audio-hotplug
```

### Step 7: Test Locally

```powershell
# Install from PyPI
uv sync

# Run LedFx
uv run python -m ledfx --offline -vv

# Test audio device changes work
```

### Step 8: Create PR

```powershell
git add .
git commit -m "feat: Integrate audio-hotplug from PyPI

- Replace workspace dependency with PyPI package (audio-hotplug>=0.1.0)
- Remove audio-hotplug workspace directory
- Update uv.lock with PyPI dependency
- Audio device change monitoring now uses published package"

git push origin feat/audio-hotplug-pypi-integration

# Create PR on GitHub
```

This new PR should have **~10 files changed** instead of 203!

## Expected Timeline

- **Day 1**: Extract repository, set up CI/CD, test builds
- **Day 2**: Publish to TestPyPI, verify installation
- **Day 3**: Publish to PyPI, create clean LedFx PR
- **Week 1**: PR review and merge

## Troubleshooting

### Git filter-repo not found
```powershell
pip install git-filter-repo
```

### PyPI upload fails (username/password)
Use API token instead:
```powershell
python -m twine upload --username __token__ --password pypi-... dist/*
```

### Tests fail in CI
Check the GitHub Actions logs for platform-specific issues. Windows/macOS/Linux may behave differently.

### Import fails after PyPI install
Verify package name is `audio-hotplug` on PyPI but imports as `audio_hotplug` (underscore):
```python
import audio_hotplug  # Correct
# NOT: import audio-hotplug
```

## Next Steps After Migration

1. Add badges to README (build status, PyPI version, coverage)
2. Set up documentation on ReadTheDocs
3. Add changelog automation (release-drafter)
4. Consider adding dependabot for dependency updates
5. Set up semantic versioning for releases
