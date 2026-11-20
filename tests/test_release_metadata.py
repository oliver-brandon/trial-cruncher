"""Stable package identities are shared by the build tools and installed app."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from trial_cruncher import __version__
from trial_cruncher.version import UPDATE_PACKAGE_ID, update_target

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("system", "machine", "runtime"),
    [("Windows", "AMD64", "win-x64"), ("Darwin", "arm64", "osx-arm64")],
)
def test_metadata_matches_release_target(monkeypatch, system, machine, runtime):
    monkeypatch.setenv("TRIAL_CRUNCHER_UPDATE_SYSTEM", system)
    monkeypatch.setenv("TRIAL_CRUNCHER_UPDATE_MACHINE", machine)
    tool = [sys.executable, str(ROOT / "scripts/version_metadata.py")]
    subprocess.run([*tool, "--check"], check=True)
    data = json.loads(subprocess.check_output(tool))
    assert data["version"] == __version__
    assert data["update_release_tag"] == f"v{__version__}"
    assert data["update_package_id"] == data["bundle_identifier"] == UPDATE_PACKAGE_ID
    assert data["update_channel"] == f"stable-{runtime}"
    assert data["update_runtime"] == runtime


@pytest.mark.parametrize("system,machine", [("Linux", "x86_64"), ("Darwin", "x86_64")])
def test_source_only_targets_have_no_release_channel(system, machine):
    with pytest.raises(ValueError, match="No Trial Cruncher installer target"):
        update_target(system, machine)
