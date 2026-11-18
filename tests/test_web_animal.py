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


def test_comparison_displays_assigned_conditions_values_and_reasons(app, phase_input):
    from trial_cruncher.aggregation import AnalysisPlan, build_analysis
    from trial_cruncher.processing import import_medpc_file

    results = {}

    def add(subject, condition, codes, *, excluded=False):
        path = phase_input(codes, name=f"file-{len(results)}.txt")
        path.write_text(path.read_text().replace("Subject: 0007", f"Subject: {subject}"))
        annotation = AnalysisMetadata(
            condition, "C", included=not excluded, inclusion_reason="Retest" if excluded else None
        )
        results[path] = import_medpc_file(path, "Reversal", annotation)

    add("001", "Vehicle_control", (7, 7))
    add("001", "Drug_A", (1, 1))
    add("002", "Vehicle_control", (1, 7))
    add("002", "Vehicle_control", (1,))
    add("002", "Drug_A", (7,), excluded=True)
    add("003", "Vehicle_control", (1, 7))
    plan = AnalysisPlan("C", "within-subjects", ("Vehicle_control", "Drug_A"), ("Reversal",))
    window = MainWindow()
    try:
        window.analysis_plan = plan
        window._web_analysis_tables = build_analysis(plan, results, list(results))
        shown = page(window, "condition_comparison.csv", 0, 100)
        columns = shown["headers"]
        vehicle = columns.index('["Vehicle_control", "Reversal"]')
        drug = columns.index('["Drug_A", "Reversal"]')
        subject = columns.index("subject_id")
        metric = columns.index("metric")
        groups = columns.index("treatment_group")
        assert shown["display_headers"][groups] == "Assigned conditions"
        assert shown["display_headers"][vehicle] == '["Vehicle_control", "Reversal"]'
        checked = set()
        for row_number, row in enumerate(shown["rows"]):
            if row[subject] == "001" and row[metric] == "Phase proportion correct":
                assert row[groups] == "Drug_A, Vehicle_control"
                assert float(row[vehicle]) == 0.0
                assert float(row[drug]) == 1.0
                checked.add("zero")
            if row[subject] == "002" and row[metric] == "Phase proportion correct":
                assert "Multiple Included" in row[vehicle]
                assert len(shown["cell_details"][row_number][vehicle].splitlines()) == 2
                assert row[drug] == "Excluded"
                assert "Source:" in shown["cell_details"][row_number][drug]
                checked.add("ambiguous")
            if row[subject] == "003" and row[metric] == "Phase proportion correct":
                assert row[drug] == "Missing selected recording"
                checked.add("missing")
            if row[subject] == "001" and row[metric] == "Win-stay, correct lever":
                assert "No eligible conditioning choices" in row[vehicle]
                assert shown["cell_details"][row_number][vehicle]
                checked.add("unavailable")
        assert checked == {"zero", "ambiguous", "missing", "unavailable"}
        between = AnalysisPlan(
            "C", "between-subjects", ("Vehicle_control", "Drug_A"), ("Reversal",)
        )
        window._web_analysis_tables = build_analysis(between, results, list(results))
        comparison = page(window, "condition_comparison.csv", 0, 100)
        row = next(
            row
            for row in comparison["rows"]
            if row[subject] == "003" and row[metric] == "Phase proportion correct"
        )
        assert row[drug] == "Outside group"
        audit = page(window, "analysis_audit.csv", 0, 10)
        assert audit["headers"][:5] == [
            "subject_id",
            "condition",
            "phase",
            "recording_proportion_correct",
            "disposition",
        ]
    finally:
        window.close()
