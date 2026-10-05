"""Consumer authority remains explicit around the pinned shared transaction."""

import os
import re
import subprocess
import sys
import textwrap
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
        r"uses: LedFx/release-ci/actions/release@([0-9a-f]{40})(?:[ \t]+#.*)?[ \t]*$",
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


def test_upload_sidecars_leave_frozen_inputs_unchanged(tmp_path: Path) -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text()
    match = re.search(
        r"(?m)^      - name: Stage verified distributions for PyPI\n"
        r"(?:(?:^        .*\n)|(?:^\n))*?^        run: \|\n"
        r"((?:^          .*\n|^\n)+)",
        workflow,
    )
    assert match is not None, "The uploader needs a separate verified input copy"
    stage = workflow.split("      - name: Stage verified distributions for PyPI\n", 1)[
        1
    ].split("\n      - ", 1)[0]
    assert "if: steps.upload.outputs.pypi_upload == 'true'" in stage
    assert "working-directory: ${{ github.workspace }}" in stage
    assert workflow.index("phase: check-upload") < workflow.index(
        "Stage verified distributions for PyPI"
    )
    uploader = workflow.split("uses: pypa/gh-action-pypi-publish@", 1)[1].split(
        "\n      - ", 1
    )[0]
    assert "packages-dir: pypi-dist/" in uploader
    script = textwrap.dedent(match.group(1))
    original = tmp_path / "dist"
    original.mkdir()
    frozen = {
        "example-1.0-py3-none-any.whl": b"tested wheel",
        "example-1.0.tar.gz": b"tested sdist",
    }
    for name, data in frozen.items():
        (original / name).write_bytes(data)
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_WORKSPACE": str(tmp_path)},
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    staging = tmp_path / "pypi-dist"
    assert {p.name: p.read_bytes() for p in staging.iterdir()} == frozen
    for name in frozen:
        (staging / (name + ".publish.attestation")).write_bytes(
            b"generated PyPI sidecar"
        )
    assert {p.name: p.read_bytes() for p in original.iterdir()} == frozen
    before_retry = {p.name: p.read_bytes() for p in staging.iterdir()}
    retry = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_WORKSPACE": str(tmp_path)},
        capture_output=True,
        check=False,
    )
    assert retry.returncode != 0
    assert {p.name: p.read_bytes() for p in staging.iterdir()} == before_retry
    assert {p.name: p.read_bytes() for p in original.iterdir()} == frozen
