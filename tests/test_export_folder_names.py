"""Portable naming and exclusive creation for user-named exports."""

import pytest

from trial_cruncher.exporters import export_import_results, validate_export_folder_name
from trial_cruncher.processing import import_medpc_file


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../escape", "C:/test", "a\\b", "x.", "NUL", " hi", "COM¹.log", "CONIN$"],
)
def test_rejects_nonportable_folder_names(name):
    with pytest.raises(ValueError):
        validate_export_folder_name(name)


def test_named_export_never_overwrites_or_touches_existing(phase_input, tmp_path):
    source = phase_input()
    result = import_medpc_file(source, "Reversal")
    parent = tmp_path / "output"
    parent.mkdir()
    existing = parent / "20261119-trial-cruncher-export-study"
    existing.mkdir()
    sentinel = existing / "sentinel"
    sentinel.write_text("untouched")
    name = existing.name
    first = export_import_results({source: result}, [source], parent, folder_name=name)
    second = export_import_results({source: result}, [source], parent, folder_name=name)
    assert first.name == f"{name}-2"
    assert second.name == f"{name}-3"
    assert sentinel.read_text() == "untouched"
    assert source.exists()


def test_unnamed_export_has_dated_unsaved_fallback(phase_input, tmp_path):
    from datetime import datetime

    source = phase_input()
    result = import_medpc_file(source, "Reversal")
    output = export_import_results({source: result}, [source], tmp_path)
    assert output.name == f"{datetime.now():%Y%m%d}-trial-cruncher-export-unsaved"


def test_project_default_name_and_portable_long_unicode(app):
    from pathlib import Path

    from trial_cruncher.gui.window import MainWindow

    window = MainWindow()
    try:
        window._project_path = Path("example.tcproj.json")
        assert window.default_export_folder_name().endswith("-trial-cruncher-export-example")
        window._project_path = Path("試" * 100 + ".tcproj.json")
        name = window.default_export_folder_name()
        assert len(name.encode("utf-8")) <= 255
        assert validate_export_folder_name(name) == name
    finally:
        window.close()


def test_existing_file_and_concurrent_export_names(tmp_path, phase_input):
    from concurrent.futures import ThreadPoolExecutor

    path = phase_input()
    results = {path: import_medpc_file(path, "Acquisition")}
    original = path.read_bytes()

    def export():
        return export_import_results(results, [path], path.parent, folder_name=path.name)

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(export) for _ in range(2)]
        destinations = {job.result() for job in jobs}
    assert {p.name for p in destinations} == {path.name + "-2", path.name + "-3"}
    assert all((p / "manifest.json").is_file() for p in destinations)
    assert path.read_bytes() == original
