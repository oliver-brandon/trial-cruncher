"""Animal analysis web adapter exercises the same asynchronous analysis worker."""

import pytest
from qt_helpers import wait_until

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.gui.web_animal import apply, configuration, page
from trial_cruncher.gui.window import MainWindow


def test_analysis_preview_and_disable(app, phase_input):
    window = MainWindow()
    path = phase_input()
    try:
        window.add_paths([str(path)])
        wait_until(app, lambda: window._worker is None)
        window.phase_assignments = {path: "Reversal"}
        window.metadata_assignments = {path: AnalysisMetadata("A", "C", included=True)}
        window.import_selected_files()
        wait_until(app, lambda: window._import_worker is None)
        assert configuration(window)["cohorts"] == ["C"]
        apply(
            window,
            {
                "cohort": "C",
                "design": "within-subjects",
                "conditions": ["A"],
                "phases": ["Reversal"],
            },
        )
        wait_until(app, lambda: window._analysis_worker is None)
        assert configuration(window)["ready"]
        result = page(window, "animal_metrics.csv", 0, 10)
        assert result["rows"] and result["total"] >= len(result["rows"])
        with pytest.raises(ValueError):
            page(window, "other.csv", 0, 10)
        window.apply_metadata_assignments({path: AnalysisMetadata("B", "C", included=True)})
        assert not configuration(window)["ready"]
        with pytest.raises(ValueError, match="unavailable"):
            page(window, "animal_metrics.csv", 0, 10)
        apply(window, None)
        assert window.analysis_plan is None
    finally:
        window.close()


def test_changed_source_invalidates_preview(app, phase_input):
    window = MainWindow()
    path = phase_input()
    try:
        window.add_paths([str(path)])
        wait_until(app, lambda: window._worker is None)
        window.phase_assignments = {path: "Reversal"}
        window.metadata_assignments = {path: AnalysisMetadata("A", "C", included=True)}
        window.import_selected_files()
        wait_until(app, lambda: window._import_worker is None)
        apply(
            window,
            {
                "cohort": "C",
                "design": "within-subjects",
                "conditions": ["A"],
                "phases": ["Reversal"],
            },
        )
        wait_until(app, lambda: window._analysis_worker is None)
        window.invalidate_animal_preview()
        path.write_text(path.read_text() + "\n")
        apply(
            window,
            {
                "cohort": "C",
                "design": "within-subjects",
                "conditions": ["A"],
                "phases": ["Reversal"],
            },
        )
        wait_until(app, lambda: window._analysis_worker is None)
        state = configuration(window)
        assert not state["ready"]
        assert "re-import" in state["error"].lower()
        assert path in window._source_issues
    finally:
        window.close()
