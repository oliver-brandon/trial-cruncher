"""Release validation checks before any remote publishing."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "release_publisher",
    Path(__file__).resolve().parents[1] / "scripts" / "publish_stable_release.py",
)
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


@pytest.mark.parametrize("malformed", ["wrong-id", "wrong-hash", "missing-full"])
def test_refuses_bad_feed_before_calling_github(tmp_path, monkeypatch, malformed):
    monkeypatch.chdir(tmp_path)
    for name in ("release-windows", "release-macos"):
        (tmp_path / name).mkdir()
    payload = b"synthetic package"
    directory = tmp_path / "release-windows"
    filename = "com.trialcruncher.app-0.1.0-stable-win-x64-full.nupkg"
    (directory / filename).write_bytes(payload)
    item = {
        "Version": "0.1.0",
        "Type": "Full",
        "FileName": filename,
        "PackageId": "wrong" if malformed == "wrong-id" else "com.trialcruncher.app",
        "Size": len(payload),
        "SHA256": "0" * 64 if malformed == "wrong-hash" else hashlib.sha256(payload).hexdigest(),
    }
    (directory / "releases.stable-win-x64.json").write_text(
        json.dumps({"Assets": [] if malformed == "missing-full" else [item]})
    )
    for key, value in {
        "RELEASE_VERSION": "0.1.0",
        "RELEASE_TAG": "v0.1.0",
        "GITHUB_REPOSITORY": "owner/repo",
        "INSTALLER_STEM": "Trial-Cruncher-v0.1.0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        publisher.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Remote release must not be accessed for invalid payloads"),
    )
    with pytest.raises(ValueError):
        publisher.main()


def test_previous_release_resolver_requires_valid_response(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "previous_stable",
        Path(__file__).resolve().parents[1] / "scripts" / "previous_stable_release.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CANDIDATE_VERSION", "1.2.0")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(module.subprocess, "check_output", lambda *args, **kwargs: "[]")
    module.main()
    assert capsys.readouterr().out.strip() == ""
    data = [[{"draft": False, "prerelease": False, "tag_name": "v1.1.0"}]]
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **kw: json.dumps(data))
    module.main()
    assert capsys.readouterr().out.strip() == "v1.1.0"
    monkeypatch.setenv("CANDIDATE_VERSION", "1.1.0")
    with pytest.raises(ValueError, match="newer"):
        module.main()


@pytest.mark.parametrize("mode", ["empty", "resumed", "published", "changed"])
def test_draft_resume_uploads_only_missing_assets_and_publishes(tmp_path, monkeypatch, mode):
    from types import SimpleNamespace

    monkeypatch.chdir(tmp_path)
    staged = {}
    for channel, folder, ext in (
        ("stable-win-x64", "release-windows", "exe"),
        ("stable-osx-arm64", "release-macos", "pkg"),
    ):
        directory = tmp_path / folder
        directory.mkdir()
        payload = (channel + " payload").encode()
        filename = f"com.trialcruncher.app-0.1.0-{channel}-full.nupkg"
        (directory / filename).write_bytes(payload)
        entry = {
            "Version": "0.1.0",
            "Type": "Full",
            "FileName": filename,
            "PackageId": "com.trialcruncher.app",
            "Size": len(payload),
            "SHA256": hashlib.sha256(payload).hexdigest(),
        }
        (directory / f"releases.{channel}.json").write_text(json.dumps({"Assets": [entry]}))
        (directory / f"candidate-Setup.{ext}").write_bytes(b"installer")
        (directory / f"candidate-{channel}-Portable.zip").write_bytes(b"portable")
    for key, value in {
        "RELEASE_VERSION": "0.1.0",
        "RELEASE_TAG": "v0.1.0",
        "GITHUB_REPOSITORY": "owner/repo",
        "INSTALLER_STEM": "Trial-Cruncher-v0.1.0",
    }.items():
        monkeypatch.setenv(key, value)
    first = tmp_path / "release-windows" / "releases.stable-win-x64.json"
    if mode in ("resumed", "changed"):
        staged[first.name] = {
            "name": first.name,
            "state": "uploaded",
            "size": first.stat().st_size,
            "digest": "sha256:" + (publisher.digest(first) if mode == "resumed" else "0" * 64),
        }
    monkeypatch.setattr(
        publisher.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps({"isDraft": mode != "published"})
        ),
    )

    def fake_gh(*args):
        if args[:2] == ("release", "view"):
            return json.dumps({"assets": list(staged.values())})
        if args[:2] == ("release", "upload"):
            for name in args[5:]:
                path = Path(name)
                staged[path.name] = {
                    "name": path.name,
                    "state": "uploaded",
                    "size": path.stat().st_size,
                    "digest": "sha256:" + publisher.digest(path),
                }
        elif args[:2] == ("release", "edit"):
            assert len(staged) == 8
        return ""

    monkeypatch.setattr(publisher, "gh", fake_gh)
    if mode == "published":
        with pytest.raises(ValueError, match="published release"):
            publisher.main()
        assert not staged
    elif mode == "changed":
        with pytest.raises(ValueError, match="Existing draft asset differs"):
            publisher.main()
        assert len(staged) == 1
    else:
        publisher.main()
        assert len(staged) == 8


def test_existing_stable_feed_requires_delta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / "release-windows"
    folder.mkdir()
    entry = {
        "Version": "0.2.0",
        "Type": "Full",
        "PackageId": "com.trialcruncher.app",
    }
    old = {"Version": "0.1.0", "Type": "Full", "PackageId": "com.trialcruncher.app"}
    (folder / "releases.stable-win-x64.json").write_text(json.dumps({"Assets": [entry, old]}))
    for key, value in {
        "RELEASE_VERSION": "0.2.0",
        "RELEASE_TAG": "v0.2.0",
        "GITHUB_REPOSITORY": "owner/repo",
        "INSTALLER_STEM": "Trial-Cruncher-v0.2.0",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PREVIOUS_TAG", "v0.1.0")
    with pytest.raises(ValueError, match="delta"):
        publisher.main()
