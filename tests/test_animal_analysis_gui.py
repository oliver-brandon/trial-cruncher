"""Offscreen user flow from reviewed input through plan selection, preview, export and reload."""

import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QTabWidget  # noqa: E402

from trial_cruncher.analysis_metadata import AnalysisMetadata  # noqa: E402
from trial_cruncher.gui.animal_analysis import AnalysisReview, PlanDialog  # noqa: E402
from trial_cruncher.gui.window import MainWindow  # noqa: E402


def test_configure_preview_save_load_export_disable(phase_input, tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    w = MainWindow()

    def wait(check):
        until = time.monotonic() + 8
        while not check() and time.monotonic() < until:
            app.processEvents()
            time.sleep(0.005)
        assert check()

    p = phase_input()
    try:
        w.add_paths([str(p)])
        wait(lambda: w._worker is None)
        w.phase_assignments = {p: "Reversal"}
        w.metadata_assignments = {p: AnalysisMetadata("A", "C", included=True)}
        w.import_selected_files()
        wait(lambda: w._import_worker is None)

        def configure():
            d = app.activeModalWidget()
            assert isinstance(d, PlanDialog)
            for widget in (d.conditions, d.phases):
                widget.item(0).setCheckState(Qt.CheckState.Checked)
            d.design.setCurrentText("within-subjects")
            d.accept()

        preview = []

        def review(self):
            preview.append(self.findChild(QTabWidget).count())
            return 1

        monkeypatch.setattr(AnalysisReview, "exec", review)
        QTimer.singleShot(0, configure)
        w.analysis_button.click()
        wait(lambda: bool(preview))
        assert preview == [4] and w.analysis_plan.phases == ("Reversal",)
        target = tmp_path / "example.tcproj.json"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(target), ""))
        w.save_project_button.click()
        wait(lambda: w._project_worker is None)
        w.clear_selection()
        assert w.analysis_plan is None
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(target), ""))
        w.open_project_button.click()
        wait(lambda: w._project_worker is None)
        assert w.analysis_plan.cohort == "C" and not w.import_results
        w.import_selected_files()
        wait(lambda: w._import_worker is None)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
        w.export_button.click()
        wait(lambda: w._export_worker is None)
        (out,) = tmp_path.glob("trial-cruncher-export-*")
        assert (
            json.loads((out / "manifest.json").read_text())["aggregation"]["plan_sha256"]
            == w.analysis_plan.sha256
        )
        QTimer.singleShot(0, lambda: app.activeModalWidget().disable())
        w.analysis_button.click()
        assert w.analysis_plan is None
    finally:
        w.close()


def test_legacy_project_empty_cohort_opens_metadata_editor(phase_input, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    from trial_cruncher.gui.metadata import MetadataDialog
    from trial_cruncher.projects import save_project

    app = QApplication.instance() or QApplication([])
    path = phase_input()
    target = tmp_path / "legacy.tcproj.json"
    save_project(target, [path], {path: "Reversal"}, {}, extensions=[".txt"], recursive=False)
    data = json.loads(target.read_text())
    data["schema_version"] = "1"
    del data["sources"][0]["analysis_metadata"]
    target.write_text(json.dumps(data))
    before = target.read_bytes()
    w = MainWindow()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(target), ""))
    try:
        w.open_project()
        deadline = time.monotonic() + 5
        while w._project_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert w.selected_files == {path}
        checks = []

        def edit_metadata():
            editor = app.activeModalWidget()
            if isinstance(editor, MetadataDialog):
                editor.editors[0].cohort.setText("Cohort 01")
                editor.editors[0].condition.setText("Control")
                editor.accept()

        def open_editor():
            dialog = app.activeModalWidget()
            checks.append((dialog.cohort.count(), dialog.cohort.placeholderText()))
            QTimer.singleShot(0, edit_metadata)
            next(
                b for b in dialog.findChildren(QPushButton) if b.text() == "Open session metadata…"
            ).click()

        QTimer.singleShot(0, open_editor)
        w.configure_analysis()
        assert checks == [(0, "Assign a cohort in Session metadata…")]
        assert w.metadata_assignments[path].cohort == "Cohort 01"

        def inspect():
            dialog = app.activeModalWidget()
            checks.append(dialog.cohort.currentText())
            dialog.reject()

        QTimer.singleShot(0, inspect)
        w.configure_analysis()
        assert checks[-1] == "Cohort 01"
        assert w.analysis_plan is None and target.read_bytes() == before
    finally:
        w.close()
