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
