"""Consumer authority remains explicit around the pinned shared transaction."""

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_preserves_identity_gates_and_same_run_artifacts() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    job = workflow.split("\n  publish-release:\n", 1)[1]
    for required in (
        "needs: [ci-passed]",
        "github.repository == 'LedFx/audio-hotplug'",
        "github.event_name == 'push'",
        "startsWith(github.ref, 'refs/tags/v')",
        "needs.ci-passed.result == 'success'",
        "name: pypi",
        "queue: max",
        "cancel-in-progress: false",
        "name: python-package-distributions",
        "permission-contents: write",
        "permission-attestations: write",
    ):
        assert required in job
    assert "run-id:" not in job
    assert workflow.count("id-token: write") == 1
    pins = re.findall(
        r"uses: LedFx/release-ci/actions/release@([0-9a-f]{40}) # (v[0-9]+\.[0-9]+\.[0-9]+)\s*$",
        job,
        re.MULTILINE,
    )
    assert len(pins) == 3 and len(set(pins)) == 1
    assert job.count("uses: LedFx/release-ci/actions/release@") == 3
    assert job.count("project: release-tools") == 3
    assert (
        job.index("phase: prepare")
        < job.index("uses: actions/attest@")
        < job.index("phase: check-upload")
        < job.index("uses: pypa/gh-action-pypi-publish@")
        < job.index("phase: finalize")
    )
    assert "bundle-path" in job and "release-snapshot.json" in job
    assert "softprops" not in workflow and "--clobber" not in workflow


def test_project_metadata_keeps_pure_python_artifacts() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["project"]["name"] == "audio-hotplug"
    assert "cibuildwheel" not in config["tool"]
    assert "release-ci" not in config["tool"]
    assert not (ROOT / ".github/release-policy.json").exists()
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    assert "pyproject.toml" in workflow
    assert "sparse-checkout-cone-mode: false" in workflow
    assert "actions/plan@" not in workflow
    assert "policy:" not in workflow
