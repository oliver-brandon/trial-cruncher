"""Synthetic project persistence, source freshness, and failure recovery."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from trial_cruncher import excel, exporters, projects, source_tracking
from trial_cruncher.exporters import export_import_results
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.projects import analysis_configuration, load_project, save_project
from trial_cruncher.source_tracking import SourcesChangedError, check_sources, source_sha256


def save(path, sources=(), phases=None, hashes=None, expected=None):
    return save_project(
        path,
        sources,
        phases or {},
        hashes or {},
        extensions=(".txt", ".med"),
        recursive=True,
        expected_project_sha256=expected,
    )


def test_project_round_trip_setup_hashes_and_duplicate_filenames(phase_input, tmp_path):
    a = phase_input(name="a/same.txt")
    b = phase_input(name="b/same.txt")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (a, b)}
    result = save(tmp_path / "study.tcproj.json", [a, b], {a: "Reversal 2 μ", b: "Acquisition"})
    loaded = load_project(result.path)
    assert loaded.project == result.project
    assert loaded.file_sha256 == result.file_sha256 == source_sha256(result.path)
    assert all(c.status == "unchanged" for c in loaded.checks)
    assert {s.path: s.phase for s in loaded.project.sources} == {
        a: "Reversal 2 μ",
        b: "Acquisition",
    }
    assert {s.path: s.sha256 for s in loaded.project.sources} == {
        p: source_sha256(p) for p in (a, b)
    }
    data = json.loads(result.path.read_text())
    assert data["analysis_configuration"] == analysis_configuration()
    assert data["discovery"] == {"extensions": [".med", ".txt"], "recursive": True}
    assert set(data["sources"][0]) == {"path", "phase", "sha256", "analysis_metadata"}
    assert not any(key in data for key in ("results", "metrics", "source_text", "events"))
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (a, b)}


def test_changed_missing_and_unknown_sources_are_retained(phase_input, tmp_path):
    a = phase_input()
    missing = tmp_path / "missing.txt"
    initial = save(tmp_path / "first.tcproj.json", [a, missing], {a: "Reversal"})
    baseline = {s.path: s.sha256 for s in initial.project.sources}
    original_stat = a.stat()
    # Same file length and restored mtime must not fool content verification.
    a.write_text(a.read_text().replace("Subject: 0007", "Subject: 0008"))
    os.utime(a, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    loaded = load_project(initial.path)
    assert {c.path: c.status for c in loaded.checks} == {a: "changed", missing: "missing"}
    again = save(initial.path, [a, missing], {a: "Reversal"}, baseline, initial.file_sha256)
    assert {s.path: s.sha256 for s in again.project.sources} == baseline
    assert next(c for c in again.checks if c.path == a).status == "changed"
    missing.write_text("now present")
    assert (
        next(c for c in load_project(initial.path).checks if c.path == missing).status
        == "unverified"
    )
    refreshed = import_medpc_file(a, "Reversal")
    updated = save(
        initial.path,
        [a, missing],
        {a: "Reversal"},
        {a: refreshed.raw["source_sha256"], missing: None},
        again.file_sha256,
    )
    assert all(c.status == "unchanged" for c in load_project(updated.path).checks)


def test_mtime_only_changes_do_not_invalidate(phase_input):
    p = phase_input()
    digest = source_sha256(p)
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert check_sources({p: digest})[0].status == "unchanged"


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "config",
        "unknown_field",
        "bad_hash",
        "relative",
        "duplicate_path",
        "phase_type",
        "phase_whitespace",
        "recursive_type",
        "extensions",
        "self_source",
    ],
)
def test_malformed_projects_rejected_before_source_checks(
    phase_input, tmp_path, monkeypatch, damage
):
    p = phase_input()
    saved = save(tmp_path / "bad.tcproj.json", [p])
    data = json.loads(saved.path.read_text())
    if damage == "version":
        data["schema_version"] = "future"
    if damage == "config":
        data["analysis_configuration"]["normalizer_version"] = "old"
    if damage == "unknown_field":
        data["cached_results"] = {}
    if damage == "bad_hash":
        data["sources"][0]["sha256"] = "bad"
    if damage == "relative":
        data["sources"][0]["path"] = "data/input.txt"
    if damage == "duplicate_path":
        data["sources"].append(data["sources"][0].copy())
    if damage == "phase_type":
        data["sources"][0]["phase"] = {"label": "Reversal"}
    if damage == "phase_whitespace":
        data["sources"][0]["phase"] = " Reversal "
    if damage == "recursive_type":
        data["discovery"]["recursive"] = "true"
    if damage == "extensions":
        data["discovery"]["extensions"] = ["*.txt"]
    if damage == "self_source":
        data["sources"][0]["path"] = str(saved.path)
    saved.path.write_text(json.dumps(data))
    monkeypatch.setattr(
        projects, "check_sources", lambda *_: pytest.fail("Malformed project touched sources")
    )
    with pytest.raises(ValueError):
        load_project(saved.path)


@pytest.mark.parametrize("content", [b"{", b"\xff", b'{"format":"a","format":"b"}'])
def test_bad_json_and_duplicate_keys(tmp_path, content):
    p = tmp_path / "bad.tcproj.json"
    p.write_bytes(content)
    with pytest.raises(ValueError):
        load_project(p)


def test_project_size_limit(tmp_path, monkeypatch):
    p = tmp_path / "large.tcproj.json"
    p.write_text(" " * 100)
    monkeypatch.setattr(projects, "MAX_PROJECT_BYTES", 50)
    with pytest.raises(ValueError, match="16 MiB"):
        load_project(p)


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_atomic_save_failure_keeps_previous_project(phase_input, tmp_path, monkeypatch, failure):
    p = phase_input()
    saved = save(tmp_path / "safe.tcproj.json", [p], {p: "Acquisition"})
    original = saved.path.read_bytes()

    def fail(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(projects.os, failure, fail)
    with pytest.raises(OSError, match="Synthetic"):
        save(saved.path, [p], {p: "Reversal"}, expected=saved.file_sha256)
    assert saved.path.read_bytes() == original
    assert not list(tmp_path.glob(".*.tmp")) and not list(tmp_path.glob(".*.lock"))


def test_save_refuses_external_edit_and_unrelated_destinations(phase_input, tmp_path):
    p = phase_input()
    saved = save(tmp_path / "safe.tcproj.json", [p])
    saved.path.write_text(saved.path.read_text() + " ")
    changed = saved.path.read_bytes()
    with pytest.raises(ValueError, match="outside"):
        save(saved.path, [p], expected=saved.file_sha256)
    assert saved.path.read_bytes() == changed
    arbitrary = tmp_path / "notes.tcproj.json"
    arbitrary.write_text("My original notes")
    with pytest.raises(FileExistsError):
        save(arbitrary, [p])
    with pytest.raises(ValueError):
        save(arbitrary, [p], expected=source_sha256(arbitrary))
    assert arbitrary.read_text() == "My original notes"


def test_source_paths_links_and_deleted_source_protection(tmp_path):
    p = tmp_path / "input.tcproj.json"
    p.write_bytes(b"original raw bytes")
    with pytest.raises(ValueError, match="source"):
        save(p, [p])
    alias = tmp_path / "alias.tcproj.json"
    alias.hardlink_to(p)
    with pytest.raises(ValueError, match="alias"):
        save(alias, [p])
    link = tmp_path / "link.tcproj.json"
    link.symlink_to(p)
    with pytest.raises(ValueError, match="symbolic"):
        save(link, [p])
    missing = tmp_path / "missing.tcproj.json"
    dangling = tmp_path / "dangling.tcproj.json"
    dangling.symlink_to(missing)
    with pytest.raises(ValueError, match="symbolic"):
        save(dangling, [])
    with pytest.raises(ValueError, match="source"):
        save(missing, [missing])
    assert p.read_bytes() == alias.read_bytes() == b"original raw bytes"
    assert dangling.is_symlink() and not missing.exists()


def test_concurrent_project_updates_never_silently_replace_each_other(phase_input, tmp_path):
    p = phase_input()
    saved = save(tmp_path / "safe.tcproj.json", [p])
    barrier = Barrier(2)

    def update(label):
        barrier.wait(timeout=5)
        try:
            return save(saved.path, [p], {p: label}, expected=saved.file_sha256)
        except (FileExistsError, ValueError):
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(update, ["Acquisition", "Reversal"]))
    winners = [v for v in outcomes if v is not None]
    assert len(winners) == 1
    assert load_project(saved.path).project == winners[0].project


def test_unreadable_and_nonregular_source_checks(tmp_path, monkeypatch):
    folder = tmp_path / "folder"
    folder.mkdir()
    assert check_sources({folder: None})[0].status == "unreadable"

    def denied(path):
        raise PermissionError("Synthetic permission denial")

    monkeypatch.setattr(source_tracking, "source_sha256", denied)
    assert check_sources({tmp_path / "input": None})[0].status == "unreadable"


@pytest.mark.parametrize("changed_during_read", [False, True])
def test_hash_compares_descriptor_ctime_only_to_itself(tmp_path, monkeypatch, changed_during_read):
    path = tmp_path / "source.txt"
    content = b"unchanged synthetic recording"
    path.write_bytes(content)
    info = path.stat()
    # Windows can report birth time through stat(path) and change time through fstat(fd).
    descriptor_ctime = info.st_ctime_ns + 100
    times = iter((descriptor_ctime, descriptor_ctime + (100 if changed_during_read else 0)))

    def fstat(fd):
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=next(times),
        )

    monkeypatch.setattr(source_tracking, "fstat", fstat)
    if changed_during_read:
        with pytest.raises(OSError, match="changed while"):
            source_sha256(path)
    else:
        assert source_sha256(path) == hashlib.sha256(content).hexdigest()


def test_file_changed_during_hash_is_rejected(phase_input, monkeypatch):
    p = phase_input()
    original = Path.open
    changed = False

    class Reader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, n):
            nonlocal changed
            value = self.stream.read(n)
            if not changed:
                changed = True
                with original(p, "ab") as writer:
                    writer.write(b"changed")
            return value

    def wrapped(path, *args, **kwargs):
        stream = original(path, *args, **kwargs)
        return Reader(stream) if path == p and args == ("rb",) else stream

    monkeypatch.setattr(Path, "open", wrapped)
    with pytest.raises(OSError, match="changed while"):
        source_sha256(p)


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_export_detects_change_during_writing_and_cleans_attempt(
    phase_input, tmp_path, monkeypatch, format
):
    p = phase_input()
    r = import_medpc_file(p, "Reversal")
    previous = export_import_results({p: r}, [p], tmp_path, format)
    before = {f.name: f.read_bytes() for f in previous.iterdir()}
    if format == "csv":
        writer = exporters.CSVExporter.export

        def modified(self, table, dest):
            result = writer(self, table, dest)
            if dest.name == "phase_metrics.csv":
                p.write_text(p.read_text().replace("0007", "0008"))
            return result

        monkeypatch.setattr(exporters.CSVExporter, "export", modified)
    else:
        writer = excel.save_workbook

        def modified(*args):
            result = writer(*args)
            p.write_text(p.read_text().replace("0007", "0008"))
            return result

        monkeypatch.setattr(excel, "save_workbook", modified)
    with pytest.raises(SourcesChangedError):
        export_import_results({p: r}, [p], tmp_path, format)
    assert list(tmp_path.glob("trial-cruncher-export-*")) == [previous]
    assert {f.name: f.read_bytes() for f in previous.iterdir()} == before
