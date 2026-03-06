# Audio-Hotplug Migration Checklist

Use this checklist to track your progress through the migration.

## Phase 1: Repository Extraction ⏱️ 10 minutes

- [ ] Install git-filter-repo: `pip install git-filter-repo`
- [ ] Create extraction directory: `C:\mine\development\ledfx\audio-hotplug-extraction`
- [ ] Clone LedFx repository locally
- [ ] Checkout audio-device-hotswap branch
- [ ] Run git filter-repo to extract audio-hotplug/
- [ ] Verify extraction: check that only audio-hotplug files remain
- [ ] Review git log to confirm history preserved

## Phase 2: GitHub Repository Setup ⏱️ 5 minutes

- [ ] Create GitHub repository at github.com/LedFx/audio-hotplug
- [ ] Set repository to Public
- [ ] Add description: "Cross-platform audio device hotplug detection library"
- [ ] Do NOT initialize with README (we have one)
- [ ] Add remote to extracted repo
- [ ] Push to GitHub: `git push -u origin main`
- [ ] Verify files visible on GitHub

## Phase 3: CI/CD Setup ⏱️ 5 minutes

- [ ] Copy `.github/workflows/` to extracted repo
- [ ] Copy `.pre-commit-config.yaml` to extracted repo
- [ ] Copy `MANIFEST.in` to extracted repo
- [ ] Copy `CHANGELOG.md` to extracted repo
- [ ] Commit: "ci: Add GitHub Actions workflows and configuration"
- [ ] Push to GitHub
- [ ] Verify workflows appear in Actions tab

## Phase 4: PyPI Account Setup ⏱️ 10 minutes

### PyPI Production
- [ ] Create account at https://pypi.org/account/register/
- [ ] Verify email address
- [ ] Go to https://pypi.org/manage/account/token/
- [ ] Create API token named "audio-hotplug-ci"
- [ ] Copy token (starts with `pypi-`)
- [ ] Store token securely

### TestPyPI (Optional but Recommended)
- [ ] Create account at https://test.pypi.org/account/register/
- [ ] Verify email address
- [ ] Create API token named "audio-hotplug-test-ci"
- [ ] Copy test token
- [ ] Store test token securely

### GitHub Secrets
- [ ] Go to repository Settings → Secrets and variables → Actions
- [ ] Add `PYPI_API_TOKEN` secret with production token
- [ ] Add `TEST_PYPI_API_TOKEN` secret with test token (if using)
- [ ] Verify secrets are saved

## Phase 5: Local Build Test ⏱️ 5 minutes

- [ ] Install build tools: `pip install build twine`
- [ ] Run build: `python -m build`
- [ ] Verify dist/ directory created
- [ ] Check package: `python -m twine check dist/*`
- [ ] Verify both checks PASSED
- [ ] Review contents: `tar -tzf dist/audio_hotplug-0.1.0.tar.gz`

## Phase 6: TestPyPI Publishing ⏱️ 5 minutes

- [ ] Upload to TestPyPI: `python -m twine upload --repository testpypi dist/*`
- [ ] Enter username: `__token__`
- [ ] Paste TEST_PYPI_API_TOKEN
- [ ] Verify successful upload
- [ ] Create test environment: `python -m venv test_env`
- [ ] Activate: `test_env\Scripts\activate`
- [ ] Install from TestPyPI: `pip install --index-url https://test.pypi.org/simple/ --no-deps audio-hotplug`
- [ ] Test import: `python -c "from audio_hotplug import create_monitor; print('✓')"`
- [ ] Deactivate and cleanup: `deactivate`

## Phase 7: PyPI Production Publishing ⏱️ 3 minutes

### Option A: Via GitHub Release (Recommended)
- [ ] Create release tag: `git tag v0.1.0`
- [ ] Push tag: `git push origin v0.1.0`
- [ ] Watch GitHub Actions run
- [ ] Verify build and publish steps succeed
- [ ] Check package at https://pypi.org/project/audio-hotplug/

### Option B: Manual Upload
- [ ] Upload: `python -m twine upload dist/*`
- [ ] Enter username: `__token__`
- [ ] Paste PYPI_API_TOKEN
- [ ] Verify upload successful
- [ ] Check https://pypi.org/project/audio-hotplug/

## Phase 8: Verify Publication ⏱️ 3 minutes

- [ ] Open https://pypi.org/project/audio-hotplug/
- [ ] Verify version 0.1.0 shows
- [ ] Check that README displays correctly
- [ ] Test install in fresh environment: `pip install audio-hotplug`
- [ ] Test import: `python -c "from audio_hotplug import create_monitor; print('✓')"`
- [ ] Test example: `python examples/monitor_print.py`

## Phase 9: Create Clean LedFx PR ⏱️ 15 minutes

### Setup
- [ ] Navigate to LedFx directory
- [ ] Checkout main: `git checkout main`
- [ ] Pull latest: `git pull upstream main`
- [ ] Create branch: `git checkout -b feat/audio-hotplug-pypi-integration`

### Edit pyproject.toml
- [ ] Add to dependencies: `"audio-hotplug>=0.1.0",`
- [ ] Remove `[tool.uv.workspace]` section
- [ ] Remove workspace members array
- [ ] Remove `[tool.uv.sources]` section
- [ ] Save file

### Update Dependencies
- [ ] Remove directory: `Remove-Item -Recurse -Force audio-hotplug`
- [ ] Update lock: `uv lock --upgrade-package audio-hotplug`
- [ ] Sync: `uv sync`
- [ ] Verify install: `uv run python -c "import audio_hotplug; print('✓')"`

### Test Integration
- [ ] Run LedFx: `uv run python -m ledfx --offline -vv`
- [ ] Verify LedFx starts without errors
- [ ] Check logs for audio device monitoring messages
- [ ] Plug/unplug audio device (or use virtual device)
- [ ] Verify callback fires and websocket event sent
- [ ] Stop LedFx gracefully

### Commit and Push
- [ ] Stage changes: `git add .`
- [ ] Commit with message (see below)
- [ ] Push: `git push origin feat/audio-hotplug-pypi-integration`
- [ ] Verify ~10 files changed (not 203!)

### Commit Message Template:
```
feat: Integrate audio-hotplug from PyPI

- Replace workspace dependency with PyPI package (audio-hotplug>=0.1.0)
- Remove audio-hotplug workspace directory
- Update uv.lock with PyPI dependency
- Audio device monitoring now uses published package

Resolves #1725
```

### Create PR
- [ ] Go to GitHub and create pull request
- [ ] Title: "feat: Integrate audio-hotplug from PyPI"
- [ ] Add description explaining the change
- [ ] Mention the package is now published
- [ ] Link to PyPI: https://pypi.org/project/audio-hotplug/
- [ ] Request review from maintainers

## Phase 10: PR Review and Merge ⏱️ Varies

- [ ] Address any review comments
- [ ] Ensure all CI checks pass
- [ ] Verify no formatting changes introduced
- [ ] Wait for maintainer approval
- [ ] Merge PR when approved
- [ ] Close old PR #1725 with reference to new PR
- [ ] Celebrate! 🎉

## Post-Merge Tasks (Optional)

### audio-hotplug Repository
- [ ] Add badges to README (build status, PyPI version, coverage)
- [ ] Enable pre-commit.ci bot
- [ ] Set up Read the Docs (if desired)
- [ ] Add contributing guidelines
- [ ] Set up issue templates
- [ ] Configure branch protection rules

### LedFx Repository
- [ ] Update documentation to reference audio-hotplug
- [ ] Verify audio device monitoring works in production
- [ ] Monitor for any issues
- [ ] Consider blog post or changelog entry

## Rollback Plan (If Needed)

If something goes wrong, you can rollback:

### LedFx Rollback
- [ ] Revert PR merge commit
- [ ] Or restore audio-hotplug to workspace
- [ ] Update pyproject.toml back to workspace dependency

### PyPI Rollback
- [ ] Cannot unpublish (PyPI policy)
- [ ] Can publish fixed version (0.1.1)
- [ ] Can yank version (marks as unavailable)

## Notes and Observations

Use this space to track any issues or notes:

```
Date: ___________
Issue: ___________________________________________
Resolution: ______________________________________


Date: ___________
Issue: ___________________________________________
Resolution: ______________________________________


```

## Completion

- [ ] All phases complete
- [ ] audio-hotplug published to PyPI
- [ ] LedFx using PyPI package
- [ ] PR merged
- [ ] Documentation updated

**Completion Date**: ___________

**Total Time Taken**: ___________ (Target: ~60 minutes)

---

## Quick Reference

- **PyPI Package**: https://pypi.org/project/audio-hotplug/
- **GitHub Repo**: https://github.com/LedFx/audio-hotplug
- **LedFx PR**: (link when created)
- **Documentation**: MIGRATION_GUIDE.md, QUICK_START.md

## Help

Stuck? Check:
1. MIGRATION_GUIDE.md - Detailed explanations
2. QUICK_START.md - Fast-track steps
3. GitHub Issues - Known problems
4. Discord - Community help
