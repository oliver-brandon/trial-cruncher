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
    window.file_list.setCurrentItem(window._items[path])


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
        assert window.file_list.count() == 1
        assert window.add_files_button.isEnabled()
        window.clear_button.click()
        assert window.file_list.count() == 0
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
        assert "Warnings" in window._items[warning].text()
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
        assert "cancelled" in window._items[second].text()
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
