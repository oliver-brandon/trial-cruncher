"""Synthetic CSV round trips and failure tests; no scientific validation claims."""

import csv
import json
from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from trial_cruncher import exporters
from trial_cruncher.exporters import CSVExporter, export_import_results
from trial_cruncher.models import Session
from trial_cruncher.prl_metrics import METRIC_LABELS, calculate_prl_summary
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.tables import CHOICE_COLUMNS, build_choice_table, build_session_table


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_export_round_trip_provenance_missing_and_raw_fields(write_export, tmp_path):
    path = write_export()
    path.write_text(path.read_text().replace("S: 10.00\n", "").replace("1.22", "1.23"))
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = import_medpc_file(path)
    # Exercise CSV quoting/newlines/Unicode without creating a second reader dialect.
    session = replace(result.session, warnings=(*result.session.warnings, 'comma, "quote"\nμ'))
    result = replace(result, session=session, summary=calculate_prl_summary(session))
    destination = export_import_results({path: result}, [path], tmp_path)
    (row,) = read_csv(destination / "sessions.csv")
    choices = read_csv(destination / "choices.csv")
    manifest = json.loads((destination / "manifest.json").read_text())
    assert row["subject_id"] == "0007"
    assert row["session_id"] == row["duration_s"] == ""
    assert row["source_file"] == str(path)
    assert row["source_sha256"] == result.raw["source_sha256"]
    assert row["source_file_header"] == r"C:\Synthetic\example.txt"
    assert row["time_origin"] == "task_start"
    assert row["time_unit"] == "seconds"
    assert row["reader_version"] == "1"
    assert row["normalizer_version"] == "2"
    assert row["latency_available"] == row["head_entries_recorded"] == "false"
    assert json.loads(row["warnings_json"]) == list(session.warnings)
    raw = json.loads(row["metadata_json"])["raw_medpc"]
    assert raw["source_text"] == result.raw["source_text"]
    assert raw["arrays"]["F"]["0"] == "0.50"
    assert raw["scalars"]["D"] == "1.00"
    assert raw["line_numbers"] == result.raw["line_numbers"]
    assert json.loads(row["summary_checks_json"])["A[0]"] is None
    assert [row["source_index"] for row in choices] == ["0", "1", "2", "3"]
    assert choices[0]["timestamp_s"] == "0.0"
    assert choices[0]["outcome_code"] == "1"
    assert choices[0]["correct"] == "true"
    assert choices[1]["timestamp_s"] == choices[1]["correct"] == ""
    assert choices[1]["outcome_code"] == choices[1]["rewarded"] == ""
    assert choices[1]["raw_value"] == "1.23"
    assert choices[3]["correct"] == choices[3]["rewarded"] == "false"
    assert all(row["warnings_json"] == choices[0]["warnings_json"] for row in choices)
    assert choices[1]["source_line"] == str(session.events[1].raw_values["line_number"])
    assert manifest["tables"]["choices.csv"]["rows"] == 4
    assert [metric["name"] for metric in manifest["configuration"]["metrics"]] == list(
        METRIC_LABELS
    )
    assert manifest["configuration"]["metric_eligibility_policy"] == "strict-withholding-v2"
    assert manifest["schema_version"] == row["schema_version"] == "8"
    assert row["metric_definition_version"] == "4"
    assert row["metric_policy"] == "strict-withholding-v2"
    assert all(row[name] == "" for name in METRIC_LABELS)
    exported_metrics = json.loads(row["metric_results_json"])
    assert len(exported_metrics) == 7
    for metric in exported_metrics:
        assert metric["value"] is None and metric["status"] == "unavailable"
        assert metric["definition_version"] == "4"
        assert "invalid choice" in metric["reasons"][0]
        assert metric["warnings"] == list(session.warnings)
    diagnostics = json.loads(row["metric_diagnostics_json"])
    assert diagnostics["observed_record_count"] == 4
    assert diagnostics["decoded_choice_count"] == 3
    assert diagnostics["invalid_record_count"] == 1
    assert manifest["dependency_versions"]["pandas"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("array", ["", "C:\n", "C:\n  0: -987.987\n"])
def test_empty_or_missing_choices_have_headers_and_retain_raw(write_export, tmp_path, array):
    path = write_export()
    path.write_text(path.read_text().replace("C:\n  0: 0.01 1.22 2.36 4.57\n", array))
    result = import_medpc_file(path)
    destination = export_import_results({path: result}, [path], tmp_path)
    assert read_csv(destination / "choices.csv") == []
    with (destination / "choices.csv").open(newline="") as stream:
        assert next(csv.reader(stream)) == list(CHOICE_COLUMNS)
    (row,) = read_csv(destination / "sessions.csv")
    raw = json.loads(row["metadata_json"])["raw_medpc"]
    assert ("C" in raw["arrays"]) == bool(array)
    if "-987" in array:
        assert raw["arrays"]["C"]["0"] == "-987.987"


def test_sparse_choices_and_after_terminator_values_are_not_lost(write_export, tmp_path):
    path = write_export()
    path.write_text(path.read_text().replace("0: 0.01 1.22 2.36 4.57", "2: 1.22 -987.987 99.01"))
    result = import_medpc_file(path)
    destination = export_import_results({path: result}, [path], tmp_path)
    (choice,) = read_csv(destination / "choices.csv")
    assert choice["source_index"] == "2"
    assert choice["rewarded"] == "false"
    (session,) = read_csv(destination / "sessions.csv")
    raw = json.loads(session["metadata_json"])["raw_medpc"]
    assert raw["arrays"]["C"] == {"2": "1.22", "3": "-987.987", "4": "99.01"}
    assert "after the terminator" in session["warnings_json"]


def test_failed_unimported_and_warning_inputs_are_accounted_for(write_export, tmp_path):
    good = write_export()
    bad = tmp_path / "bad.txt"
    bad.write_text("malformed input")
    unsupported = tmp_path / "unsupported.txt"
    unsupported.write_text(good.read_text().replace("PRL_BO", "UNKNOWN"))
    pending = tmp_path / "pending.txt"
    results = {path: import_medpc_file(path) for path in (good, bad, unsupported)}
    destination = export_import_results(results, [pending, *results], tmp_path)
    manifest = json.loads((destination / "manifest.json").read_text())
    entries = {row["source_file"]: row for row in manifest["inputs"]}
    assert entries[str(good)]["status"] == "exported"
    assert entries[str(bad)]["status"] == entries[str(unsupported)]["status"] == "failed"
    assert entries[str(pending)]["status"] == "not_imported"
    assert "Expected a Med-PC" in entries[str(bad)]["error"]
    assert entries[str(unsupported)]["source_sha256"]
    assert len(read_csv(destination / "sessions.csv")) == 1
    with pytest.raises(ValueError, match="at least one"):
        export_import_results({bad: results[bad]}, [bad], tmp_path)
    assert len(list(tmp_path.glob("*-trial-cruncher-export-*"))) == 1


def test_export_twice_creates_separate_complete_bundles(write_export, tmp_path):
    path = write_export()
    results = {path: import_medpc_file(path)}
    first = export_import_results(results, [path], tmp_path)
    before = {file.name: file.read_bytes() for file in first.iterdir()}
    second = export_import_results(results, [path], tmp_path)
    assert first != second
    assert {file.name: file.read_bytes() for file in first.iterdir()} == before
    assert (second / "sessions.csv").read_bytes() == before["sessions.csv"]


def test_csv_writer_refuses_existing_sources_links_and_missing_source_path(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"original")
    table = pd.DataFrame({"raw": [Decimal("0.00"), None]}, dtype=object)
    with pytest.raises(ValueError, match="input file"):
        CSVExporter([source]).export(table, source)
    with pytest.raises(FileExistsError):
        CSVExporter().export(table, source)
    for name, target in (("alias", source), ("dangling", tmp_path / "absent")):
        link = tmp_path / name
        link.symlink_to(target)
        with pytest.raises(FileExistsError):
            CSVExporter().export(table, link)
        assert link.is_symlink()
    hard_link = tmp_path / "hardlink"
    hard_link.hardlink_to(source)
    with pytest.raises(FileExistsError):
        CSVExporter().export(table, hard_link)
    assert source.read_bytes() == b"original"
    absent_source = tmp_path / "deleted-input.txt"
    with pytest.raises(ValueError):
        CSVExporter([absent_source]).export(table, absent_source)
    assert not absent_source.exists()


@pytest.mark.parametrize("failed_name", ["choices.csv", "phase_metrics.csv", "manifest.json"])
def test_write_failure_removes_attempt_only(write_export, tmp_path, monkeypatch, failed_name):
    path = write_export()
    result = import_medpc_file(path)
    previous = export_import_results({path: result}, [path], tmp_path)
    before = {file.name: file.read_bytes() for file in previous.iterdir()}
    original_open = type(path).open

    def failing_open(candidate, *args, **kwargs):
        if candidate.name == failed_name and args and args[0] == "x":
            raise OSError("Synthetic disk failure")
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", failing_open)
    with pytest.raises(OSError, match="Synthetic disk failure"):
        export_import_results({path: result}, [path], tmp_path)
    assert list(tmp_path.glob("*-trial-cruncher-export-*")) == [previous]
    assert {file.name: file.read_bytes() for file in previous.iterdir()} == before
    assert import_medpc_file(path).session == result.session


def test_bad_metadata_and_unwritable_parent_leave_no_export(write_export, tmp_path, monkeypatch):
    path = write_export()
    result = import_medpc_file(path)
    invalid = replace(
        result,
        session=replace(result.session, metadata={**result.session.metadata, "invalid": object()}),
    )
    with pytest.raises(TypeError, match="Cannot export"):
        export_import_results({path: invalid}, [path], tmp_path)
    assert not list(tmp_path.glob("*-trial-cruncher-export-*"))

    def deny(*args, **kwargs):
        raise PermissionError("Synthetic permission denial")

    monkeypatch.setattr(exporters.Path, "mkdir", deny)
    with pytest.raises(PermissionError):
        export_import_results({path: result}, [path], tmp_path)
    assert not list(tmp_path.glob("*-trial-cruncher-export-*"))


def test_generic_missing_session_does_not_invent_provenance(tmp_path):
    session = Session(tmp_path / "unknown.txt")
    table = build_session_table([session])
    for column in ("subject_id", "session_id", "duration_s", "program", "source_sha256"):
        assert table.iloc[0][column] is None
    assert build_choice_table([session]).empty
    assert build_session_table([]).columns.tolist() == table.columns.tolist()


def test_mid_csv_write_failure_removes_partial_file(tmp_path, monkeypatch):
    real_writer = exporters.csv.writer

    class BrokenWriter:
        def __init__(self, stream):
            self.writer = real_writer(stream)
            self.rows = 0

        def writerow(self, row):
            self.writer.writerow(row)
            self.rows += 1
            if self.rows == 2:
                raise OSError("Synthetic mid-write failure")

    monkeypatch.setattr(exporters.csv, "writer", BrokenWriter)
    destination = tmp_path / "partial.csv"
    with pytest.raises(OSError, match="mid-write"):
        CSVExporter().export(pd.DataFrame({"value": [1, 2]}), destination)
    assert not destination.exists()


def test_competing_writers_do_not_overwrite(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    destination = tmp_path / "shared.csv"
    barrier = Barrier(2)

    def write(value):
        barrier.wait(timeout=5)
        try:
            CSVExporter().export(pd.DataFrame({"value": [value]}), destination)
        except FileExistsError:
            return None
        return value

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("one", "two")))
    (winner,) = [value for value in results if value is not None]
    assert read_csv(destination) == [{"value": winner}]


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
def test_export_requires_reimport_after_source_changes(write_export, tmp_path, export_format):
    from trial_cruncher.source_tracking import SourcesChangedError

    path = write_export()
    result = import_medpc_file(path)
    path.write_text(path.read_text().replace("Subject: 0007", "Subject: 0008"))
    changed = path.read_bytes(), path.stat().st_mtime_ns
    with pytest.raises(SourcesChangedError, match="re-import"):
        export_import_results({path: result}, [path], tmp_path, export_format)
    assert not list(tmp_path.glob("*-trial-cruncher-export-*"))
    assert (path.read_bytes(), path.stat().st_mtime_ns) == changed
    refreshed = import_medpc_file(path)
    destination = export_import_results({path: refreshed}, [path], tmp_path, export_format)
    assert (destination / "manifest.json").exists()


@pytest.mark.parametrize(
    "choices,counts,outcomes,expected",
    [
        ("0.06 1.27", "0 2 2", "0 0 1 1", ["2", "0", "2", "1", "1", "0.0"]),
        ("0.01 1.26 2.37", "1 2 3", "1 0 1 1", ["3", "1", "2", "2", "1", str(1 / 3)]),
        (None, "0 0 0", "0 0 0 0", ["0", "0", "0", "0", "0", ""]),
    ],
)
def test_metric_csv_zero_missing_and_precision(
    write_export, tmp_path, choices, counts, outcomes, expected
):
    c = f"C:\n  0: {choices}\n" if choices is not None else "C:\n"
    path = write_export(
        f"File: synthetic\nMSN: PRL_BO\nSubject: 0007\nS: 10\n"
        f"{c}A:\n  0: {counts}\n  5: 0.12345\nB:\n  0: {outcomes}\n"
    )
    result = import_medpc_file(path)
    destination = export_import_results({path: result}, [path], tmp_path)
    (row,) = read_csv(destination / "sessions.csv")
    assert [row[name] for name in METRIC_LABELS] == [*expected, str(60 * int(expected[0]) / 10)]
    serialized = json.loads(row["metric_results_json"])
    for metric, original in zip(serialized, result.summary.metrics, strict=True):
        assert metric["value"] == original.value
        assert metric["status"] == original.status
        assert metric["reasons"] == list(original.reasons)
        assert metric["unit"] == original.unit
    assert json.loads(row["metadata_json"])["raw_medpc"]["arrays"]["A"]["5"] == "0.12345"


def test_csv_mismatch_withholds_metrics_but_preserves_choice_rows(write_export, tmp_path):
    path = write_export()
    path.write_text(path.read_text().replace("2.00 2.00 4.00", "2.00 2.00 5.00"))
    result = import_medpc_file(path)
    destination = export_import_results({path: result}, [path], tmp_path)
    (row,) = read_csv(destination / "sessions.csv")
    assert all(row[name] == "" for name in METRIC_LABELS)
    assert all(
        "Saved count mismatch: A[2]" in metric["reasons"][0]
        for metric in json.loads(row["metric_results_json"])
    )
    assert len(read_csv(destination / "choices.csv")) == 4
    assert json.loads(row["metadata_json"])["raw_medpc"]["arrays"]["A"]["2"] == "5.00"


def test_export_requires_calculated_summary_before_writing(write_export, tmp_path):
    path = write_export()
    result = replace(import_medpc_file(path), summary=None)
    with pytest.raises(ValueError, match="re-import"):
        export_import_results({path: result}, [path], tmp_path)
    assert not list(tmp_path.glob("*-trial-cruncher-export-*"))


def test_csv_export_without_optional_matlab_packages(write_export, tmp_path, monkeypatch):
    from importlib.metadata import PackageNotFoundError, version

    def installed_version(name):
        if name in {"scipy", "h5py"}:
            raise PackageNotFoundError(name)
        return version(name)

    monkeypatch.setattr(exporters, "version", installed_version)
    path = write_export()
    output = export_import_results({path: import_medpc_file(path)}, [path], tmp_path)
    manifest = json.loads((output / "manifest.json").read_text())
    assert set(manifest["dependency_versions"]) == {"pandas", "numpy", "openpyxl", "PySide6"}
