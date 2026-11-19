"""Accuracy scale and export identity checks using small synthetic recordings."""

import csv
import json
from dataclasses import replace

import pytest
from openpyxl import load_workbook

from trial_cruncher.exporters import export_import_results
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.projects import analysis_configuration, load_project, save_project


@pytest.mark.parametrize(
    "codes,expected", [((7, 6), 0), ((1, 7), 0.5), ((1, 2), 1), ((1, 7, 6), 1 / 3)]
)
@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_accuracy_proportions_in_both_export_tables(phase_input, tmp_path, codes, expected, format):
    path = phase_input(codes)
    result = import_medpc_file(path, "Acquisition")
    assert result.summary.metrics[5].value == result.phase_summary.metrics[0].value == expected
    assert result.summary.metrics[5].unit == result.phase_summary.metrics[0].unit == "proportion"
    out = export_import_results({path: result}, [path], tmp_path, format)
    if format == "xlsx":
        book = load_workbook(out / "results.xlsx")
    for sheet, filename, column in [
        ("Sessions", "sessions.csv", "prl.proportion_correct"),
        ("Phase metrics", "phase_metrics.csv", "prl.phase.proportion_correct"),
    ]:
        if format == "csv":
            with (out / filename).open(newline="") as f:
                (row,) = csv.DictReader(f)
        else:
            header, values = book[sheet].values
            row = dict(zip(header, values, strict=True))
            cell = book[sheet].cell(2, list(header).index(column) + 1)
            assert cell.data_type == "n"
            assert "%" not in cell.number_format
            assert cell.number_format == "0.0000"
        assert float(row[column]) == pytest.approx(expected)
        assert not any("percent_correct" in key for key in row)
        accuracy = next(m for m in json.loads(row["metric_results_json"]) if m["name"] == column)
        assert accuracy["unit"] == "proportion"
    if format == "xlsx":
        book.close()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["schema_version"] == "8"
    if format == "xlsx":
        assert manifest["workbook_schema_version"] == "7"
    assert manifest["configuration"]["metric_definition_version"] == "4"
    assert manifest["configuration"]["phase_definition_version"] == "2"
    assert manifest["configuration"]["metrics"][5]["unit"] == "proportion"


def test_old_project_scale_upgrade_preserves_setup_until_explicit_save(phase_input, tmp_path):
    path = phase_input()
    target = tmp_path / "old.tcproj.json"
    saved = save_project(
        target, [path], {path: "Reversal 2"}, {}, extensions=[".txt"], recursive=False
    )
    data = json.loads(target.read_text())
    data["analysis_configuration"]["session_definition_version"] = "2"
    data["analysis_configuration"]["phase_definition_version"] = "1"
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    loaded = load_project(target)
    assert loaded.project.configuration_updated
    assert target.read_bytes() == before
    assert loaded.project.sources == saved.project.sources
    current = save_project(
        target,
        [path],
        {path: "Reversal 2"},
        {s.path: s.sha256 for s in loaded.project.sources},
        extensions=loaded.project.extensions,
        recursive=loaded.project.recursive,
        expected_project_sha256=loaded.file_sha256,
    )
    assert not current.project.configuration_updated
    assert json.loads(target.read_text())["analysis_configuration"] == analysis_configuration()
    # No general migration: another scientific-policy difference is still rejected.
    data["analysis_configuration"]["phase_profile"]["protocol_profile"] = "different-protocol"
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="incompatible"):
        load_project(target)


@pytest.mark.parametrize("stale", ["session_version", "phase_version", "session_name"])
def test_old_accuracy_snapshots_cannot_be_exported(phase_input, tmp_path, stale):
    path = phase_input()
    r = import_medpc_file(path, "Reversal")
    if stale == "session_version":
        r = replace(r, summary=replace(r.summary, definition_version="2"))
    if stale == "phase_version":
        r = replace(r, phase_summary=replace(r.phase_summary, definition_version="1"))
    if stale == "session_name":
        r = replace(
            r,
            summary=replace(
                r.summary,
                metrics=(
                    *r.summary.metrics[:-1],
                    replace(r.summary.metrics[-1], name="prl.percent_correct"),
                ),
            ),
        )
    with pytest.raises(ValueError, match="re-import"):
        export_import_results({path: r}, [path], tmp_path)
    assert not list(tmp_path.glob("*-trial-cruncher-export-*"))
