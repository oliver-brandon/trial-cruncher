import os
import time
from threading import Event as ThreadEvent

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import Qt, QThread  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from trial_cruncher.gui import import_worker as worker_module  # noqa: E402
from trial_cruncher.gui import window as window_module  # noqa: E402
from trial_cruncher.gui.window import MainWindow  # noqa: E402
from trial_cruncher.processing import import_medpc_file  # noqa: E402


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
def test_phase_assignment_dialog_import_snapshot_and_full_export(
    app, phase_input, monkeypatch, export_format
):
    import csv
    import json

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialogButtonBox

    from trial_cruncher.gui.phases import PhaseDialog

    first = phase_input(name="a/same.txt")
    second = phase_input((1, 1, 1), name="b/same.txt")
    root = first.parent.parent
    window = MainWindow()
    window.show()
    try:
        assert not window.phase_button.isEnabled()
        window.add_paths([str(first), str(second)])
        wait_for_discovery(app, window)

        def edit(cancel=False):
            dialog = app.activeModalWidget()
            assert isinstance(dialog, PhaseDialog)
            assert dialog.paths == (first, second)
            assert dialog.table.item(0, 0).text() == str(first)
            dialog.bulk_phase.setCurrentText("Acquisition")
            dialog.apply_all.click()
            dialog.pickers[1].setCurrentText("Reversal 2")
            button = (
                QDialogButtonBox.StandardButton.Cancel
                if cancel
                else QDialogButtonBox.StandardButton.Save
            )
            dialog.buttons.button(button).click()

        QTimer.singleShot(0, lambda: edit(True))
        window.phase_button.click()
        assert window.phase_assignments == {}
        QTimer.singleShot(0, edit)
        window.phase_button.click()
        assert window.phase_assignments == {first: "Acquisition", second: "Reversal 2"}
        window.import_button.click()
        assert not window.phase_button.isEnabled()
        wait_until(app, lambda: window._import_worker is None)
        choose_path(window, first)
        assert "Acquisition" in window.review.phase_label.text()
        assert window.review.phase_table.rowCount() == 8
        assert window.review.phase_table.item(1, 1).text() == "3"
        assert window.review.phase_table.item(4, 3).text() == "1"
        assert window.review.phase_table.item(4, 4).text() == "4"
        choose_path(window, second)
        assert "Reversal 2" in window.review.phase_label.text()
        assert "Postcriterion choices: 0" in window.review.phase_diagnostics.toPlainText()
        assert window.review.phase_table.item(3, 1).text() == "Unavailable"

        # Pending edits do not relabel already calculated results or their export.
        def reassign():
            d = app.activeModalWidget()
            d.bulk_phase.setCurrentText("Changed next import")
            d.apply_all.click()
            d.accept()

        QTimer.singleShot(0, reassign)
        window.phase_button.click()
        assert window.import_results[first].phase_summary.config.phase == "Acquisition"
        window.overview.search.setText(str(first))
        assert window.overview.proxy.rowCount() == 1
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(root))
        (window.excel_button if export_format == "xlsx" else window.export_button).click()
        wait_until(app, lambda: window._export_worker is None)
        (out,) = root.glob("trial-cruncher-export-*")
        if export_format == "csv":
            with (out / "phase_metrics.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        else:
            from openpyxl import load_workbook

            book = load_workbook(out / "results.xlsx")
            header, *body = book["Phase metrics"].values
            rows = [dict(zip(header, r, strict=True)) for r in body]
            book.close()
        assert {r["source_file"]: r["phase"] for r in rows} == {
            str(first): "Acquisition",
            str(second): "Reversal 2",
        }
        manifest = json.loads((out / "manifest.json").read_text())
        assert len(manifest["configuration"]["phase_configurations"]) == 2
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert all(
            r.phase_summary.config.phase == "Changed next import"
            for r in window.import_results.values()
        )
        window.clear_selection()
        assert window.phase_assignments == {}
        assert window.review.phase_table.rowCount() == 0
    finally:
        window.close()


def test_phase_worker_snapshot_cancel_and_failed_reimport(app, phase_input, monkeypatch):
    first = phase_input(name="a.txt")
    second = phase_input(name="b.txt")
    entered, release = ThreadEvent(), ThreadEvent()

    def controlled(path, phase=None):
        assert QThread.currentThread() != app.thread()
        if path == first:
            entered.set()
            assert release.wait(5)
        return import_medpc_file(path, phase)

    monkeypatch.setattr(worker_module, "import_medpc_file", controlled)
    window = MainWindow()
    try:
        window.add_paths([str(first), str(second)])
        wait_for_discovery(app, window)
        window.phase_assignments = {first: "Acquisition", second: "Reversal"}
        window.import_button.click()
        wait_until(app, entered.is_set)
        window.assign_phases()  # Busy guard must not open a dialog.
        window.phase_assignments[first] = "Future"
        window.cancel_import()
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        assert window.import_results[first].phase_summary.config.phase == "Acquisition"
        assert second not in window.import_results
        monkeypatch.setattr(worker_module, "import_medpc_file", import_medpc_file)
        first.write_text("malformed")
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        choose_path(window, first)
        assert window.import_results[first].phase_summary is None
        assert window.review.phase_table.rowCount() == 0
        choose_path(window, second)
        assert window.review.phase_table.rowCount() == 8
        assert window.import_results[second].phase_summary.config.phase == "Reversal"
        window.phase_assignments.clear()
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        choose_path(window, second)
        assert window.review.metric_table.item(0, 1).text() == "10"
        assert all(window.review.phase_table.item(i, 1).text() == "Unavailable" for i in range(8))
    finally:
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        window.close()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for_discovery(app, window):
    deadline = time.monotonic() + 5
    while window._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window._worker is None, "Discovery worker did not finish"


def wait_until(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), "Background operation did not finish"


def choose_path(window, path):
    window.overview.select_path(path)


def cell(window, row, column):
    model = window.review.choice_model
    return model.data(model.index(row, column))


def test_file_and_folder_dialogs_add_candidates(app, tmp_path, monkeypatch):
    selected = tmp_path / "session.mat"
    selected.touch()
    window = MainWindow()
    window.show()
    try:
        assert window.windowTitle() == "Trial Cruncher"
        monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([str(selected)], ""))
        window.add_files_button.click()
        wait_for_discovery(app, window)
        assert window.selected_files == {selected}
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
        window.add_folder_button.click()
        wait_for_discovery(app, window)
        assert window.overview.model.rowCount() == 1
        assert window.add_files_button.isEnabled()
        window.clear_button.click()
        assert window.overview.model.rowCount() == 0
        assert not window.selected_files
    finally:
        window.close()


def test_import_review_mixed_results_and_no_source_changes(app, write_export):
    good = write_export()
    original = good.read_bytes(), good.stat().st_mtime_ns
    warning = good.with_name("warning.txt")
    warning.write_text(good.read_text().replace("1.22", "1.23"))
    bad = good.with_name("bad.txt")
    bad.write_text("not an export")
    unsupported = good.with_name("unsupported.txt")
    unsupported.write_text(good.read_text().replace("MSN: PRL_BO", "MSN: OTHER_TASK"))
    window = MainWindow()
    window.show()
    try:
        assert not window.import_button.isEnabled()
        window.add_paths([str(good.parent)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert len(window.import_results) == 4
        assert window.progress.value() == 4
        assert "2 imported (1 with warnings), 2 failed" in window.statusBar().currentMessage()
        choose_path(window, good)
        assert window.review.choice_model.rowCount() == 4
        assert cell(window, 0, 0) == "0"
        assert cell(window, 0, 1) == "0.0"
        assert cell(window, 1, 3) == "No"
        assert cell(window, 1, 5) == "1.22"
        details = window.review.details.toPlainText()
        assert "Subject: 0007" in details
        assert "Task duration (S, seconds): 10.0" in details
        assert "Latency: unavailable" in details
        assert "A[0]: Match" in window.review.warnings.toPlainText()
        assert window.review.source.toPlainText() == good.read_text()
        assert window.review.details.isReadOnly()
        assert not (
            window.review.choice_model.flags(window.review.choice_model.index(0, 0))
            & Qt.ItemFlag.ItemIsEditable
        )
        choose_path(window, warning)
        assert (
            window.overview.model.rows[window.overview.model._row_by_path[warning]].quality
            == "Withheld"
        )
        assert cell(window, 1, 1) == "Unavailable"
        assert cell(window, 1, 2) == "Unavailable"
        assert "C[1]" in window.review.warnings.toPlainText()
        assert "A[0]: Unavailable" in window.review.warnings.toPlainText()
        choose_path(window, unsupported)
        assert window.review.choice_model.rowCount() == 0
        assert "OTHER_TASK" in window.review.details.toPlainText()
        assert "Unsupported PRL program" in window.review.warnings.toPlainText()
        assert window.review.source.toPlainText() == unsupported.read_text()
        choose_path(window, bad)
        assert window.review.choice_model.rowCount() == 0
        assert window.review.source.toPlainText() == ""
        assert "Expected a Med-PC" in window.review.warnings.toPlainText()
        assert (good.read_bytes(), good.stat().st_mtime_ns) == original
        window.clear_button.click()
        assert not window.import_results
        assert window.review.choice_model.rowCount() == 0
        assert not window.import_button.isEnabled()
    finally:
        window.close()


def test_reimport_failure_clears_stale_choices(app, write_export):
    path = write_export()
    window = MainWindow()
    try:
        window.add_paths([str(path)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert window.review.choice_model.rowCount() == 4
        path.unlink()
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert window.review.choice_model.rowCount() == 0
        assert window.import_results[path].session is None
        assert "could not read" in window.review.warnings.toPlainText()
    finally:
        window.close()


@pytest.mark.parametrize("close_window", [False, True])
def test_import_stays_responsive_and_cancels_between_files(
    app, write_export, monkeypatch, close_window
):
    first = write_export()
    second = first.with_name("z-next.txt")
    second.write_bytes(first.read_bytes())
    entered, release = ThreadEvent(), ThreadEvent()
    calls = []

    def controlled_import(path):
        assert QThread.currentThread() != app.thread()
        calls.append(path)
        entered.set()
        assert release.wait(5)
        return import_medpc_file(path)

    monkeypatch.setattr(worker_module, "import_medpc_file", controlled_import)
    window = MainWindow()
    window.show()
    try:
        window.add_paths([str(first), str(second)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, entered.is_set)
        assert not window.import_button.isEnabled()
        assert not window.clear_button.isEnabled()
        # Switching the reviewed file still works while I/O runs in the worker.
        choose_path(window, second)
        assert "No import result" in window.review.summary.text()
        if close_window:
            window.close()
            assert window.isVisible()  # Close is deferred until the worker returns.
        else:
            window.cancel_button.click()
            assert not window.cancel_button.isEnabled()
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        assert calls == [first]
        assert window.import_results[first].session is not None
        assert second not in window.import_results
        assert (
            "cancelled"
            in window.overview.model.rows[window.overview.model._row_by_path[second]].quality
        )
        if close_window:
            wait_until(app, lambda: not window.isVisible())
        else:
            assert window.import_button.isEnabled()
            assert "Cancelled" in window.statusBar().currentMessage()
    finally:
        release.set()
        wait_until(app, lambda: window._import_worker is None)
        window.close()


def test_unexpected_import_error_does_not_abort_other_files(app, write_export, monkeypatch):
    path = write_export()
    broken = path.with_name("a-broken.txt")
    broken.write_bytes(path.read_bytes())

    def fail_one(candidate):
        if candidate == broken:
            raise RuntimeError("Synthetic failure")
        return import_medpc_file(candidate)

    monkeypatch.setattr(worker_module, "import_medpc_file", fail_one)
    window = MainWindow()
    try:
        window.add_paths([str(broken), str(path)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert window.import_results[path].session is not None
        assert "Unexpected import failure" in window.import_results[broken].error
        assert window.import_button.isEnabled()
    finally:
        window.close()


def test_missing_files_and_invalid_extensions_are_visible(app, tmp_path, monkeypatch):
    window = MainWindow()
    try:
        window.add_paths([str(tmp_path / "absent.mat")])
        wait_for_discovery(app, window)
        assert window.issue_list.count() == 1
        warnings = []
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
        window.extensions.setText("")
        window.add_paths([str(tmp_path)])
        assert warnings
        assert window._worker is None
    finally:
        window.close()


def test_unexpected_worker_failure_keeps_selection_and_restores_controls(
    app, tmp_path, monkeypatch
):
    selected = tmp_path / "session.mat"
    selected.touch()
    window = MainWindow()
    try:
        window.add_paths([str(selected)])
        wait_for_discovery(app, window)

        def fail(*args, **kwargs):
            raise RuntimeError("Synthetic worker failure")

        warnings = []
        monkeypatch.setattr(window_module, "discover_files", fail)
        monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
        window.add_paths([str(tmp_path)])
        wait_for_discovery(app, window)
        assert window.selected_files == {selected}
        assert window.add_files_button.isEnabled()
        assert warnings and "Could not discover" in warnings[0]
    finally:
        window.close()


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
def test_gui_export_all_results_and_dialog_cancel(app, write_export, monkeypatch, export_format):
    import csv
    import json

    path = write_export()
    bad = path.with_name("bad.txt")
    bad.write_text("malformed export")
    before = path.read_bytes(), path.stat().st_mtime_ns
    window = MainWindow()
    button = window.excel_button if export_format == "xlsx" else window.export_button
    label = "Excel" if export_format == "xlsx" else "CSV"
    try:
        assert not button.isEnabled()
        window.add_paths([str(path), str(bad)])
        wait_for_discovery(app, window)
        assert not button.isEnabled()
        window.import_button.click()
        assert not button.isEnabled()
        wait_until(app, lambda: window._import_worker is None)
        assert button.isEnabled()
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: "")
        button.click()
        assert window._export_worker is None
        assert not list(path.parent.glob("trial-cruncher-export-*"))
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(path.parent))
        choose_path(window, bad)  # Export scope is all successes, not the highlighted file.
        button.click()
        wait_until(app, lambda: window._export_worker is None)
        (destination,) = path.parent.glob("trial-cruncher-export-*")
        if export_format == "xlsx":
            from openpyxl import load_workbook

            book = load_workbook(destination / "results.xlsx")
            header, *body = book["Sessions"].values
            rows = [dict(zip(header, row, strict=True)) for row in body]
            book.close()
        else:
            with (destination / "sessions.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        assert len(rows) == 1 and rows[0]["subject_id"] == "0007"
        manifest = json.loads((destination / "manifest.json").read_text())
        assert [entry["status"] for entry in manifest["inputs"]] == ["failed", "exported"]
        assert str(destination) in window.export_status.text()
        assert window.statusBar().currentMessage() == f"{label} export complete"
        assert (path.read_bytes(), path.stat().st_mtime_ns) == before
        window.clear_button.click()
        assert not button.isEnabled()
    finally:
        window.close()


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
@pytest.mark.parametrize("fail", [False, True])
def test_export_background_controls_failure_retry_and_close(
    app, write_export, monkeypatch, fail, export_format
):
    from trial_cruncher.exporters import export_import_results
    from trial_cruncher.gui import export_worker as export_module

    path = write_export()
    entered, release = ThreadEvent(), ThreadEvent()
    warnings = []

    def controlled_export(*args):
        assert QThread.currentThread() != app.thread()
        entered.set()
        assert release.wait(5)
        if fail:
            raise OSError("Synthetic export failure")
        return export_import_results(*args)

    monkeypatch.setattr(export_module, "export_import_results", controlled_export)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(path.parent))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    window = MainWindow()
    button = window.excel_button if export_format == "xlsx" else window.export_button
    label = "Excel" if export_format == "xlsx" else "CSV"
    window.show()
    try:
        window.add_paths([str(path)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        button.click()
        wait_until(app, entered.is_set)
        assert not button.isEnabled()
        assert not window.excel_button.isEnabled()
        assert not window.export_button.isEnabled()
        assert not window.import_button.isEnabled()
        assert not window.clear_button.isEnabled()
        assert not window.add_files_button.isEnabled()
        assert not window.cancel_button.isEnabled()
        # Programmatic calls are guarded as well as buttons.
        window.clear_selection()
        window.import_selected_files()
        window.add_paths([str(path)])
        assert window.selected_files == {path}
        assert window._import_worker is window._worker is None
        choose_path(window, path)
        assert window.review.choice_model.rowCount() == 4
        if not fail:
            window.close()
            assert window.isVisible()
        release.set()
        wait_until(app, lambda: window._export_worker is None)
        if fail:
            assert warnings and "Synthetic export failure" in warnings[0]
            assert button.isEnabled()
            assert window.review.choice_model.rowCount() == 4
            assert not list(path.parent.glob("trial-cruncher-export-*"))
            monkeypatch.setattr(export_module, "export_import_results", export_import_results)
            button.click()
            wait_until(app, lambda: window._export_worker is None)
            assert window.statusBar().currentMessage() == f"{label} export complete"
        else:
            wait_until(app, lambda: not window.isVisible())
            (destination,) = path.parent.glob("trial-cruncher-export-*")
            assert (destination / "manifest.json").exists()
    finally:
        release.set()
        wait_until(app, lambda: window._export_worker is None)
        window.close()


def test_session_metrics_display_withholding_zero_and_clear(app, write_export, monkeypatch):
    import csv
    import json

    from trial_cruncher.prl_metrics import DEFINITION_VERSION

    path = write_export()
    mismatch = path.with_name("mismatch.txt")
    mismatch.write_text(path.read_text().replace("2.00 2.00 4.00", "2.00 2.00 5.00"))
    empty = path.with_name("empty.txt")
    empty.write_text(
        "File: synthetic\nMSN: PRL_BO\nS: 0\nSubject: 0007\nC:\nA:\n  0: 0 0 0\nB:\n  0: 0 0 0 0\n"
    )
    bad = path.with_name("bad.txt")
    bad.write_text("Malformed synthetic input")
    window = MainWindow()
    assert f"definition {DEFINITION_VERSION}" in window.review.metric_note.text()
    window.show()
    try:
        window.add_paths([str(path), str(mismatch), str(empty), str(bad)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        choose_path(window, path)
        window.review.tabs.setCurrentWidget(window.review.metric_page)
        table = window.review.metric_table
        assert table.rowCount() == 7
        assert [table.item(row, 1).text() for row in range(6)] == [
            "4",
            "2",
            "2",
            "2",
            "2",
            "0.5000",
        ]
        assert table.item(0, 3).text() == "Available"
        assert "Valid decoded records: 4" in window.review.metric_diagnostics.toPlainText()
        choose_path(window, mismatch)
        assert [table.item(row, 1).text() for row in range(6)] == ["Unavailable"] * 6
        assert all("A[2]" in table.item(row, 4).text() for row in range(6))
        assert "Valid decoded records: 4" in window.review.metric_diagnostics.toPlainText()
        choose_path(window, empty)
        assert [table.item(row, 1).text() for row in range(6)] == ["0"] * 5 + ["Unavailable"]
        assert "zero recorded choices" in table.item(5, 4).text()
        choose_path(window, bad)
        assert table.rowCount() == 0
        assert window.review.metric_diagnostics.toPlainText() == "No calculated metrics available."
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(path.parent))
        window.export_button.click()
        wait_until(app, lambda: window._export_worker is None)
        (destination,) = path.parent.glob("trial-cruncher-export-*")
        with (destination / "sessions.csv").open(newline="") as stream:
            exported = {row["source_file"]: row for row in csv.DictReader(stream)}
        assert len(exported) == 3
        assert exported[str(path)]["prl.proportion_correct"] == "0.5"
        assert exported[str(empty)]["prl.choice_count"] == "0"
        assert exported[str(empty)]["prl.proportion_correct"] == ""
        assert exported[str(mismatch)]["prl.choice_count"] == ""
        assert (
            json.loads(exported[str(mismatch)]["metric_results_json"])[0]["status"] == "unavailable"
        )
        choose_path(window, path)
        assert table.rowCount() == 7
        path.unlink()
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        choose_path(window, path)
        assert table.rowCount() == 0  # No stale metrics after a failed re-read.
        window.clear_button.click()
        assert table.rowCount() == 0
    finally:
        window.close()


def test_metric_calculation_is_in_worker_and_failure_isolated(app, write_export, monkeypatch):
    from trial_cruncher import processing

    path = write_export()
    failed = path.with_name("a-failed.txt")
    failed.write_bytes(path.read_bytes())
    original = processing.calculate_prl_summary
    calls = []

    def calculate(session):
        assert QThread.currentThread() != app.thread()
        calls.append(session.source_file)
        if session.source_file == failed:
            raise RuntimeError("Synthetic metric calculation failure")
        return original(session)

    monkeypatch.setattr(processing, "calculate_prl_summary", calculate)
    window = MainWindow()
    try:
        window.add_paths([str(path), str(failed)])
        wait_for_discovery(app, window)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert calls == [failed, path]
        assert window.import_results[failed].error
        assert window.import_results[failed].summary is None
        choose_path(window, path)
        assert window.review.metric_table.rowCount() == 7
        assert window.import_results[path].summary.metrics[5].value == 0.5
        assert window.export_button.isEnabled()
    finally:
        window.close()
