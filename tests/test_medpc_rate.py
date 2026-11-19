"""Synthetic Med-PC whole-session rate acceptance cases and UI/export checks."""

import csv
import json
import math

import pytest
from openpyxl import load_workbook
from PySide6.QtCore import Qt
from qt_helpers import wait_until

from trial_cruncher.exporters import export_import_results
from trial_cruncher.gui.window import MainWindow
from trial_cruncher.prl_metrics import MEDPC_RATE
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.projects import load_project, save_project


def rate(result):
    return next(m for m in result.summary.metrics if m.name == MEDPC_RATE)


@pytest.mark.parametrize(
    "count,duration,expected",
    [(30, 180, 10), (4, 10, 24), (10, 3600, 1 / 6), (2, 120, 1), (0, 120, 0)],
)
def test_full_session_rate_uses_recorded_s(phase_input, count, duration, expected):
    path = phase_input((1,) * count)
    path.write_text(path.read_text().replace(f"S: {count + 1}", f"S: {duration}"))
    result = import_medpc_file(path)
    assert rate(result).value == pytest.approx(expected)
    assert rate(result).unit == "choices/min"
    assert rate(result).definition_version == "4"
    assert result.phase_summary.config.phase is None  # Whole-session rate needs no assigned phase.
    assert rate(result).status == "available"


@pytest.mark.parametrize("duration", ["", "S: 0\n", "S: -1\n", "S: 1E+999\n", "S: 1E-999\n"])
def test_bad_duration_does_not_block_choice_or_phase_accuracy(write_export, duration):
    path = write_export()
    path.write_text(path.read_text().replace("S: 10.00\n", duration))
    result = import_medpc_file(path, "Reversal")
    assert result.error is None
    assert rate(result).value is None and rate(result).reasons
    assert result.summary.metrics[0].value == 4
    assert result.summary.metrics[5].value == result.phase_summary.metrics[0].value == 0.5


def test_no_saved_a3_substitution_or_header_duration_fallback(write_export):
    path = write_export()
    original = path.read_text().replace("24.00", "0.00").replace("4.57", "4.57 0 0")
    path.write_bytes(original.replace("\n", "\r\n").encode("utf-8"))
    result = import_medpc_file(path, "Acquisition")
    assert result.raw["arrays"]["A"][3] == 0
    assert result.summary.diagnostics.unused_slot_count == 2
    assert (
        rate(result).value == 24
    )  # 4 recorded choices / ten seconds, despite one-hour header interval.
    assert result.raw["source_text"] == path.read_bytes().decode("utf-8")


def test_out_of_duration_choice_blocks_only_rate_and_order_warning_does_not(write_export):
    path = write_export()
    text = path.read_text()
    path.write_text(text.replace("4.57", "14.57"))
    result = import_medpc_file(path, "Rev")
    assert rate(result).value is None and "exceeds S" in rate(result).reasons[0]
    assert result.summary.metrics[5].value == result.phase_summary.metrics[0].value == 0.5
    path.write_text(text.replace("0.01 1.22", "9.01 1.22"))
    result = import_medpc_file(path, "Rev")
    assert rate(result).value == 24 and rate(result).status == "available_with_warnings"


def test_unrepresentable_rate_and_empty_zero_duration_are_unavailable(phase_input):
    path = phase_input((1,))
    path.write_text(path.read_text().replace("S: 2", "S: 1E-323"))
    result = import_medpc_file(path)
    assert rate(result).value is None
    assert "finite number" in rate(result).reasons[0]
    path = phase_input(())
    path.write_text(path.read_text().replace("S: 1", "S: 0"))
    result = import_medpc_file(path)
    assert rate(result).value is None
    assert result.summary.metrics[0].value == 0


@pytest.mark.parametrize("damage", ["invalid", "mismatch", "missing"])
def test_strict_count_withholding_applies_to_rate(write_export, damage):
    path = write_export()
    text = path.read_text()
    if damage == "invalid":
        text = text.replace("1.22", "1.23")
    if damage == "mismatch":
        text = text.replace("2.00 2.00 4.00", "2.00 2.00 99.00")
    if damage == "missing":
        text = text.replace("C:\n  0: 0.01 1.22 2.36 4.57\n", "")
    path.write_text(text)
    result = import_medpc_file(path)
    assert rate(result).value is None and rate(result).reasons


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_rate_export_precision_provenance_and_manifest(phase_input, tmp_path, format):
    path = phase_input((1,) * 10)
    path.write_text(path.read_text().replace("S: 11", "S: 3600"))
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = import_medpc_file(path, "Acquisition")
    dest = export_import_results({path: result}, [path], tmp_path, format)
    if format == "csv":
        with (dest / "sessions.csv").open(newline="") as f:
            (row,) = csv.DictReader(f)
        with (dest / "phase_metrics.csv").open(newline="") as f:
            (phase,) = csv.DictReader(f)
    else:
        book = load_workbook(dest / "results.xlsx")
        headers, values = book["Sessions"].values
        row = dict(zip(headers, values, strict=True))
        cell = book["Sessions"].cell(2, list(headers).index(MEDPC_RATE) + 1)
        assert cell.data_type == "n" and "%" not in cell.number_format
        h, v = book["Phase metrics"].values
        phase = dict(zip(h, v, strict=True))
        book.close()
    assert float(row[MEDPC_RATE]) == pytest.approx(1 / 6, rel=1e-14)
    assert float(row["duration_s"]) == 3600 and int(row["prl.choice_count"]) == 10
    assert MEDPC_RATE not in phase  # Explicit whole-session alias, not a phase metric.
    assert float(phase["whole_session_medpc_trials_per_minute"]) == pytest.approx(1 / 6)
    assert phase["whole_session_rate_scope"] == "whole session"
    detail = next(m for m in json.loads(row["metric_results_json"]) if m["name"] == MEDPC_RATE)
    assert detail["unit"] == "choices/min" and detail["status"] == "available"
    manifest = json.loads((dest / "manifest.json").read_text())
    assert manifest["schema_version"] == "8"
    assert manifest["configuration"]["medpc_trials_per_minute"]["scope"] == "whole session"
    assert "S" in manifest["configuration"]["medpc_trials_per_minute"]["duration_source"]
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_previous_project_adds_rate_without_rewriting_setup(phase_input, tmp_path):
    path = phase_input()
    p = tmp_path / "old.tcproj.json"
    saved = save_project(p, [path], {path: "Reversal"}, {}, extensions=[".txt"], recursive=False)
    data = json.loads(p.read_text())
    data["analysis_configuration"]["session_definition_version"] = "3"
    p.write_text(json.dumps(data))
    before = p.read_bytes()
    loaded = load_project(p)
    assert loaded.project.configuration_updated
    assert "Med-PC" in loaded.project.configuration_update_message
    assert loaded.project.sources == saved.project.sources and p.read_bytes() == before


def test_batch_rate_is_independent_of_phase_and_sorts_numerically(
    app, phase_input, tmp_path, monkeypatch
):
    fast = phase_input((1, 1, 1, 7), name="fast.txt")
    slow = phase_input((1, 1, 1, 7), name="slow.txt")
    slow.write_text(slow.read_text().replace("S: 5", "S: 100"))
    zero = phase_input((), name="zero.txt")
    missing = phase_input((1,), name="missing.txt")
    missing.write_text(missing.read_text().replace("S: 2", "S: 0"))
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(p) for p in (fast, slow, zero, missing)])
        wait_until(app, lambda: window._worker is None)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        view = window.phase_overview
        window.batch_tabs.setCurrentWidget(view)
        view.column_view.setCurrentText("Session rate")
        assert all(r.phase_summary.config.phase is None for r in window.import_results.values())
        assert view.proxy.rowCount() == 4
        for order, expected in [
            (Qt.SortOrder.AscendingOrder, [zero, slow, fast, missing]),
            (Qt.SortOrder.DescendingOrder, [fast, slow, zero, missing]),
        ]:
            view.table.sortByColumn(29, order)
            assert [
                view.proxy.index(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(4)
            ] == expected
        view.status_filter.setCurrentText("Available")
        assert view.proxy.rowCount() == 3
        view.status_filter.setCurrentText("Unavailable metrics")
        assert view.proxy.rowCount() == 1
        assert view.proxy.index(0, 0).data(Qt.ItemDataRole.UserRole) == missing
        view.status_filter.setCurrentIndex(0)
        view.select_path(fast)
        assert window.review.tabs.currentWidget() is window.review.metric_page
        assert window.review.metric_table.rowCount() == 7
        assert window.review.metric_table.item(6, 0).text() == "Trials/min (Med-PC)"
        assert window.review.metric_table.item(6, 1).text() == "48.0000"
        row = view.model.source._row_by_path[fast]
        assert view.model.row(row).value(27) == 4
        assert view.model.row(row).value(28) == 5
        assert math.isclose(view.model.row(row).value(29), 48)
        view.column_view.setCurrentText("Errors and criterion")
        assert not view.proxy.rate_view and view.status_filter.currentText() == "All statuses"
    finally:
        window.close()
