"""Offscreen user flow from reviewed input through plan selection, preview, export and reload."""

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QTabWidget
from qt_helpers import answer_dialog, wait_until

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.gui.animal_analysis import AnalysisReview, PlanDialog
from trial_cruncher.gui.window import MainWindow


def test_configure_preview_save_load_export_disable(app, phase_input, tmp_path, monkeypatch):
    w = MainWindow()

    p = phase_input()
    try:
        w.add_paths([str(p)])
        wait_until(app, lambda: w._worker is None)
        w.phase_assignments = {p: "Reversal"}
        w.metadata_assignments = {p: AnalysisMetadata("A", "C", included=True)}
        w.import_selected_files()
        wait_until(app, lambda: w._import_worker is None)

        def configure(d):
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
        with answer_dialog(monkeypatch, PlanDialog, configure):
            w.analysis_button.click()
        wait_until(app, lambda: bool(preview))
        assert preview == [4] and w.analysis_plan.phases == ("Reversal",)
        target = tmp_path / "example.tcproj.json"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **kw: (str(target), ""))
        w.save_project_button.click()
        wait_until(app, lambda: w._project_worker is None)
        w.clear_selection()
        assert w.analysis_plan is None
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(target), ""))
        w.open_project_button.click()
        wait_until(app, lambda: w._project_worker is None)
        assert w.analysis_plan.cohort == "C" and not w.import_results
        w.import_selected_files()
        wait_until(app, lambda: w._import_worker is None)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(tmp_path))
        w.export_button.click()
        wait_until(app, lambda: w._export_worker is None)
        (out,) = tmp_path.glob("trial-cruncher-export-*")
        assert (
            json.loads((out / "manifest.json").read_text())["aggregation"]["plan_sha256"]
            == w.analysis_plan.sha256
        )
        with answer_dialog(monkeypatch, PlanDialog, lambda d: d.disable()):
            w.analysis_button.click()
        assert w.analysis_plan is None
    finally:
        w.close()


def test_legacy_project_empty_cohort_opens_metadata_editor(app, phase_input, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QPushButton

    from trial_cruncher.gui.metadata import MetadataDialog
    from trial_cruncher.projects import save_project

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
        wait_until(app, lambda: w._project_worker is None)
        assert w.selected_files == {path}
        checks = []

        def edit_metadata(editor):
            editor.editors[0].cohort.setText("Cohort 01")
            editor.editors[0].condition.setText("Control")
            editor.accept()

        def open_editor(dialog):
            checks.append((dialog.cohort.count(), dialog.cohort.placeholderText()))
            next(
                b for b in dialog.findChildren(QPushButton) if b.text() == "Open session metadata…"
            ).click()

        with (
            answer_dialog(monkeypatch, PlanDialog, open_editor),
            answer_dialog(monkeypatch, MetadataDialog, edit_metadata),
        ):
            w.configure_analysis()
        assert checks == [(0, "Assign a cohort in Session metadata…")]
        assert w.metadata_assignments[path].cohort == "Cohort 01"

        def inspect(dialog):
            checks.append(dialog.cohort.currentText())
            dialog.reject()

        with answer_dialog(monkeypatch, PlanDialog, inspect):
            w.configure_analysis()
        assert checks[-1] == "Cohort 01"
        assert w.analysis_plan is None and target.read_bytes() == before
    finally:
        w.close()
