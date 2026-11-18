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
