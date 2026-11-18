import os

import pytest

from trial_cruncher.discovery import discover_files, normalize_extensions


def test_recursive_discovery_is_sorted_unique_and_read_only(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    first = tmp_path / "a.MAT"
    second = nested / "b.txt"
    first.write_bytes(b"synthetic placeholder, not a MATLAB schema")
    second.write_text("synthetic")
    (tmp_path / "ignored.csv").write_text("ignore me")
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (first, second)}
    result = discover_files([tmp_path, first, nested])
    assert result.files == (first, second)
    assert result.issues == ()
    assert before == {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (first, second)
    }


def test_nonrecursive_custom_extensions(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    selected = tmp_path / "one.CSV"
    selected.touch()
    (nested / "two.csv").touch()
    assert discover_files([tmp_path], extensions=["CSV"], recursive=False).files == (selected,)


def test_missing_and_unsupported_inputs_are_reported(tmp_path):
    unknown = tmp_path / "unknown.bin"
    unknown.touch()
    result = discover_files([unknown, tmp_path / "missing.mat"])
    assert not result.files
    assert len(result.issues) == 2


def test_directory_access_error_retains_other_files(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    good = tmp_path / "good.mat"
    good.touch()
    original = os.scandir

    def scandir(path):
        if path == blocked:
            raise PermissionError("Synthetic permission failure")
        return original(path)

    monkeypatch.setattr(os, "scandir", scandir)
    result = discover_files([tmp_path])
    assert result.files == (good,)
    assert len(result.issues) == 1
    assert result.issues[0].path == blocked


def test_directory_symlink_cycle_is_reported(tmp_path):
    link = tmp_path / "cycle"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks unavailable on this platform")
    result = discover_files([tmp_path])
    assert not result.files
    assert len(result.issues) == 1
    assert "linked folder" in result.issues[0].message


@pytest.mark.parametrize("extensions", [[], [""], ["*mat"], ["a/b"], ["."]])
def test_invalid_extensions(extensions):
    with pytest.raises(ValueError, match="extension"):
        normalize_extensions(extensions)


def test_extension_normalization():
    assert normalize_extensions(["MAT", " .txt ", ".mat"]) == {".mat", ".txt"}


def test_file_symlinks_are_filtered_by_target_extension(tmp_path):
    target = tmp_path / "source.med"
    target.write_text("synthetic")
    folder = tmp_path / "links"
    folder.mkdir()
    link = folder / "different.bin"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("File symlinks unavailable on this platform")
    result = discover_files([folder])
    assert result.files == (target,)
    assert not result.issues
