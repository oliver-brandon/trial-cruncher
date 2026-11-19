"""Descriptive within-project analyses of reviewed, explicitly included recordings."""

import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from itertools import product
from pathlib import Path

import pandas as pd

from trial_cruncher import phase_metrics, prl_metrics
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.analysis_plan import VERSION as VERSION
from trial_cruncher.analysis_plan import AnalysisPlan
from trial_cruncher.analysis_sort import SHEETS as SHEETS
from trial_cruncher.processing import ImportResult, validate_reviewed_result
from trial_cruncher.source_tracking import require_current_sources
from trial_cruncher.tables import json_text

ALL_METRICS = (*prl_metrics.METRIC_LABELS, *phase_metrics.METRIC_LABELS)
ACCURACY = "prl.phase.proportion_correct"
ADJUSTED = "prl.phase.adjusted_regressive_error_proportion"
# Display the unscaled evidence sums, including choices and seconds for the rate.
POOL_UNITS = {
    ACCURACY: ("correct choices", "choices", "proportion"),
    ADJUSTED: ("regressive errors", "postcriterion choices", "proportion"),
    **{name: ("successes", "eligible pairs", "probability") for name in phase_metrics.STRATEGIES},
    prl_metrics.MEDPC_RATE: ("choices", "seconds", "choices/min"),
}


def _individual_rows(result):
    phase = result.phase_summary
    summary = result.summary
    d = phase.diagnostics
    evidence = {
        name: (pair.numerator, pair.denominator)
        for name, pair in zip(phase_metrics.STRATEGIES, phase.strategies, strict=True)
    }
    evidence[ADJUSTED] = (d.adjusted_regressive.numerator, d.adjusted_regressive.denominator)
    evidence[ACCURACY] = (d.correct_choice_count, d.valid_choice_count)
    evidence["prl.proportion_correct"] = evidence[ACCURACY]
    evidence[prl_metrics.MEDPC_RATE] = (summary.metrics[0].value, result.session.duration_s)
    for metric in (*summary.metrics, *phase.metrics):
        num, den = evidence.get(metric.name, (None, None))
        yield {
            "metric": metric.name,
            "value": metric.value,
            "unit": metric.unit,
            "status": metric.status,
            "reasons": json_text(metric.reasons),
            "warnings": json_text(metric.warnings),
            "source_definition_version": metric.definition_version,
            "numerator": num,
            "denominator": den,
            "criterion_reached": d.criterion_reached,
            "criterion_choice_ordinal": d.criterion_choice_ordinal,
            "criterion_source_index": d.criterion_source_index,
            "postcriterion_choices": d.postcriterion_choice_count,
        }


def _frame(rows, columns):
    # Keep nullable integer/boolean observations intact through Excel serialization.
    return pd.DataFrame([[r.get(k) for k in columns] for r in rows], columns=columns, dtype=object)


def build_analysis(
    plan: AnalysisPlan,
    results: Mapping[Path, ImportResult],
    paths: Sequence[Path],
    assignments: Mapping[Path, AnalysisMetadata] | None = None,
) -> dict[str, pd.DataFrame]:
    """Build fresh derived rows from one reviewed batch. Verify source bytes before analysis."""
    paths = sorted(set(paths), key=str)
    require_current_sources(
        {p: results[p].raw["source_sha256"] for p in paths if p in results and results[p].raw}
    )
    audit, cells, groups, hashes = _candidates(plan, results, paths, assignments)
    individual, observed, blocked = _select_metrics(plan, results, cells, groups, hashes)
    pooled = _pool(plan, cells, observed, blocked)
    comparison, labels = _compare(plan, audit, groups, observed, blocked)
    return _tables(audit, individual, pooled, comparison, labels)


def _candidates(plan, results, paths, assignments):
    audit = []
    cells = defaultdict(list)
    groups = defaultdict(set)
    hashes = Counter()
    for path in paths:
        r = results.get(path)
        if r and r.session and not r.error:
            validate_reviewed_result(r)
        a = r.analysis_metadata if r else (assignments or {}).get(path, AnalysisMetadata())
        raw = r.raw if r else None
        subject = raw["headers"].get("Subject") if raw else None
        digest = raw["source_sha256"] if raw else None
        phase = r.phase_summary.config.phase if r and r.phase_summary else None
        reason = None
        if a.included is not True:
            reason = a.inclusion_status
        elif not r or r.error or not r.session or not r.summary or not r.phase_summary:
            reason = (r.error if r else None) or "Import required"
        elif not all((subject, a.condition, phase)):
            reason = "Missing subject, condition, or imported phase"
        elif a.condition not in plan.conditions or phase not in plan.phases:
            reason = "Outside selected scope"
        item = {
            "source_file": str(path),
            "source_sha256": digest,
            "subject_id": subject,
            "condition": a.condition,
            "phase": phase,
            "inclusion": a.inclusion_status,
            "inclusion_reason": a.inclusion_reason,
            "metadata_sha256": a.sha256,
            "phase_configuration_sha256": r.phase_summary.config.sha256
            if r and r.phase_summary
            else None,
            "import_status": "not_imported" if not r else "failed" if r.error else "imported",
            "import_error": r.error if r else None,
            "disposition": reason or "candidate",
            "metric_status_json": json_text(
                {
                    m.name: {"status": m.status, "reasons": m.reasons}
                    for m in (*r.summary.metrics, *r.phase_summary.metrics)
                }
            )
            if r and r.summary and r.phase_summary
            else None,
        }
        audit.append(item)
        if reason is None:
            cells[subject, a.condition, phase].append(item)
            groups[subject].add(a.condition)
            hashes[digest] += 1
    return audit, cells, groups, hashes


def _select_metrics(plan, results, cells, groups, hashes):
    individual = []
    observed = {}
    blocked = {}
    for (subject, condition, phase), items in cells.items():
        issues = []
        if len(items) > 1:
            issues.append("Multiple Included recordings for this cell")
        if plan.design == "between-subjects" and len(groups[subject]) > 1:
            issues.append("Animal assigned to multiple between-subjects conditions")
        if any(hashes[i["source_sha256"]] > 1 for i in items):
            issues.append("Duplicate Included source content")
        if issues:
            blocked[subject, condition, phase] = ". ".join(issues)
            for item in items:
                item["disposition"] = blocked[subject, condition, phase]
            continue
        (item,) = items
        item["disposition"] = "selected"
        for m in _individual_rows(results[Path(item["source_file"])]):
            row = {
                **{
                    k: item[k]
                    for k in (
                        "subject_id",
                        "condition",
                        "phase",
                        "source_file",
                        "source_sha256",
                        "phase_configuration_sha256",
                        "metadata_sha256",
                    )
                },
                **m,
            }
            individual.append(row)
            observed[subject, condition, phase, m["metric"]] = row
    return individual, observed, blocked


def _pool(plan, cells, observed, blocked):
    animals_by_cell = defaultdict(list)
    for subject, condition, phase in cells:
        animals_by_cell[condition, phase].append(subject)
    pooled = []
    for condition, phase in product(plan.conditions, plan.phases):
        animals = sorted(animals_by_cell[condition, phase])
        n_files = sum(len(cells[a, condition, phase]) for a in animals)
        for metric, (num_unit, den_unit, unit) in POOL_UNITS.items():
            rows = [
                observed[a, condition, phase, metric]
                for a in animals
                if (a, condition, phase, metric) in observed
            ]
            valid = [r for r in rows if r["value"] is not None and r["denominator"] > 0]
            zero = sum(
                r["denominator"] == 0 and r["numerator"] == 0
                for r in rows
                if metric != prl_metrics.MEDPC_RATE
            )
            numerator = sum(r["numerator"] for r in valid)
            denominator = sum(r["denominator"] for r in valid)
            scale = 60 if metric == prl_metrics.MEDPC_RATE else 1
            row = {
                "condition": condition,
                "phase": phase,
                "metric": metric,
                "pooled_value": scale * numerator / denominator
                if denominator and math.isfinite(denominator)
                else None,
                "unit": unit,
                "sum_numerator": numerator if valid or zero else None,
                "numerator_unit": num_unit,
                "sum_denominator": denominator
                if (valid or zero) and math.isfinite(denominator)
                else None,
                "denominator_unit": den_unit,
                "scale": scale,
                "candidate_sessions": n_files,
                "candidate_animals": len(animals),
                "selected_sessions": len(rows),
                "valid_animal_n": len(valid),
                "zero_opportunity_n": zero,
                "unavailable_n": len(rows) - len(valid) - zero,
                "ambiguous_animal_n": len(animals) - len(rows),
                "reason": "Duration sum exceeds numeric range"
                if not math.isfinite(denominator)
                else None
                if valid
                else "No eligible positive denominator",
                "contributors_json": json_text([r["source_file"] for r in valid]),
                "omitted_json": json_text(
                    [
                        {
                            "subject_id": a,
                            "sources": [i["source_file"] for i in cells[a, condition, phase]],
                            "reason": blocked.get((a, condition, phase))
                            or json.loads(observed[a, condition, phase, metric]["reasons"]),
                        }
                        for a in animals
                        if (a, condition, phase, metric) not in observed
                        or observed[a, condition, phase, metric]["value"] is None
                    ]
                ),
            }
            pooled.append(row)
    return pooled


def _compare(plan, audit, groups, observed, blocked):
    sources = defaultdict(list)
    for item in audit:
        sources[item["subject_id"], item["condition"], item["phase"]].append(item)
    coverage = Counter()
    for (_, condition, phase, metric), record in observed.items():
        if record["value"] is not None:
            coverage[condition, phase, metric] += 1
    comparison = []
    keys = list(product(plan.conditions, plan.phases))
    labels = {key: json_text(key) for key in keys}
    for subject in sorted(groups):
        expected = [
            key for key in keys if plan.design == "within-subjects" or key[0] in groups[subject]
        ]
        required_cells = json_text(expected)
        axes = [[key for key in expected if key[0] == c] for c in plan.conditions]
        if plan.design == "within-subjects":
            axes.extend([key for key in expected if key[1] == p] for p in plan.phases)
        subsets = [
            (json_text(axis), [labels[key] for key in axis]) for axis in axes if len(axis) > 1
        ]
        for metric in ALL_METRICS:
            row = {
                "subject_id": subject,
                "design": plan.design,
                "metric": metric,
                "treatment_group": next(iter(groups[subject]))
                if len(groups[subject]) == 1
                else None,
            }
            details = {}
            for c, p in expected:
                record = observed.get((subject, c, p, metric))
                row[labels[c, p]] = record["value"] if record else None
                matches = sources[subject, c, p]
                issues = [i["disposition"] for i in matches]
                details[labels[c, p]] = {
                    "valid_animal_n": coverage[c, p, metric],
                    "sources": [
                        i["source_file"]
                        for i in matches
                        if record is None or i["disposition"] == "selected"
                    ],
                    "reasons": json.loads(record["reasons"])
                    if record
                    else (
                        [blocked[subject, c, p]]
                        if (subject, c, p) in blocked
                        else issues or ["Missing selected recording"]
                    ),
                }
            row["required_cells_json"] = required_cells
            row["complete"] = all(row[labels[key]] is not None for key in expected)
            row["cell_evidence_json"] = json_text(details)
            row["pair_sets"] = {
                key: all(row[label] is not None for label in columns) for key, columns in subsets
            }
            comparison.append(row)
    complete_n = Counter(
        (r["metric"], r["required_cells_json"]) for r in comparison if r["complete"]
    )
    subset_n = Counter(
        (r["metric"], k) for r in comparison for k, complete in r["pair_sets"].items() if complete
    )
    for r in comparison:
        r["pair_coverage_json"] = json_text(
            [
                {
                    "cells": json.loads(k),
                    "complete": complete,
                    "complete_animal_n": subset_n[r["metric"], k],
                }
                for k, complete in r.pop("pair_sets").items()
            ]
        )
        r["complete_animal_n"] = complete_n[r["metric"], r["required_cells_json"]]
    return comparison, labels


def _tables(audit, individual, pooled, comparison, labels):
    cols = (
        "subject_id",
        "condition",
        "phase",
        "metric",
        "value",
        "unit",
        "status",
        "reasons",
        "warnings",
        "numerator",
        "denominator",
        "criterion_reached",
        "criterion_choice_ordinal",
        "criterion_source_index",
        "postcriterion_choices",
        "source_file",
        "source_sha256",
        "source_definition_version",
        "metadata_sha256",
        "phase_configuration_sha256",
    )
    return {
        "analysis_audit.csv": _frame(
            audit, tuple(audit[0]) if audit else ("source_file", "disposition")
        ),
        "animal_metrics.csv": _frame(individual, cols),
        "condition_comparison.csv": _frame(
            comparison,
            (
                "subject_id",
                "design",
                "treatment_group",
                "metric",
                *labels.values(),
                "complete",
                "complete_animal_n",
                "required_cells_json",
                "cell_evidence_json",
                "pair_coverage_json",
            ),
        ),
        "pooled_metrics.csv": _frame(pooled, tuple(pooled[0])),
    }
