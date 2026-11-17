"""Invented PRL examples for within-cohort selection, pooling, pairing and persistence."""

import csv
import json
from dataclasses import replace

import pytest
from openpyxl import load_workbook

from trial_cruncher.aggregation import ACCURACY, ADJUSTED, SHEETS, AnalysisPlan, build_analysis
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.exporters import export_import_results
from trial_cruncher.phase_metrics import STRATEGIES
from trial_cruncher.prl_metrics import MEDPC_RATE
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.projects import load_project, save_project
from trial_cruncher.source_tracking import SourcesChangedError


@pytest.fixture
def batch(phase_input):
    results = {}

    def add(subject, condition, codes, phase="Reversal", cohort="C1", included=True, duration=60):
        path = phase_input(codes, name=f"source-{len(results)}.txt")
        text = (
            path.read_text()
            .replace("Subject: 0007", f"Subject: {subject}")
            .replace(f"S: {len(codes) + 1}", f"S: {duration}")
        )
        path.write_text(text)
        a = AnalysisMetadata(
            condition, cohort, None, included, "Retest" if included is False else None
        )
        results[path] = import_medpc_file(path, phase, a)
        return path

    return results, add


def plan(design="within-subjects", conditions=("A", "B"), phases=("Reversal",)):
    return AnalysisPlan("C1", design, conditions, phases)


def pool(t, metric, condition="A"):
    return next(
        r
        for r in t["pooled_metrics.csv"].to_dict("records")
        if r["metric"] == metric and r["condition"] == condition
    )


def comparison(t, subject, metric):
    return next(
        r
        for r in t["condition_comparison.csv"].to_dict("records")
        if r["metric"] == metric and r["subject_id"] == subject
    )


def test_pooled_evidence_and_individual_pairs(batch):
    results, add = batch
    add("007", "A", (1, 7))
    add("7", "A", (1,) * 9 + (7,), duration=180)
    add("007", "B", (7, 7))
    t = build_analysis(plan(), results, list(results))
    acc = pool(t, ACCURACY)
    assert (acc["sum_numerator"], acc["sum_denominator"], acc["valid_animal_n"]) == (10, 12, 2)
    assert acc["pooled_value"] == pytest.approx(10 / 12)
    rate = pool(t, MEDPC_RATE)
    assert (rate["sum_numerator"], rate["sum_denominator"], rate["pooled_value"]) == (12, 240, 3)
    a = comparison(t, "007", ACCURACY)
    assert a['["A", "Reversal"]'] == 0.5 and a['["B", "Reversal"]'] == 0
    assert a["complete"] and a["complete_animal_n"] == 1
    b = comparison(t, "7", ACCURACY)
    assert b['["A", "Reversal"]'] == 0.9 and b['["B", "Reversal"]'] is None and not b["complete"]
    adj = pool(t, ADJUSTED)
    assert adj["valid_animal_n"] == 1 and adj["zero_opportunity_n"] == 1
    assert adj["pooled_value"] == pytest.approx(1 / 7)
    reverse = build_analysis(plan(conditions=("B", "A")), results, list(results))
    assert comparison(reverse, "007", ACCURACY)['["A", "Reversal"]'] == 0.5


def test_audit_duplicate_selection_isolated_and_exclusions_preserved(batch, tmp_path):
    results, add = batch
    a = add("001", "A", (1, 7))
    add("001", "A", (1,))
    add("002", "A", (7, 7))
    b = add("002", "B", (1,), included=False)
    add("003", "A", (7,), included=None)
    paths = [*results, tmp_path / "pending"]
    t = build_analysis(plan(), results, paths)
    dispositions = {
        r["source_file"]: r["disposition"] for r in t["analysis_audit.csv"].to_dict("records")
    }
    assert "Multiple Included" in dispositions[str(a)]
    assert dispositions[str(b)] == "Excluded" and len(dispositions) == 6
    assert "Excluded" in comparison(t, "002", ACCURACY)["cell_evidence_json"]
    acc = pool(t, ACCURACY)
    assert (
        acc["candidate_sessions"] == 3
        and acc["ambiguous_animal_n"] == 1
        and acc["valid_animal_n"] == 1
    )
    results[a] = replace(
        results[a],
        analysis_metadata=AnalysisMetadata("A", "C1", included=False, inclusion_reason="Retest"),
    )
    assert pool(build_analysis(plan(), results, paths), ACCURACY)["valid_animal_n"] == 2


def test_between_design_pairs_phases_and_flags_conflicts(batch):
    results, add = batch
    add("001", "A", (1,), "Acquisition")
    add("001", "A", (7,))
    add("002", "B", (1, 1))
    add("003", "A", (1, 7))
    add("003", "B", (7, 1))
    add("004", "A", (1, 1))
    add("004", "B", (1,), cohort="C2")
    t = build_analysis(
        plan("between-subjects", phases=("Acquisition", "Reversal")), results, list(results)
    )
    a = comparison(t, "001", ACCURACY)
    assert a["complete"] and a["treatment_group"] == "A" and a["complete_animal_n"] == 1
    assert len(json.loads(a["required_cells_json"])) == 2
    assert not comparison(t, "002", ACCURACY)["complete"]
    assert "multiple between-subjects" in comparison(t, "003", ACCURACY)["cell_evidence_json"]
    assert "Conflicting cohort" in comparison(t, "004", ACCURACY)["cell_evidence_json"]


def test_metric_specific_missingness_and_strict_counts(batch):
    results, add = batch
    add("one", "A", (7,), duration=0)
    add("two", "A", (), duration=120)
    bad = add("three", "A", (1, 7))
    bad.write_text(bad.read_text().replace("0: 1 1 2", "0: 1 1 99"))
    results[bad] = import_medpc_file(bad, "Reversal", results[bad].analysis_metadata)
    t = build_analysis(plan(), results, list(results))
    acc = pool(t, ACCURACY)
    rate = pool(t, MEDPC_RATE)
    assert (
        acc["pooled_value"] == 0 and acc["valid_animal_n"] == 1 and acc["zero_opportunity_n"] == 1
    )
    assert (
        rate["pooled_value"] == 0 and rate["sum_denominator"] == 120 and rate["valid_animal_n"] == 1
    )
    assert rate["unavailable_n"] == 2
    assert pool(t, STRATEGIES[0])["pooled_value"] is None
    bad.write_text(bad.read_text() + "\n")
    with pytest.raises(SourcesChangedError):
        build_analysis(plan(), results, list(results))


@pytest.mark.parametrize("fmt", ["csv", "xlsx"])
def test_exports_and_plan_restore(batch, tmp_path, fmt):
    results, add = batch
    p = add("0001", "A", (1, 7))
    cfg = plan()
    project = tmp_path / "study.tcproj.json"
    save_project(
        project,
        [p],
        {p: "Reversal"},
        {},
        extensions=[".txt"],
        recursive=True,
        analysis_metadata={p: results[p].analysis_metadata},
        analysis_plan=cfg,
    )
    assert load_project(project).project.analysis_plan == cfg
    manifest_path = export_import_results(results, [p], tmp_path, fmt, analysis_plan=cfg)
    manifest = json.loads((manifest_path / "manifest.json").read_text())
    assert manifest["aggregation"]["plan_sha256"] == cfg.sha256
    if fmt == "csv":
        assert set(SHEETS) <= set(manifest["tables"])
        with (manifest_path / "pooled_metrics.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
    else:
        book = load_workbook(manifest_path / "results.xlsx")
        assert set(SHEETS.values()) <= set(book.sheetnames)
        head, *body = book["Pooled metrics"].values
        rows = [dict(zip(head, row, strict=True)) for row in body]
        book.close()
    assert (
        float(
            next(
                r["pooled_value"] for r in rows if r["metric"] == ACCURACY and r["condition"] == "A"
            )
        )
        == 0.5
    )
    data = json.loads(project.read_text())
    data["analysis_plan"]["pool"] = "average everything"
    project.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Unsupported aggregation"):
        load_project(project)


def test_pool_not_mean_rate_and_metric_specific_pair_counts(batch):
    results, add = batch
    add("x", "A", (1, 7), duration=60)
    add("y", "A", (1,) * 18, duration=180)
    add("x", "B", (7, 7))
    add("y", "A", (1,), "Acquisition")
    t = build_analysis(plan(phases=("Acquisition", "Reversal")), results, list(results))
    row = next(
        r
        for r in t["pooled_metrics.csv"].to_dict("records")
        if (r["metric"], r["condition"], r["phase"]) == (MEDPC_RATE, "A", "Reversal")
    )
    assert row["pooled_value"] == 5 and row["sum_numerator"] == 20 and row["sum_denominator"] == 240
    r = comparison(t, "x", ACCURACY)
    assert r["complete_animal_n"] == 0
    assert any(
        s["cells"] == [["A", "Reversal"], ["B", "Reversal"]] and s["complete_animal_n"] == 1
        for s in json.loads(r["pair_coverage_json"])
    )
    assert json.loads(r["cell_evidence_json"])['["A", "Reversal"]']["valid_animal_n"] == 2


def test_duplicate_hash_and_missing_keys(batch):
    results, add = batch
    a = add("007", "A", (1,))
    b = add("007", "B", (1,))
    add("other", None, (7,))
    t = build_analysis(plan(), results, list(results))
    dispositions = dict(
        zip(t["analysis_audit.csv"].source_file, t["analysis_audit.csv"].disposition, strict=True)
    )
    assert dispositions[str(a)] == dispositions[str(b)] == "Duplicate Included source content"
    assert "Missing subject, cohort, condition, or imported phase" in dispositions.values()
    assert t["animal_metrics.csv"].empty


def test_strategy_pools_use_conditioning_opportunities_and_keep_genuine_zero(batch):
    results, add = batch
    add("007", "A", (1, 7))  # Correct win-stay 0/1
    add("008", "A", (1, 1, 1))  # Correct win-stay 2/2
    add("009", "A", (7,))  # No next choice
    tables = build_analysis(plan(), results, list(results))
    row = pool(tables, STRATEGIES[0])
    assert (row["sum_numerator"], row["sum_denominator"]) == (2, 3)
    assert row["pooled_value"] == pytest.approx(2 / 3)
    assert row["valid_animal_n"] == 2 and row["zero_opportunity_n"] == 1
    assert comparison(tables, "007", STRATEGIES[0])['["A", "Reversal"]'] == 0


def test_preview_rejects_stale_metric_definition(batch):
    results, add = batch
    path = add("007", "A", (1, 7))
    result = results[path]
    results[path] = replace(result, summary=replace(result.summary, definition_version="obsolete"))
    with pytest.raises(ValueError, match="re-import"):
        build_analysis(plan(), results, list(results))
