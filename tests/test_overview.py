"""Synthetic batch overview checks, including real Qt selection and worker signals."""

import csv
import json
import os
import time
from dataclasses import replace
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from trial_cruncher.gui import import_worker  # noqa: E402
from trial_cruncher.gui.overview import BatchOverview  # noqa: E402
from trial_cruncher.gui.window import MainWindow  # noqa: E402
from trial_cruncher.processing import import_medpc_file  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def make_input(tmp_path):
    def make(
        name,
        *,
        n=2,
        subject="0007",
        program="PRL_BO",
        date="12/01/25",
        duration="10",
        c=None,
        saved=None,
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if c is None:
            c = "C:\n" + ("  0: " + " ".join(f"{i}.01" for i in range(n)) + "\n" if n else "")
        path.write_text(
            f"File: synthetic\nSubject: {subject}\nMSN: {program}\nStart Date: {date}\n"
            + (f"S: {duration}\n" if duration is not None else "")
            + f"{c}A:\n  0: {n} 0 {n if saved is None else saved}\nB:\n  0: {n} 0 0 0\n"
        )
        return path

    return make


def wait_until(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), "GUI operation did not finish"


def visible_paths(overview):
    return [
        overview.proxy.index(i, 0).data(Qt.ItemDataRole.UserRole)
        for i in range(overview.proxy.rowCount())
    ]


def shown(overview, path, column, role=Qt.ItemDataRole.DisplayRole):
    row = visible_paths(overview).index(path)
    return overview.proxy.index(row, column).data(role)


def click_row(app, overview, path, column=0):
    row = visible_paths(overview).index(path)
    index = overview.proxy.index(row, column)
    overview.table.scrollTo(index)
    app.processEvents()
    QTest.mouseClick(
        overview.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=overview.table.visualRect(index).center(),
    )
    app.processEvents()
    assert overview.current_path() == path


def test_quality_missing_withheld_zero_and_raw_metadata(app, make_input):
    good = make_input("good.txt")
    warning = make_input("warning.txt", duration=None)
    withheld = make_input("withheld.txt", saved=3)
    missing = make_input("missing.txt", c="")
    empty = make_input("empty.txt", n=0, duration="0")
    failed = make_input("failed.txt", program="UNSUPPORTED", subject="0012")
    pending = make_input("pending.txt")
    paths = [good, warning, withheld, missing, empty, failed, pending]
    results = {p: import_medpc_file(p) for p in paths if p != pending}
    overview = BatchOverview()
    try:
        overview.set_files(paths, results)
        expected = [
            "Available",
            "Unavailable metrics",
            "Withheld",
            "Unavailable metrics",
            "Unavailable metrics",
            "Failed",
            "Not imported",
        ]
        assert [shown(overview, p, 1) for p in paths] == expected
        assert shown(overview, good, 2) == "0007"
        assert shown(overview, good, 6) == "2"
        assert shown(overview, good, 11) == "1.0000"
        assert shown(overview, warning, 5) == "Unavailable"
        assert shown(overview, withheld, 6) == "Withheld"
        assert "Saved count mismatch: A[2]" in shown(
            overview, withheld, 6, Qt.ItemDataRole.ToolTipRole
        )
        assert shown(overview, missing, 6) == "Unavailable"
        assert "C is missing" in shown(overview, missing, 6, Qt.ItemDataRole.ToolTipRole)
        assert shown(overview, empty, 6) == "0"
        assert shown(overview, empty, 5) == "0.0"
        assert shown(overview, empty, 11) == "Unavailable"
        assert "zero recorded choices" in shown(overview, empty, 11, Qt.ItemDataRole.ToolTipRole)
        assert (
            shown(overview, failed, 2) == "0012"
        )  # Raw extraction still identifies failed program.
        assert shown(overview, failed, 6) == "Unavailable"
        assert "Unsupported PRL program" in shown(overview, failed, 1, Qt.ItemDataRole.ToolTipRole)
        assert shown(overview, pending, 6) == "Not imported"
        assert shown(overview, pending, 12) == "Not imported"
        assert str(good) in shown(overview, good, 0, Qt.ItemDataRole.ToolTipRole)
        assert not (overview.proxy.flags(overview.proxy.index(0, 0)) & Qt.ItemFlag.ItemIsEditable)
        assert "Showing 7 of 7 files" in overview.count_label.text()
    finally:
        overview.close()


@pytest.mark.parametrize("column", [5, 6, 11])
def test_numeric_sort_both_directions_keeps_unavailable_last(app, make_input, column):
    small = make_input("z-small.txt", n=2, duration="2")
    large = make_input("a-large.txt", n=10, duration="10")
    missing = make_input("0-missing.txt", c="", duration=None)
    results = {p: import_medpc_file(p) for p in (small, large, missing)}
    if column == 11:
        # Synthetic UI values exercise precision beneath identical display rounding.
        for path, value in ((small, 0.33331), (large, 0.33334)):
            original = results[path]
            metrics = (
                *original.summary.metrics[:5],
                replace(original.summary.metrics[5], value=value),
                *original.summary.metrics[6:],
            )
            results[path] = replace(original, summary=replace(original.summary, metrics=metrics))
    overview = BatchOverview()
    try:
        overview.set_files(tuple(results), results)
        overview.select_path(small)
        for order, expected in (
            (Qt.SortOrder.AscendingOrder, [small, large, missing]),
            (Qt.SortOrder.DescendingOrder, [large, small, missing]),
        ):
            overview.table.sortByColumn(column, order)
            assert visible_paths(overview) == expected
            assert overview.current_path() == small
        if column == 11:
            assert shown(overview, small, 11) == shown(overview, large, 11) == "0.3333"
    finally:
        overview.close()


def test_filter_combinations_literal_search_and_date_text_sort(app, make_input):
    first = make_input("one/file[1].txt")
    second = make_input("two/file.txt", program="PRL_OPTO_CORSTIM", subject="0010", date="01/01/26")
    warning = make_input("warning.txt", duration=None)
    paths = (first, second, warning)
    overview = BatchOverview()
    try:
        overview.set_files(paths, {p: import_medpc_file(p) for p in paths})
        overview.table.sortByColumn(4, Qt.SortOrder.AscendingOrder)
        assert visible_paths(overview)[0] == second  # Source text order, not inferred year order.
        overview.search.setText("FILE[1]")
        assert visible_paths(overview) == [first]
        overview.search.setText("0007")
        assert set(visible_paths(overview)) == {first, warning}
        overview.program.setCurrentIndex(overview.program.findData("PRL_OPTO_CORSTIM"))
        assert not visible_paths(overview)
        assert "No files match the filters" in overview.count_label.text()
        overview.search.clear()
        assert visible_paths(overview) == [second]
        overview.program.setCurrentIndex(0)
        overview.quality.setCurrentText("Needs attention")
        assert visible_paths(overview) == [warning]
        overview.search.setText("TASK DURATION")
        assert visible_paths(overview) == [warning]
        overview.reset_filters.click()
        assert set(visible_paths(overview)) == set(paths)
        assert overview.program.currentIndex() == overview.quality.currentIndex() == 0
    finally:
        overview.close()


@pytest.mark.parametrize(
    "quality",
    ["Available", "Warnings", "Withheld", "Unavailable metrics", "Failed", "Not imported"],
)
def test_status_filters_and_attention_include_failures_and_unimported(app, make_input, quality):
    paths = {
        "Available": make_input("available.txt"),
        "Warnings": make_input("warning.txt"),
        "Withheld": make_input("withheld.txt", saved=3),
        "Unavailable metrics": make_input("missing.txt", c=""),
        "Failed": make_input("failed.txt", program="OTHER"),
        "Not imported": make_input("pending.txt"),
    }
    warning_path = paths["Warnings"]
    warning_path.write_text(warning_path.read_text() + "F:\n  2: 0\n")
    results = {
        path: import_medpc_file(path) for state, path in paths.items() if state != "Not imported"
    }
    overview = BatchOverview()
    try:
        overview.set_files(tuple(paths.values()), results)
        overview.quality.setCurrentText(quality)
        assert visible_paths(overview) == [paths[quality]]
        overview.quality.setCurrentText("Needs attention")
        assert set(visible_paths(overview)) == set(paths.values()) - {paths["Available"]}
    finally:
        overview.close()


def test_sorted_click_through_duplicate_names_and_hidden_selection_clear(app, make_input):
    first = make_input("one/same.txt", n=2)
    second = make_input("two/same.txt", n=10, subject="0010")
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(first), str(second)])
        wait_until(app, lambda: window._worker is None)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        overview = window.overview
        overview.table.sortByColumn(6, Qt.SortOrder.DescendingOrder)
        click_row(app, overview, first)
        assert f"Source file: {first}" in window.review.details.toPlainText()
        assert window.review.metric_table.item(0, 1).text() == "2"
        click_row(app, overview, second)
        assert f"Source file: {second}" in window.review.details.toPlainText()
        assert window.review.choice_model.rowCount() == 10
        overview.table.sortByColumn(6, Qt.SortOrder.AscendingOrder)
        assert overview.current_path() == second
        assert f"Source file: {second}" in window.review.details.toPlainText()
        overview.search.setText("one/")
        assert visible_paths(overview) == [first]
        assert overview.current_path() is None
        assert window.review.metric_table.rowCount() == 0
        assert window.review.source.toPlainText() == ""
        overview.search.setText("no matching file")
        assert window.review.choice_model.rowCount() == 0
        assert "No files match" in window.review.summary.text()
        assert "Showing 0 of 2" in overview.count_label.text()
        overview.reset_filters.click()
        click_row(app, overview, first)
        assert window.review.choice_model.rowCount() == 2
    finally:
        window.close()


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
def test_filters_do_not_limit_export_or_import_and_clear_resets_view(
    app, make_input, monkeypatch, export_format
):
    first = make_input("one.txt")
    second = make_input("two.txt", n=10, program="PRL_OPTO_CORSTIM")
    failed = make_input("failed.txt", program="OTHER")
    pending = make_input("later.txt")
    paths = (first, second, failed, pending)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(p) for p in paths[:-1]])
        wait_until(app, lambda: window._worker is None)
        window.overview.search.setText("one.txt")
        assert window.overview.proxy.rowCount() == 1
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert len(window.import_results) == 3
        window.add_paths([str(pending)])
        wait_until(app, lambda: window._worker is None)
        assert window.overview.proxy.rowCount() == 1
        assert "Showing 1 of 4" in window.overview.count_label.text()
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(first.parent))
        (window.excel_button if export_format == "xlsx" else window.export_button).click()
        wait_until(app, lambda: window._export_worker is None)
        (destination,) = first.parent.glob("trial-cruncher-export-*")
        if export_format == "xlsx":
            from openpyxl import load_workbook

            book = load_workbook(destination / "results.xlsx")
            header, *body = book["Sessions"].values
            exported = [dict(zip(header, row, strict=True)) for row in body]
            book.close()
        else:
            with (destination / "sessions.csv").open(newline="") as stream:
                exported = list(csv.DictReader(stream))
        assert {row["source_file"] for row in exported} == {str(first), str(second)}
        manifest = json.loads((destination / "manifest.json").read_text())
        assert {entry["source_file"]: entry["status"] for entry in manifest["inputs"]} == {
            str(first): "exported",
            str(second): "exported",
            str(failed): "failed",
            str(pending): "not_imported",
        }
        window.overview.program.setCurrentIndex(
            window.overview.program.findData("PRL_OPTO_CORSTIM")
        )
        window.overview.quality.setCurrentText("Warnings")
        window.clear_button.click()
        assert not window.selected_files and not window.import_results
        assert window.overview.model.rowCount() == window.overview.proxy.rowCount() == 0
        assert window.overview.search.text() == ""
        assert window.overview.program.currentIndex() == window.overview.quality.currentIndex() == 0
        assert window.review.metric_table.rowCount() == 0
        assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths} == before
    finally:
        window.close()


def test_live_sort_filter_cancellation_and_reimport_clear_stale_values(
    app, make_input, monkeypatch
):
    first = make_input("a-first.txt")
    second = make_input("z-second.txt", n=10)
    entered, release = Event(), Event()
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(first), str(second)])
        wait_until(app, lambda: window._worker is None)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert shown(window.overview, second, 6) == "10"

        def controlled(path):
            entered.set()
            assert release.wait(5)
            return import_medpc_file(path)

        monkeypatch.setattr(import_worker, "import_medpc_file", controlled)
        window.import_button.click()
        wait_until(app, entered.is_set)
        overview = window.overview
        assert all(shown(overview, p, 1) == "Pending" for p in (first, second))
        assert all(shown(overview, p, 6) == "Pending" for p in (first, second))
        assert window.review.metric_table.rowCount() == 0
        overview.table.sortByColumn(6, Qt.SortOrder.DescendingOrder)
        overview.quality.setCurrentText("Pending")
        click_row(app, overview, second)
        assert "No import result" in window.review.summary.text()
        window.cancel_button.click()
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        assert overview.proxy.rowCount() == 0  # No pending results after cancellation.
        assert window.review.metric_table.rowCount() == 0
        overview.quality.setCurrentText("Not imported")
        assert visible_paths(overview) == [second]
        assert shown(overview, second, 1) == "Not imported (cancelled)"
        assert shown(overview, second, 6) == "Not imported"
        overview.clear_filters()
        assert shown(overview, first, 6) == "2"
        second.write_text("Malformed on re-read")
        monkeypatch.setattr(import_worker, "import_medpc_file", import_medpc_file)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert shown(overview, second, 1) == "Failed"
        assert shown(overview, second, 6) == "Unavailable"
        click_row(app, overview, second)
        assert window.review.metric_table.rowCount() == 0
        assert "Expected a Med-PC" in window.review.warnings.toPlainText()
    finally:
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        window.close()
