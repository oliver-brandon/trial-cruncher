"""The embedded frontend reads the same sorted and reviewed values as Qt."""

import pytest
from PySide6.QtCore import Qt

from trial_cruncher.gui.web_data import batch, batch_tooltip, detail_section
from trial_cruncher.gui.window import MainWindow
from trial_cruncher.processing import import_medpc_file


def test_pages_follow_sort_and_show_reviewed_metrics(app, phase_input):
    path = phase_input()
    window = MainWindow()
    try:
        result = import_medpc_file(path, "Acquisition")
        window.import_results[path] = result
        window.overview.set_files((path,), {path: result})
        window.overview.table.sortByColumn(6, Qt.SortOrder.DescendingOrder)
        window.review_path(path)
        page = batch(window, "sessions", 0, 1)
        assert page["total"] == 1
        assert page["rows"][0]["path"] == str(path)
        assert page["rows"][0]["cells"][page["columns"].index(6)] == window.overview.model.row(
            0
        ).text(6)
        metrics = detail_section(window, "Session metrics")["content"]["table"]
        assert len(metrics["rows"]) == 7
        choices = detail_section(window, "Decoded choices", 0, 1)["content"]
        assert choices["total"] == len(result.session.events)
        assert len(choices["rows"]) == 1
        assert detail_section(window, "Decoded choices", 100, 1)["content"]["rows"] == []
        assert batch(window, "phases")["rows"][0]["path"] == str(path)
        phase_page = batch(window, "phases")
        assert len(phase_page["columns"]) < window.phase_overview.model.columnCount()
        assert phase_page["rows"][0]["pending_phase"]
        assert "Quality" in batch_tooltip(window, "sessions", str(path), 1)
        window.phase_assignments[path] = "Acquisition"
        assert not batch(window, "phases")["rows"][0]["pending_phase"]
        with pytest.raises(ValueError):
            batch(window, "sessions", 0, 501)
    finally:
        window.close()


def test_sections_preserve_withholding_and_page_choices(app, phase_input, monkeypatch):
    path = phase_input(codes=(1, 7) * 75)
    path.write_text(path.read_text().replace("  0: 75 75 150", "  0: 75 75 151"))
    result = import_medpc_file(path, "Acquisition")
    window = MainWindow()
    try:
        window.import_results[path] = result
        window.overview.set_files((path,), {path: result})
        window.review_path(path)
        assert (
            batch(window, "sessions")["rows"][0]["cells"][
                batch(window, "sessions")["columns"].index(6)
            ]
            == "Withheld"
        )
        metrics = detail_section(window, "Session metrics")["content"]["table"]["rows"]
        assert metrics[0][1] == "Unavailable"
        assert metrics[0][4]
        monkeypatch.setattr(
            window.review.source,
            "toPlainText",
            lambda: (_ for _ in ()).throw(AssertionError("Source must be loaded on demand")),
        )
        first = detail_section(window, "Decoded choices", 0, 100)["content"]
        second = detail_section(window, "Decoded choices", 100, 100)["content"]
        assert first["total"] == second["total"] == 150
        assert len(first["rows"]) == 100
        assert len(second["rows"]) == 50
        assert first["rows"][-1][0] == "99"
        assert second["rows"][0][0] == "100"
    finally:
        window.close()


def test_compact_data_view_orders_values_and_sorts_without_losing_missing(app, phase_input):
    from trial_cruncher.analysis_metadata import AnalysisMetadata
    from trial_cruncher.compact_results import DATA_COLUMNS

    first = phase_input((1, 1, 1, 7), name="one.txt")
    second = phase_input((7, 7, 7, 7), name="two.txt")
    results = {
        first: import_medpc_file(first, "Reversal", AnalysisMetadata("Drug", "A", included=True)),
        second: import_medpc_file(
            second, "Reversal", AnalysisMetadata("Vehicle", "A", included=True)
        ),
    }
    window = MainWindow()
    try:
        window.selected_files = set(results)
        window.import_results = results
        window.phase_assignments = dict.fromkeys(results, "Reversal")
        window.overview.set_files(tuple(results), results)
        window._compact_sort = (3, False)
        result = batch(window, "data")
        assert result["headers"] == DATA_COLUMNS
        assert [r["path"] for r in result["rows"]] == [str(second), str(first)]
        assert result["rows"][0]["cells"][3] == "0.0000"
        assert result["rows"][1]["cells"][3] == "0.7500"
        assert result["rows"][0]["cells"][2] == "Vehicle"
        assert result["rows"][0]["cells"][11] == "Unavailable"
        assert "not reached" in result["rows"][0]["tooltips"][11]
        window._compact_sort = (11, True)
        result = batch(window, "data")
        assert [r["path"] for r in result["rows"]] == [str(first), str(second)]
    finally:
        window.close()


def test_compact_pending_and_failed_rows_have_identity_and_distinct_state(app, phase_input):
    from trial_cruncher.analysis_metadata import AnalysisMetadata

    pending = phase_input(name="waiting.txt")
    failed = phase_input(name="unsupported.txt", program="UNSUPPORTED")
    result = import_medpc_file(failed, analysis_metadata=AnalysisMetadata("Treatment", "C"))
    window = MainWindow()
    try:
        window.selected_files = {pending, failed}
        window.import_results = {failed: result}
        window.phase_assignments = {pending: "Reversal"}
        window.overview.set_files(
            (pending, failed),
            {failed: result},
            {failed: result.analysis_metadata},
        )
        rows = {row["path"]: row for row in batch(window, "data")["rows"]}
        assert rows[str(pending)]["cells"][:3] == ["File: waiting.txt", "Reversal", "Unassigned"]
        assert rows[str(pending)]["row_state"] == "Not imported"
        assert rows[str(pending)]["cells"][3] == "—"
        assert rows[str(failed)]["cells"][:3] == ["0007", "Unassigned", "Treatment"]
        assert rows[str(failed)]["row_state"] == "Failed"
        assert "Unsupported" in rows[str(failed)]["state_detail"]
    finally:
        window.close()


def test_compact_trials_inspector_uses_recorded_choices_and_pages(app, phase_input):
    path = phase_input((1, 2, 6, 7) * 30)
    result = import_medpc_file(path, "Reversal")
    window = MainWindow()
    try:
        window.import_results[path] = result
        window.review_path(path)
        first = detail_section(window, "Trials", 0, 2)["content"]
        last = detail_section(window, "Trials", 100, 50)["content"]
        assert first["rows"] == [(1, 1, 1), (2, 1, 0)]
        assert first["total"] == 120
        assert len(last["rows"]) == 20
        assert last["rows"][-1] == (120, 0, 0)
        assert "1 = correct" in first["note"]
    finally:
        window.close()
