"""Offscreen project save/load, stale source handling, and worker lifecycle."""

import json
from threading import Event

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QFileDialog, QMessageBox
from qt_helpers import wait_until

from trial_cruncher.gui import project_worker
from trial_cruncher.gui.window import MainWindow
from trial_cruncher.source_tracking import source_sha256


def add_import(app, window, paths):
    window.add_paths([str(p) for p in paths])
    wait_until(app, lambda: window._worker is None)
    window.phase_assignments = {p: f"Phase {i}" for i, p in enumerate(paths)}
    window.import_button.click()
    wait_until(app, lambda: window._import_worker is None)


def test_percentage_project_load_notifies_and_reimports_as_proportions(
    app, phase_input, tmp_path, monkeypatch
):
    from trial_cruncher.projects import save_project

    p = phase_input((1, 7))
    target = tmp_path / "old.tcproj.json"
    save_project(target, [p], {p: "Reversal"}, {}, extensions=[".txt"], recursive=False)
    data = json.loads(target.read_text())
    data["analysis_configuration"]["session_definition_version"] = "2"
    data["analysis_configuration"]["phase_definition_version"] = "1"
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(target), ""))
    window = MainWindow()
    try:
        window.open_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert "proportions" in window.statusBar().currentMessage()
        assert window._project_dirty and target.read_bytes() == before
        assert not window.import_results and not window.export_button.isEnabled()
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        window.overview.select_path(p)
        assert window.review.metric_table.item(5, 1).text() == "0.5000"
        assert window.review.phase_table.item(0, 1).text() == "0.5000"
        assert window.review.metric_table.item(5, 0).text() == "Proportion correct"
        assert window.review.phase_table.item(0, 0).text() == "Proportion correct"
        window.save_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert not window._project_dirty
        assert (
            json.loads(target.read_text())["analysis_configuration"]["session_definition_version"]
            == "4"
        )
    finally:
        window.close()


def test_save_load_restores_phases_settings_and_changed_missing_paths(
    app, phase_input, tmp_path, monkeypatch
):
    a = phase_input(name="a/same.txt")
    b = phase_input(name="b/same.txt")
    original_a = a.read_bytes()
    target = tmp_path / "study.tcproj.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(target), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args)))
    window = MainWindow()
    try:
        add_import(app, window, [a, b])
        # Persist pending phase assignments, not the old imported labels.
        window.phase_assignments = {a: "Acquisition", b: "Reversal 2 μ"}
        window.extensions.setText(".txt, .med")
        window.recursive.setChecked(False)
        window.save_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        saved = json.loads(target.read_text())
        assert window._project_path == target and not window._project_dirty
        assert {s["path"]: s["phase"] for s in saved["sources"]} == {
            str(a): "Acquisition",
            str(b): "Reversal 2 μ",
        }
        assert saved["sources"][0]["sha256"] == source_sha256(a)
        window.clear_selection()
        a.unlink()
        b.write_text(b.read_text().replace("0007", "0008"))
        window.open_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert window.selected_files == {a, b}
        assert window.phase_assignments == {a: "Acquisition", b: "Reversal 2 μ"}
        assert window.extensions.text() == ".med, .txt" and not window.recursive.isChecked()
        assert not window.import_results and not window.export_button.isEnabled()
        assert "missing" in window._source_issues[a].lower()
        assert "changed" in window._source_issues[b].lower()
        assert all(row.quality == "Re-import required" for row in window.overview.model.rows)
        window.overview.select_path(b)
        assert window.review.metric_table.rowCount() == window.review.phase_table.rowCount() == 0
        assert "changed" in window.review.summary.text().lower()
        a.write_bytes(original_a)
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        assert not window._source_issues and window.export_button.isEnabled()
        assert window.import_results[b].phase_summary.config.phase == "Reversal 2 μ"
        assert window.import_results[b].session.subject_id == "0008"
        assert window._project_dirty
        window.save_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        refreshed = json.loads(target.read_text())
        assert {s["path"]: s["sha256"] for s in refreshed["sources"]} == {
            str(p): source_sha256(p) for p in (a, b)
        }
        # Even unchanged project load requires an explicit import; no result cache.
        window.open_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert not window.import_results and not window._source_issues
        assert not window.export_button.isEnabled()
        assert "import required" in window.statusBar().currentMessage()
    finally:
        window.close()


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_export_stale_file_clears_review_then_reimport_recovers(
    app, phase_input, tmp_path, monkeypatch, format
):
    p = phase_input()
    window = MainWindow()
    warnings = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    try:
        add_import(app, window, [p])
        window.overview.select_path(p)
        assert window.review.phase_table.rowCount() == 8
        p.write_text(p.read_text().replace("0007", "0008"))
        button = window.excel_button if format == "xlsx" else window.export_button
        button.click()
        wait_until(app, lambda: window._export_worker is None)
        assert warnings and "re-import" in warnings[0]
        assert p not in window.import_results
        assert window.review.phase_table.rowCount() == window.review.metric_table.rowCount() == 0
        assert not button.isEnabled()
        assert not list(tmp_path.glob("trial-cruncher-export-*"))
        assert window.overview.model.rows[0].quality == "Re-import required"
        window.import_button.click()
        wait_until(app, lambda: window._import_worker is None)
        button.click()
        wait_until(app, lambda: window._export_worker is None)
        assert len(list(tmp_path.glob("trial-cruncher-export-*"))) == 1
        assert window.import_results[p].session.subject_id == "0008"
    finally:
        window.close()


def test_check_and_save_invalidate_changed_source_without_advancing_baseline(
    app, phase_input, tmp_path, monkeypatch
):
    p = phase_input()
    target = tmp_path / "study.tcproj.json"
    window = MainWindow()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    try:
        add_import(app, window, [p])
        baseline = window._source_hashes[p]
        p.write_text(p.read_text().replace("0007", "0008"))
        window.save_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert json.loads(target.read_text())["sources"][0]["sha256"] == baseline
        assert not window.import_results and "changed" in window._source_issues[p]
        window.check_sources_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert window._source_hashes[p] == baseline
        assert not window.export_button.isEnabled()
        assert "changed" in window.overview.model.rows[0].tooltip(1).lower()
    finally:
        window.close()


def test_cancel_and_bad_project_keep_current_setup(app, phase_input, tmp_path, monkeypatch):
    p = phase_input()
    target = tmp_path / "broken.tcproj.json"
    target.write_text("broken")
    window = MainWindow()
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    try:
        add_import(app, window, [p])
        original = dict(window.import_results)
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
        window.save_project_button.click()
        assert window._project_worker is None
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", ""))
        window.open_project_button.click()
        assert window._project_worker is None
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(target), "")
        )
        window.open_project_button.click()
        wait_until(app, lambda: window._project_worker is None)
        assert warnings and window.import_results == original
        assert window.phase_assignments == {p: "Phase 0"}
        assert window.selected_files == {p} and window._project_path is None
    finally:
        window.close()


@pytest.mark.parametrize("fail", [False, True])
def test_project_io_background_busy_failure_retry_and_close(
    app, phase_input, tmp_path, monkeypatch, fail
):
    p = phase_input()
    target = tmp_path / "study.tcproj.json"
    entered, release = Event(), Event()
    real_save = project_worker.save_project
    warnings = []

    def controlled(*args, **kwargs):
        assert QThread.currentThread() != app.thread()
        entered.set()
        assert release.wait(5)
        if fail:
            raise OSError("Synthetic save failure")
        return real_save(*args, **kwargs)

    monkeypatch.setattr(project_worker, "save_project", controlled)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    window = MainWindow()
    window.show()
    try:
        add_import(app, window, [p])
        window.save_project_button.click()
        wait_until(app, entered.is_set)
        for widget in (
            window.import_button,
            window.phase_button,
            window.open_project_button,
            window.save_project_button,
            window.clear_button,
            window.export_button,
        ):
            assert not widget.isEnabled()
        window.import_selected_files()
        window.clear_selection()
        window.check_source_files()
        assert window._import_worker is None and window.selected_files == {p}
        if not fail:
            window.close()
            assert window.isVisible()
        release.set()
        wait_until(app, lambda: window._project_worker is None)
        if fail:
            assert warnings and window.import_results[p].session is not None
            assert window._project_path is None and not target.exists()
            monkeypatch.setattr(project_worker, "save_project", real_save)
            window.save_project_button.click()
            wait_until(app, lambda: window._project_worker is None)
            assert target.exists()
        else:
            wait_until(app, lambda: not window.isVisible())
            assert target.exists()
    finally:
        release.set()
        wait_until(app, lambda: window._project_worker is None)
        window.close()
