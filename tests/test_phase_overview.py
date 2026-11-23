"""Synthetic batch phase presentation and actual Qt navigation/lifecycle checks."""

import csv
import json
import os
from dataclasses import replace
from threading import Event

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from qt_helpers import wait_until

from trial_cruncher.gui import import_worker
from trial_cruncher.gui.overview import OverviewModel
from trial_cruncher.gui.phase_overview import HEADERS, VIEWS, BatchPhaseOverview
from trial_cruncher.gui.window import MainWindow
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.projects import save_project


def shown(view, path, column):
    row = view.model.source._row_by_path[path]
    return view.model.data(view.model.index(row, column))


def visible(view):
    return [
        view.proxy.index(i, 0).data(Qt.ItemDataRole.UserRole) for i in range(view.proxy.rowCount())
    ]


def click(app, view, path):
    row = view.model.source._row_by_path[path]
    index = view.proxy.mapFromSource(view.model.index(row, 0))
    assert index.isValid()
    view.table.scrollTo(index)
    app.processEvents()
    QTest.mouseClick(
        view.table.viewport(), Qt.MouseButton.LeftButton, pos=view.table.visualRect(index).center()
    )
    app.processEvents()
    assert view.current_path() == path


def test_values_ratios_statuses_and_literal_filters(app, phase_input):
    available = phase_input(name="available.txt")
    partial = phase_input((7,), name="partial.txt")
    empty = phase_input((), name="empty.txt")
    invalid = phase_input(name="invalid.txt")
    invalid.write_text(invalid.read_text().replace("1.06", "1.03"))
    unassigned = phase_input(name="unassigned.txt")
    warning = phase_input(name="warning.txt")
    warning.write_text(warning.read_text().replace("S: 11\n", ""))
    failed = phase_input(name="failed.txt", program="OTHER")
    pending = phase_input(name="later.txt")
    paths = (available, partial, empty, invalid, unassigned, warning, failed, pending)
    results = {
        p: import_medpc_file(p, None if p == unassigned else "Rev [1] <b>") for p in paths[:-1]
    }
    source = OverviewModel()
    view = BatchPhaseOverview(source)
    try:
        source.set_files(paths, results)
        assert view.model.rowCount() == 8 and view.model.columnCount() == len(HEADERS)
        assert [shown(view, p, 3) for p in paths] == [
            "Available",
            "Some metrics unavailable",
            "Unavailable metrics",
            "Withheld",
            "Phase unassigned",
            "Warnings",
            "Failed",
            "Not imported",
        ]
        assert [shown(view, available, c) for c in (4, 5, 6, 7, 8, 9, 10, 11, 12)] == [
            "10",
            "0.5000",
            "3",
            "2",
            "0.6667",
            "3",
            "Yes",
            "7",
            "9",
        ]
        assert [shown(view, available, c) for c in range(13, 25)] == [
            "0.2500",
            "1",
            "4",
            "0.0000",
            "0",
            "1",
            "0.0000",
            "0",
            "1",
            "0.6667",
            "2",
            "3",
        ]
        assert [shown(view, partial, c) for c in (7, 8, 9, 10, 13, 14, 15)] == [
            "0",
            "Unavailable",
            "0",
            "No",
            "Unavailable",
            "0",
            "0",
        ]
        assert shown(view, empty, 4) == "0" and shown(view, empty, 15) == "0"
        assert shown(view, invalid, 15) == "Withheld"
        assert shown(view, unassigned, 2) == "Unassigned"
        tip = view.model.data(
            view.model.index(source._row_by_path[available], 13), Qt.ItemDataRole.ToolTipRole
        )
        assert "Numerator: 1" in tip and "Denominator: 4" in tip
        assert "&lt;b&gt;" in tip and "<b>" not in tip
        view.search.setText("[1] <b>")
        assert set(visible(view)) == {available, partial, empty, invalid, warning}
        view.search.clear()
        view.phase_filter.setCurrentIndex(view.phase_filter.findData(""))
        assert visible(view) == [unassigned]
        view.clear_filters()
        view.status_filter.setCurrentText("Needs attention")
        assert set(visible(view)) == set(paths) - {available}
        view.status_filter.setCurrentText("Withheld")
        assert visible(view) == [invalid]
        view.search.setText("not present")
        assert not visible(view) and "Showing 0 of 8" in view.count_label.text()
    finally:
        view.close()


def test_numeric_sort_zero_and_missing_both_orders_and_full_precision(app, phase_input):
    zero = phase_input((7,), name="zero.txt")
    two = phase_input((1, 1, 1), name="two.txt")
    ten = phase_input((1,) * 11, name="ten.txt")
    missing = phase_input(name="missing.txt")
    results = {
        p: import_medpc_file(p, None if p == missing else "Rev") for p in (zero, two, ten, missing)
    }
    for path, value in ((two, 0.33331), (ten, 0.33334)):
        phase = results[path].phase_summary
        results[path] = replace(
            results[path],
            phase_summary=replace(
                phase, metrics=(replace(phase.metrics[0], value=value), *phase.metrics[1:])
            ),
        )
    source = OverviewModel()
    view = BatchPhaseOverview(source)
    try:
        source.set_files(tuple(results), results)
        for order, expected in [
            (Qt.SortOrder.AscendingOrder, [zero, two, ten, missing]),
            (Qt.SortOrder.DescendingOrder, [ten, two, zero, missing]),
        ]:
            view.table.sortByColumn(15, order)
            assert visible(view) == expected
            view.table.sortByColumn(5, order)
            assert visible(view) == expected
        assert shown(view, two, 5) == shown(view, ten, 5) == "0.3333"
        view.table.sortByColumn(10, Qt.SortOrder.AscendingOrder)
        assert visible(view)[0] == zero and visible(view)[-1] == missing
        for name, columns in VIEWS.items():
            view.column_view.setCurrentText(name)
            assert [c for c in range(len(HEADERS)) if not view.table.isColumnHidden(c)] == list(
                columns
            )
        view.column_view.setCurrentText("Win-stay")
        view.table.sortByColumn(15, Qt.SortOrder.DescendingOrder)
        view.column_view.setCurrentText("Errors and criterion")
        assert view.proxy.sortColumn() == 0  # Do not retain a hidden sort key.
    finally:
        view.close()


def test_phase_click_through_tabs_hidden_rows_and_pending_assignments(app, phase_input):
    first = phase_input(name="one/same.txt")
    second = phase_input((1, 1, 1), name="two/same.txt")
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(first), str(second)])
        wait_until(app, lambda: window._worker is None)
        window.phase_assignments = {first: "Acquisition", second: "Reversal"}
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        window.batch_tabs.setCurrentWidget(window.phase_overview)
        view = window.phase_overview
        assert view.model.source is window.overview.model
        view.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        click(app, view, second)
        assert window.review.tabs.currentWidget() is window.review.phase_page
        assert "Imported phase: Reversal" in window.review.phase_label.text()
        assert str(second) in window.review.details.toPlainText()
        window.phase_assignments[second] = "Pending change"
        assert shown(view, second, 2) == "Reversal"
        # Inactive view cannot overwrite phase review.
        window.overview.search.setText(f"{first.parent.name}{os.sep}")
        assert str(second) in window.review.details.toPlainText()
        view.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
        assert view.current_path() == second
        view.phase_filter.setCurrentIndex(view.phase_filter.findData("Acquisition"))
        assert visible(view) == [first]
        assert view.current_path() is None and window.review.phase_table.rowCount() == 0
        click(app, view, first)
        window.batch_tabs.setCurrentWidget(window.overview)
        assert window.overview.current_path() == first
        window.batch_tabs.setCurrentWidget(view)
        assert view.current_path() == first
        window.clear_selection()
        assert view.model.rowCount() == 0 and window.review.phase_table.rowCount() == 0
        assert not view.search.text() and view.phase_filter.currentIndex() == 0
    finally:
        window.close()


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
def test_filtered_phase_batch_exports_and_imports_all_sources(
    app, phase_input, tmp_path, monkeypatch, export_format
):
    a = phase_input(name="a.txt")
    b = phase_input(name="b.txt")
    failed = phase_input(name="failed.txt", program="OTHER")
    later = phase_input(name="later.txt")
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(p) for p in (a, b, failed)])
        wait_until(app, lambda: window._worker is None)
        window.phase_assignments = {a: "Acq", b: "Rev"}
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        window.add_paths([str(later)])
        wait_until(app, lambda: window._worker is None)
        view = window.phase_overview
        window.batch_tabs.setCurrentWidget(view)
        view.phase_filter.setCurrentIndex(view.phase_filter.findData("Acq"))
        assert visible(view) == [a] and "Showing 1 of 4" in view.count_label.text()
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
        (window.excel_button if export_format == "xlsx" else window.export_button).click()
        wait_until(app, lambda: window._export_worker is None)
        (out,) = tmp_path.glob("*-trial-cruncher-export-*")
        if export_format == "csv":
            with (out / "phase_metrics.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        else:
            from openpyxl import load_workbook

            book = load_workbook(out / "results.xlsx")
            header, *body = book["Phase metrics"].values
            rows = [dict(zip(header, row, strict=True)) for row in body]
            book.close()
        assert {row["source_file"] for row in rows} == {str(a), str(b)}
        manifest = json.loads((out / "manifest.json").read_text())
        assert {item["source_file"]: item["status"] for item in manifest["inputs"]} == {
            str(a): "exported",
            str(b): "exported",
            str(failed): "failed",
            str(later): "not_imported",
        }
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert len(window.import_results) == 4 and visible(view) == [a]
    finally:
        window.close()


def test_live_import_cancel_failure_stale_source_and_project_load(
    app, phase_input, tmp_path, monkeypatch
):
    a = phase_input(name="a.txt")
    b = phase_input(name="b.txt")
    entered, release = Event(), Event()
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(a), str(b)])
        wait_until(app, lambda: window._worker is None)
        window.phase_assignments = {a: "Rev", b: "Rev"}
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        view = window.phase_overview
        window.batch_tabs.setCurrentWidget(view)
        click(app, view, b)

        def controlled(path, phase=None, metadata=None):
            entered.set()
            assert release.wait(5)
            return import_medpc_file(path, phase, metadata)

        monkeypatch.setattr(import_worker, "import_medpc_file", controlled)
        window.import_button.click()
        wait_until(app, entered.is_set)
        assert shown(view, b, 3) == "Pending" and shown(view, b, 13) == "Pending"
        assert window.review.phase_table.rowCount() == 0
        view.status_filter.setCurrentText("Pending")
        view.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        window.cancel_import()
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        assert not visible(view)
        view.status_filter.setCurrentText("Not imported")
        assert visible(view) == [b] and shown(view, b, 3) == "Not imported (cancelled)"
        monkeypatch.setattr(import_worker, "import_medpc_file", import_medpc_file)
        b.write_text("malformed")
        view.clear_filters()
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        click(app, view, b)
        assert shown(view, b, 3) == "Failed" and window.review.phase_table.rowCount() == 0
        click(app, view, a)
        a.write_text(a.read_text().replace("0007", "0008"))
        view.phase_filter.setCurrentIndex(view.phase_filter.findData("Rev"))
        assert visible(view) == [a]
        window.check_sources_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert not visible(view) and view.current_path() is None
        assert "No files match" in window.review.summary.text()
        view.clear_filters()
        assert shown(view, a, 3) == "Re-import required" and shown(view, a, 13) == "Not imported"
        assert window.review.phase_table.rowCount() == 0
        view.status_filter.setCurrentText("Needs attention")
        assert set(visible(view)) == {a, b}
        # Loading a setup while Phase results is active clears both views/results/filters.
        project = tmp_path / "saved.tcproj.json"
        save_project(project, [a, b], {a: "Acq"}, {}, extensions=[".txt"], recursive=False)
        window.overview.model.start_import()
        window.overview.model.finish_import()
        assert shown(view, b, 3) == "Not imported (cancelled)"
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(project), "")
        )
        window.open_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert (
            view.status_filter.currentText() == "All statuses"
            and view.phase_filter.currentIndex() == 0
        )
        assert not window.import_results and window.review.phase_table.rowCount() == 0
        assert all(shown(view, p, 4) == "Not imported" for p in (a, b))
        assert all(shown(view, p, 3) == "Not imported" for p in (a, b))
    finally:
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        window.close()


def test_incremental_filter_menus_preserve_selection_and_drop_obsolete_labels(app, phase_input):
    from trial_cruncher.analysis_metadata import AnalysisMetadata

    path = phase_input()
    result = import_medpc_file(path, "Acquisition", AnalysisMetadata("Vehicle"))
    source = OverviewModel()
    view = BatchPhaseOverview(source)
    try:
        source.set_files([path], {path: result})
        view.phase_filter.setCurrentIndex(view.phase_filter.findData("Acquisition"))
        view.select_path(path)
        updated = replace(result, analysis_metadata=AnalysisMetadata("Drug"))
        source.set_result(updated)
        assert view.current_path() == path
        assert view.phase_filter.currentData() == "Acquisition"
        for combo, old, new in ((view.condition_filter, "Vehicle", "Drug"),):
            assert combo.findData(old) == -1
            assert combo.findData(new) >= 0
        source.start_import()
        assert not view.proxy.rowCount()
        source.set_result(updated)
        assert view.proxy.rowCount() == 1
        assert view.current_path() is None
    finally:
        view.close()
