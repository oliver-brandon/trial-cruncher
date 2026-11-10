"""Whole-session rate copies in phase exports retain their own scope/availability."""

import csv
import json
from dataclasses import asdict

import pytest
from openpyxl import load_workbook

from trial_cruncher import prl_metrics
from trial_cruncher.exporters import export_import_results
from trial_cruncher.prl_metrics import MEDPC_RATE
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.tables import WHOLE_SESSION_RATE_COLUMN


@pytest.mark.parametrize("format", ["csv", "xlsx"])
@pytest.mark.parametrize(
    "case", ["available", "unassigned", "empty", "bad_duration", "withheld", "warnings"]
)
def test_rate_copy_matches_session_result_in_all_availability_states(
    phase_input, tmp_path, monkeypatch, format, case
):
    path = phase_input(() if case == "empty" else (7, 6, 1, 7, 1, 2, 1, 7, 1, 7))
    text = path.read_text()
    if case == "bad_duration":
        text = text.replace("S: 11", "S: 0")
    if case == "withheld":
        text = text.replace("0: 5 5 10", "0: 5 5 11")
    if case == "warnings":
        text += "F:\n  2: 0\n"
    path.write_text(text)
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = import_medpc_file(path, None if case == "unassigned" else "Reversal")
    rate = next(m for m in result.summary.metrics if m.name == MEDPC_RATE)

    def forbidden(*args, **kwargs):
        pytest.fail("Export must not recalculate the session rate")

    monkeypatch.setattr(prl_metrics, "calculate_prl_summary", forbidden)
    dest = export_import_results({path: result}, [path], tmp_path, format)
    if format == "csv":
        with (dest / "sessions.csv").open(newline="") as f:
            (session,) = csv.DictReader(f)
        with (dest / "phase_metrics.csv").open(newline="") as f:
            (phase,) = csv.DictReader(f)
    else:
        book = load_workbook(dest / "results.xlsx")
        header, values = book["Sessions"].values
        session = dict(zip(header, values, strict=True))
        header, values = book["Phase metrics"].values
        phase = dict(zip(header, values, strict=True))
        cell = book["Phase metrics"].cell(2, list(header).index(WHOLE_SESSION_RATE_COLUMN) + 1)
        if rate.value is not None:
            assert cell.data_type == "n"
        assert "%" not in cell.number_format
        # The rate remains one session metric in Quality, not a ninth phase metric.
        qh, *qr = book["Quality"].values
        quality = [dict(zip(qh, row, strict=True)) for row in qr]
        assert len([r for r in quality if r["metric"] == MEDPC_RATE]) == 1
        book.close()
    assert phase[WHOLE_SESSION_RATE_COLUMN] == session[MEDPC_RATE]
    assert phase["whole_session_duration_s"] == session["duration_s"]
    assert phase["session_total_choices"] == session["prl.choice_count"]
    assert phase["whole_session_rate_scope"] == "whole session"
    assert phase["whole_session_rate_unit"] == rate.unit == "choices/min"
    assert phase["whole_session_rate_status"] == rate.status
    assert json.loads(phase["whole_session_rate_reasons_json"]) == list(rate.reasons)
    expected = json.loads(json.dumps({**asdict(rate), "status": rate.status}))
    assert json.loads(phase["whole_session_rate_result_json"]) == expected
    assert len(json.loads(phase["metric_results_json"])) == 8
    assert all(m["name"] != MEDPC_RATE for m in json.loads(phase["metric_results_json"]))
    if case == "unassigned":
        assert phase["phase_status"] == "phase_unassigned"
        assert rate.value is not None and phase["whole_session_rate_status"] == "available"
    if case == "empty":
        assert float(phase[WHOLE_SESSION_RATE_COLUMN]) == 0
    if case in ("bad_duration", "withheld"):
        assert phase[WHOLE_SESSION_RATE_COLUMN] in ("", None)
        assert phase["whole_session_rate_status"] == "unavailable"
        assert json.loads(phase["whole_session_rate_reasons_json"])
    if case == "warnings":
        assert phase["whole_session_rate_status"] == "available_with_warnings"
    manifest = json.loads((dest / "manifest.json").read_text())
    copy = manifest["configuration"]["medpc_trials_per_minute"]["phase_table_copy"]
    assert copy["value_column"] == WHOLE_SESSION_RATE_COLUMN
    assert copy["count_column"] == "session_total_choices"
    assert manifest["schema_version"] == "7"
    if format == "xlsx":
        assert manifest["workbook_schema_version"] == "6"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
