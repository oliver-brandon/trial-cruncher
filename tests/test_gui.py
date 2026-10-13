import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from trial_cruncher.gui import window as window_module  # noqa: E402
from trial_cruncher.gui.window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for_discovery(app, window):
    deadline = time.monotonic() + 5
    while window._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window._worker is None, "Discovery worker did not finish"


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
