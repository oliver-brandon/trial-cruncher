"""Actual offscreen metadata editing, filtering, projects, and export snapshots."""

import csv
import json
from threading import Event

import pytest
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QMessageBox
from qt_helpers import answer_dialog, wait_until

from trial_cruncher import phase_metrics
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.gui import import_worker
from trial_cruncher.gui.metadata import MetadataDialog
from trial_cruncher.gui.window import MainWindow
from trial_cruncher.processing import import_medpc_file


def test_manual_editor_validation_immediate_updates_filters_and_project(
    app, phase_input, tmp_path, monkeypatch
):
    a = phase_input(name="a/same.txt")
    b = phase_input(name="b/same.txt")
    window = MainWindow()
    window.show()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    try:
        assert not window.metadata_button.isEnabled()
        window.add_paths([str(a), str(b)])
        wait_until(app, lambda: window._worker is None)
        window.phase_assignments = {a: "Acquisition", b: "Reversal"}
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        before = dict(window.import_results)

        def cancelled(d):
            assert isinstance(d, MetadataDialog)
            d.editors[1].inclusion.setCurrentIndex(2)
            d.buttons.button(QDialogButtonBox.StandardButton.Save).click()
            assert warnings and "reason" in warnings[-1]
            assert d.isVisible() and window.metadata_assignments == {}
            d.reject()

        with answer_dialog(monkeypatch, MetadataDialog, cancelled):
            window.metadata_button.click()
        assert window.import_results == before

        def edit(d):
            assert d.paths == (a, b)
            assert d.table.item(0, 0).text() == str(a)
            d.bulk_text.setText("Vehicle")
            d.apply_all.click()
            d.bulk_field.setCurrentText("Cohort")
            d.bulk_text.setText("001")
            d.apply_all.click()
            d.editors[0].order.setValue(2)
            d.editors[0].inclusion.setCurrentIndex(1)
            d.editors[1].condition.setText("Drug")
            d.editors[1].cohort.setText("002")
            d.editors[1].order.setValue(10)
            d.editors[1].inclusion.setCurrentIndex(2)
            d.editors[1].reason.setPlainText("Technical exclusion")
            d.accept()

        original_calc = phase_metrics.calculate_prl_summary
        monkeypatch.setattr(
            phase_metrics,
            "calculate_prl_summary",
            lambda *_: pytest.fail("Metadata edit recalculated metrics"),
        )
        with answer_dialog(monkeypatch, MetadataDialog, edit):
            window.metadata_button.click()
        for path in (a, b):
            assert window.import_results[path].summary is before[path].summary
            assert window.import_results[path].phase_summary is before[path].phase_summary
            assert window.import_results[path].session is before[path].session
        monkeypatch.setattr(phase_metrics, "calculate_prl_summary", original_calc)
        assert window.metadata_assignments[b].included is False
        assert window.metadata_assignments[a].session_order == 2
        view = window.phase_overview
        window.batch_tabs.setCurrentWidget(view)
        view.column_view.setCurrentText("Experiment metadata")
        view.table.sortByColumn(33, Qt.SortOrder.AscendingOrder)
        assert [view.proxy.index(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(2)] == [a, b]
        view.table.sortByColumn(33, Qt.SortOrder.DescendingOrder)
        assert [view.proxy.index(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(2)] == [b, a]
        view.inclusion_filter.setCurrentText("Excluded")
        assert (
            view.proxy.rowCount() == 1
            and view.proxy.index(0, 0).data(Qt.ItemDataRole.UserRole) == b
        )
        view.select_path(b)
        assert window.review.tabs.currentWidget() is window.review.analysis_details
        assert "Technical exclusion" in window.review.analysis_details.toPlainText()
        assert "Analysis: Excluded" in window.review.summary.text()
        assert "Condition / treatment: Drug" in window.review.details.toPlainText()
        view.inclusion_filter.setCurrentIndex(0)
        view.condition_filter.setCurrentIndex(view.condition_filter.findData("Vehicle"))
        assert (
            view.proxy.rowCount() == 1
            and view.proxy.index(0, 0).data(Qt.ItemDataRole.UserRole) == a
        )
        view.cohort_filter.setCurrentIndex(view.cohort_filter.findData("002"))
        assert view.proxy.rowCount() == 0
        view.clear_filters()
        view.inclusion_filter.setCurrentText("Included")
        view.select_path(a)

        # Excluding the visible row applies immediately and clears hidden detail.
        def exclude(d):
            d.editors[0].inclusion.setCurrentIndex(2)
            d.editors[0].reason.setPlainText("Review decision")
            d.accept()

        with answer_dialog(monkeypatch, MetadataDialog, exclude):
            window.metadata_button.click()
        assert view.proxy.rowCount() == 0 and window.review.phase_table.rowCount() == 0
        target = tmp_path / "study.tcproj.json"
        monkeypatch.setattr(
            QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), "")
        )
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(target), "")
        )
        window.save_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        expected = dict(window.metadata_assignments)
        window.clear_selection()
        assert window.metadata_assignments == {}
        window.open_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert window.metadata_assignments == expected and not window.import_results
        assert (
            view.inclusion_filter.currentIndex()
            == view.condition_filter.currentIndex()
            == view.cohort_filter.currentIndex()
            == 0
        )
        # Manual flags remain visible before re-import; they are not measurements.
        assert all(view.model.row(i).value(34) == "Excluded" for i in range(2))
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert {p: r.analysis_metadata for p, r in window.import_results.items()} == expected
        # Re-import still includes excluded files and preserves their numerical results.
        assert all(r.summary.metrics[0].value == 10 for r in window.import_results.values())
    finally:
        window.close()


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_filtered_inclusion_does_not_drop_export_rows_and_preserves_pending_metadata(
    app, phase_input, tmp_path, monkeypatch, format
):
    a = phase_input(name="a.txt")
    b = phase_input(name="b.txt")
    later = phase_input(name="later.txt")
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(a), str(b)])
        wait_until(app, lambda: window._worker is None)
        window.metadata_assignments = {
            a: AnalysisMetadata("Vehicle", "001", 2, True),
            b: AnalysisMetadata("Drug", "001", 10, False, "Excluded for review"),
        }
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        window.add_paths([str(later)])
        wait_until(app, lambda: window._worker is None)
        window.metadata_assignments[later] = AnalysisMetadata(
            included=False, inclusion_reason="Not yet reviewed"
        )
        view = window.phase_overview
        window.batch_tabs.setCurrentWidget(view)
        view.inclusion_filter.setCurrentText("Included")
        assert view.proxy.rowCount() == 1
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
        (window.excel_button if format == "xlsx" else window.export_button).click()
        wait_until(app, lambda: window._export_worker is None)
        (dest,) = tmp_path.glob("trial-cruncher-export-*")
        if format == "csv":
            with (dest / "phase_metrics.csv").open(newline="") as f:
                rows = list(csv.DictReader(f))
        else:
            from openpyxl import load_workbook

            book = load_workbook(dest / "results.xlsx")
            header, *body = book["Phase metrics"].values
            rows = [dict(zip(header, row, strict=True)) for row in body]
            book.close()
        assert {r["analysis_inclusion_status"] for r in rows} == {"Included", "Excluded"}
        assert len(rows) == 2
        manifest = json.loads((dest / "manifest.json").read_text())
        pending = next(i for i in manifest["inputs"] if i["source_file"] == str(later))
        assert (
            pending["status"] == "not_imported"
            and pending["analysis_metadata"]["included"] is False
        )
    finally:
        window.close()


def test_worker_freezes_metadata_and_retains_it_for_failures_and_stale_sources(
    app, phase_input, monkeypatch
):
    a = phase_input(name="a.txt")
    b = phase_input(name="b.txt", program="OTHER")
    entered, release = Event(), Event()
    real_import = import_medpc_file

    def controlled(path, phase=None, metadata=None):
        assert QThread.currentThread() != app.thread()
        if path == a:
            entered.set()
            assert release.wait(5)
        return real_import(path, phase, metadata)

    monkeypatch.setattr(import_worker, "import_medpc_file", controlled)
    window = MainWindow()
    try:
        window.add_paths([str(a), str(b)])
        wait_until(app, lambda: window._worker is None)
        assignment = AnalysisMetadata("A", None, 1, False, "Technical")
        window.metadata_assignments = {a: assignment, b: assignment}
        window.import_button.click()
        wait_until(app, entered.is_set)
        assert not window.metadata_button.isEnabled()
        window.assign_metadata()  # Busy guard must not open a modal dialog.
        window.metadata_assignments[a] = AnalysisMetadata("Future")
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        assert window.import_results[a].analysis_metadata == assignment
        assert (
            window.import_results[b].error
            and window.import_results[b].analysis_metadata == assignment
        )
        # Restore the current assignment for a normal GUI state, then invalidate source.
        window.metadata_assignments[a] = assignment
        a.write_text(a.read_text().replace("0007", "0008"))
        window.check_sources_button.click()
        wait_until(app, lambda: window._project_worker is None)
        row = window.phase_overview.model.row(window.overview.model._row_by_path[a])
        assert row.value(34) == "Excluded" and row.status == "Re-import required"
        assert a not in window.import_results
    finally:
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        window.close()
