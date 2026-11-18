"""Exercise the main-window workflow and pane sizing on a laptop-sized window."""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog
from qt_helpers import wait_until

from trial_cruncher.gui.window import MainWindow


def test_import_review_export_and_full_height_views(app, phase_input, tmp_path, monkeypatch):
    path = phase_input()
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a: ([str(path)], ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
    w = MainWindow()
    w.resize(1180, 720)
    w.show()

    def click(widget):
        assert widget.isVisible() and widget.isEnabled()
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        app.processEvents()

    try:
        assert w.height() == 720 and w.workflow.currentWidget() is w.import_page
        click(w.options_button)
        assert w.extensions.isVisible() and w.clear_button.isVisible()
        click(w.options_button)
        click(w.add_files_button)
        wait_until(app, lambda: w._worker is None)
        click(w.import_button)
        wait_until(app, lambda: w._import_worker is None)
        assert w.workflow.currentWidget() is w.review_page
        assert not w.progress.isVisible() and not w.cancel_button.isVisible()
        w.overview.select_path(path)
        w.review.tabs.setCurrentWidget(w.review.metric_page)
        app.processEvents()
        batch_height = w.overview.table.viewport().height()
        detail_height = w.review.metric_table.viewport().height()
        assert batch_height > 90 and detail_height > 70
        w.view_mode.setCurrentText("Batch only")
        app.processEvents()
        assert w.overview.table.viewport().height() > batch_height + 100
        w.view_mode.setCurrentText("Detail only")
        app.processEvents()
        assert w.review.metric_table.viewport().height() > detail_height + 100
        click(w.review.metric_diagnostics_toggle)
        assert w.review.metric_diagnostics.isVisible()
        w.view_mode.setCurrentText("Split view")
        assert w.overview.current_path() == path and w.review.metric_table.rowCount() == 7
        click(w.go_to_export)
        click(w.export_button)
        wait_until(app, lambda: w._export_worker is None)
        assert "Saved" in w.export_status.text() and list(tmp_path.glob("*/sessions.csv"))
        w.issue_list.addItem("Example file message")
        assert w.messages_button.text() == "Messages (1)"
        click(w.messages_button)
        assert w.issue_list.isVisible()
        w.workflow.setCurrentWidget(w.project_page)
        assert w.open_project_button.isVisible()
    finally:
        w.close()
