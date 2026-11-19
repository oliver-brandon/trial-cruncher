"""Synthetic manual annotations stay separate from raw data and computed metrics."""

import csv
import hashlib
import json
from dataclasses import asdict

import pytest
from openpyxl import load_workbook

from trial_cruncher.analysis_metadata import AnalysisMetadata, analysis_metadata_from_dict
from trial_cruncher.exporters import export_import_results
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.projects import load_project, save_project


@pytest.mark.parametrize(
    "fields",
    [
        {"included": False},
        {"included": False, "inclusion_reason": " "},
        {"included": 0},
        {"condition": 1},
        {"condition": ""},
        {"version": "future"},
    ],
)
def test_invalid_metadata_rejected(fields):
    with pytest.raises(ValueError):
        AnalysisMetadata(**fields)


def test_missing_fields_not_inferred_from_raw_headers(write_export):
    path = write_export()
    original = import_medpc_file(path, "Reversal")
    assert original.raw["headers"]["Group"] == "00"
    assert original.analysis_metadata == AnalysisMetadata()
    assert original.analysis_metadata.included is None
    assert original.analysis_metadata.inclusion_status == "Not reviewed"
    assignment = AnalysisMetadata("Vehicle", False, "Equipment issue")
    result = import_medpc_file(path, "Reversal", assignment)
    assert result.summary == original.summary and result.phase_summary == original.phase_summary
    assert result.session == original.session and result.raw == original.raw
    assert result.analysis_metadata.included is False
    assert result.analysis_metadata.export_fields()["analysis_metadata_source"] == "manual"
    assert (
        assignment.sha256
        == hashlib.sha256(json.dumps(asdict(assignment), sort_keys=True).encode()).hexdigest()
    )


def test_project_roundtrip_and_legacy_not_reviewed_migration(phase_input, tmp_path):
    a = phase_input(name="a/same.txt")
    b = phase_input(name="b/same.txt")
    metadata = {
        a: AnalysisMetadata("Vehicle", True),
        b: AnalysisMetadata("Drug", False, "Technical exclusion"),
    }
    target = tmp_path / "study.tcproj.json"
    saved = save_project(
        target,
        [a, b],
        {a: "Acq", b: "Rev"},
        {},
        extensions=[".txt"],
        recursive=False,
        analysis_metadata=metadata,
    )
    loaded = load_project(target)
    assert loaded.project == saved.project
    assert {s.path: s.analysis_metadata for s in loaded.project.sources} == metadata
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["schema_version"] == "4"
    data["schema_version"] = "1"
    data.pop("analysis_plan")
    data.pop("analysis_sorts")
    for item in data["sources"]:
        item.pop("analysis_metadata")
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    legacy = load_project(target)
    assert (
        legacy.project.configuration_updated
        and "not reviewed" in legacy.project.configuration_update_message
    )
    assert all(s.analysis_metadata == AnalysisMetadata() for s in legacy.project.sources)
    assert [s.phase for s in legacy.project.sources] == ["Acq", "Rev"]
    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "damage", ["missing", "extra", "excluded_without_reason", "order", "version"]
)
def test_project_metadata_validation_is_transactional(phase_input, tmp_path, damage):
    path = phase_input()
    target = tmp_path / "bad.tcproj.json"
    save_project(target, [path], {}, {}, extensions=[".txt"], recursive=False)
    data = json.loads(target.read_text(encoding="utf-8"))
    m = data["sources"][0]["analysis_metadata"]
    if damage == "missing":
        m.pop("included")
    if damage == "extra":
        m["guessed_group"] = "automatic"
    if damage == "excluded_without_reason":
        m["included"] = False
    if damage == "order":
        m["session_order"] = 0
    if damage == "version":
        m["version"] = "unknown"
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    with pytest.raises(ValueError):
        load_project(target)
    assert target.read_bytes() == before


def records(sheet):
    head, *body = sheet.values
    return [dict(zip(head, row, strict=True)) for row in body]


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_every_record_and_annotation_is_exported_regardless_of_inclusion(
    phase_input, tmp_path, format
):
    included = phase_input(name="included.txt")
    excluded = phase_input(name="excluded.txt")
    unknown = phase_input(name="unreviewed.txt")
    failed = phase_input(name="failed.txt", program="OTHER")
    pending = tmp_path / "not-imported.txt"
    assignments = {
        included: AnalysisMetadata("=1+1", True, "Reviewed"),
        excluded: AnalysisMetadata("Drug", False, 'Equipment, "issue"\nμ'),
        failed: AnalysisMetadata("Vehicle", False, "Unsupported recording"),
        pending: AnalysisMetadata("Vehicle", False, "Missing recording"),
    }
    paths = [included, excluded, unknown, failed, pending]
    results = {p: import_medpc_file(p, "Reversal", assignments.get(p)) for p in paths[:-1]}
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths[:-1]}
    dest = export_import_results(results, paths, tmp_path, format, assignments=assignments)
    if format == "xlsx":
        book = load_workbook(dest / "results.xlsx")
    for filename, sheet in [
        ("sessions.csv", "Sessions"),
        ("choices.csv", "Choices"),
        ("phase_metrics.csv", "Phase metrics"),
    ]:
        if format == "csv":
            with (dest / filename).open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
        else:
            rows = records(book[sheet])
        assert {r["source_file"] for r in rows} == {str(included), str(excluded), str(unknown)}
        for row in rows:
            path = next(p for p in paths if str(p) == row["source_file"])
            annotation = assignments.get(path, AnalysisMetadata())
            assert row["analysis_inclusion_status"] == annotation.inclusion_status
            assert row["analysis_metadata_sha256"] == annotation.sha256
            if path == excluded:
                assert (
                    row["analysis_included"] is False
                    if format == "xlsx"
                    else row["analysis_included"] == "false"
                )
                assert row["analysis_inclusion_reason"] == annotation.inclusion_reason
                if sheet == "Sessions":
                    assert int(row["prl.choice_count"]) == 10
            if path == unknown:
                assert (
                    row["analysis_included"] is None
                    if format == "xlsx"
                    else row["analysis_included"] == ""
                )
                assert row["analysis_condition"] in ("", None)
            if path == included:
                assert row["analysis_condition"] == "=1+1"
        if format == "xlsx":
            header = list(next(book[sheet].values))
            for i, row in enumerate(rows, 2):
                cell = book[sheet].cell(i, header.index("analysis_condition") + 1)
                if row["analysis_condition"]:
                    assert cell.data_type == "s"
                if row["analysis_included"] is not None:
                    assert (
                        book[sheet].cell(i, header.index("analysis_included") + 1).data_type == "b"
                    )
    if format == "xlsx":
        quality = records(book["Quality"])
        assert {r["source_file"] for r in quality if r["record_type"] == "input"} == {
            str(p) for p in paths
        }
        book.close()
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    entries = {row["source_file"]: row for row in manifest["inputs"]}
    assert entries[str(excluded)]["status"] == "exported"
    assert (
        entries[str(failed)]["status"] == "failed"
        and entries[str(pending)]["status"] == "not_imported"
    )
    for p in paths:
        assert analysis_metadata_from_dict(entries[str(p)]["analysis_metadata"]) == assignments.get(
            p, AnalysisMetadata()
        )
    assert before == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths[:-1]}


def test_inclusion_does_not_override_strict_withholding(phase_input):
    path = phase_input()
    path.write_text(path.read_text().replace("0: 5 5 10", "0: 5 5 11"))
    result = import_medpc_file(path, "Reversal", AnalysisMetadata(included=True))
    assert result.analysis_metadata.included is True
    assert all(m.value is None for m in result.summary.metrics)
    assert all(m.value is None for m in result.phase_summary.metrics)
