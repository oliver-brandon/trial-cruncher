"""Candidate provenance and immutable payload checks."""

import hashlib
import io
import runpy
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

mod = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/validate_release_candidate.py")
)
validate, download = mod["validate"], mod["download"]
SHA = "a" * 40


def candidate():
    run = {
        "id": 4,
        "repository": {"full_name": "org/repo"},
        "head_repository": {"full_name": "org/repo"},
        "path": ".github/workflows/build-desktop-apps.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
    }
    jobs = []
    for system in ("ubuntu-latest", "windows-latest", "macos-latest"):
        for version in ("3.12", "3.14"):
            jobs.append(
                {
                    "name": f"Full CI / Full tests ({system}, {version})",
                    "conclusion": "success",
                    "steps": [
                        {"name": "Test", "conclusion": "success"},
                        {"name": "Lint", "conclusion": "success"},
                        {"name": "Check formatting", "conclusion": "success"},
                    ],
                }
            )
    for name, steps in mod["PLATFORMS"].items():
        jobs.append(
            {
                "name": name,
                "conclusion": "success",
                "started_at": "2026-01-01T00:00:00Z",
                "completed_at": "2026-01-01T00:10:00Z",
                "steps": [{"name": step, "conclusion": "success"} for step in steps],
            }
        )
    jobs.append({"name": "Publish verified stable release", "conclusion": "skipped"})
    artifacts = [
        {
            "name": name,
            "id": i,
            "digest": "sha256:" + "b" * 64,
            "expired": False,
            "created_at": "2026-01-01T00:05:00Z",
            "workflow_run": {"id": 4, "head_sha": SHA},
        }
        for i, name in enumerate(mod["ARTIFACTS"], 1)
    ]
    return run, jobs, artifacts


def test_valid_candidate():
    run, jobs, artifacts = candidate()
    assert validate(run, jobs, artifacts, "org/repo", SHA)["stable-windows-release"]["id"] == 1


@pytest.mark.parametrize(
    "mutation",
    ["sha", "branch", "wrong_attempt", "ci", "smoke", "publish", "expired", "digest", "duplicate"],
)
def test_reject_bad_candidate(mutation):
    run, jobs, artifacts = candidate()
    if mutation == "sha":
        run["head_sha"] = "c" * 40
    if mutation == "branch":
        run["head_branch"] = "other"
    if mutation == "wrong_attempt":
        artifacts[0]["created_at"] = "2025-01-01T00:00:00Z"
    if mutation == "ci":
        jobs.pop(1)
    if mutation == "smoke":
        jobs[-3]["steps"][0]["conclusion"] = "failure"
    if mutation == "publish":
        jobs[-1]["conclusion"] = "success"
    if mutation == "expired":
        artifacts[0]["expired"] = True
    if mutation == "digest":
        artifacts[0]["digest"] = ""
    if mutation == "duplicate":
        artifacts.append(deepcopy(artifacts[0]))
    with pytest.raises(ValueError):
        validate(run, jobs, artifacts, "org/repo", SHA)


@pytest.mark.parametrize("member", ["payload.exe", "../escape"])
def test_archive_hash_and_path_are_checked(monkeypatch, tmp_path, member):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(member, b"contents")
    blob = data.getvalue()
    import subprocess

    def api_download(args, stdout, check):
        stdout.write(blob)

    monkeypatch.setattr(subprocess, "run", api_download)
    record = {
        "stable-windows-release": {"id": 1, "digest": "sha256:" + hashlib.sha256(blob).hexdigest()}
    }
    if member.startswith(".."):
        with pytest.raises(ValueError, match="path"):
            download("org/repo", record, tmp_path)
    else:
        download("org/repo", record, tmp_path)
        assert (tmp_path / "release-windows" / member).read_bytes() == b"contents"


def test_current_publishing_run_allows_in_progress_publish_job():
    run, jobs, artifacts = candidate()
    run.update(status="in_progress", conclusion=None, event="push", head_branch="v0.2.0")
    jobs[-1]["conclusion"] = None
    assert validate(run, jobs, artifacts, "org/repo", SHA, current_run=True, release_tag="v0.2.0")
    with pytest.raises(ValueError):
        validate(run, jobs, artifacts, "org/repo", SHA)


def test_retried_run_uses_each_carried_forward_successful_job_time():
    run, jobs, artifacts = candidate()
    run["run_attempt"] = 3
    jobs[-2]["started_at"] = "2026-01-02T00:00:00Z"
    jobs[-2]["completed_at"] = "2026-01-02T00:10:00Z"
    artifacts[1]["created_at"] = "2026-01-02T00:05:00Z"
    assert validate(run, jobs, artifacts, "org/repo", SHA)
    artifacts[1]["created_at"] = "2026-01-01T00:05:00Z"
    with pytest.raises(ValueError, match="job attempt"):
        validate(run, jobs, artifacts, "org/repo", SHA)


def test_candidate_markers_bind_previous_release_and_platform(tmp_path):
    import json
    import subprocess
    import sys

    from trial_cruncher.version import __version__

    script = Path(__file__).resolve().parents[1] / "scripts/validate_release_candidate.py"
    base = [sys.executable, str(script), "--sha", SHA, "--version", __version__]
    for platform in ("windows", "macos"):
        folder = tmp_path / ("release-" + platform)
        folder.mkdir()
        subprocess.run(
            [
                *base,
                "--write-marker",
                str(folder / "tested-candidate.json"),
                "--previous-tag",
                "v0.1.0",
                "--platform",
                platform,
            ],
            check=True,
        )
        assert json.loads((folder / "tested-candidate.json").read_text())["commit"] == SHA
    mod["verify_markers"](tmp_path, SHA, __version__, "v0.1.0")
    with pytest.raises(ValueError, match="different release inputs"):
        mod["verify_markers"](tmp_path, SHA, __version__, "")
