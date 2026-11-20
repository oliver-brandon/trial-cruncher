"""Synthetic security tool output for the release runner identity preflight."""

import runpy
from pathlib import Path

import pytest

verify = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/verify_macos_identities.py")
)["verify"]


@pytest.mark.parametrize("case", ["valid", "different-name", "missing-installer", "wrong-team"])
def test_verify_identities(monkeypatch, tmp_path, case):
    import subprocess

    app = "Developer ID Application: Example (TEAM)"
    installer = "Developer ID Installer: Example (TEAM)"
    output = f'  1) {"A" * 40} "{app}"\n'
    if case != "missing-installer":
        output += f'  2) {"B" * 40} "{installer}"\n'
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: output)
    monkeypatch.setenv("APPLE_TEAM_ID", "OTHER" if case == "wrong-team" else "TEAM")
    monkeypatch.setenv(
        "MACOS_DEVELOPER_ID_APPLICATION", "incorrect" if case == "different-name" else app
    )
    monkeypatch.setenv("MACOS_DEVELOPER_ID_INSTALLER", installer)
    env = tmp_path / "env"
    monkeypatch.setenv("GITHUB_ENV", str(env))
    if case == "valid":
        verify("temporary.keychain-db")
        assert env.read_text().splitlines() == [
            "VERIFIED_APPLICATION_IDENTITY=" + "A" * 40,
            "VERIFIED_INSTALLER_IDENTITY=" + installer,
        ]
    else:
        with pytest.raises(SystemExit, match="valid"):
            verify("temporary.keychain-db")
