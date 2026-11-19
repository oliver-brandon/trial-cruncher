"""Web-facing animal analysis configuration and paged review."""

import json
from pathlib import Path

import pandas as pd

from trial_cruncher.analysis_plan import AnalysisPlan
from trial_cruncher.analysis_sort import SHEETS
from trial_cruncher.gui.animal_analysis import METRIC_TITLES, AnalysisModel
from trial_cruncher.gui.window import MainWindow


def configuration(window: MainWindow) -> dict:
    annotations = window.metadata_assignments.values()
    plan = window.analysis_plan
    tables = window._web_analysis_tables
    audit = tables["analysis_audit.csv"] if tables is not None else None
    return {
        "selected_count": int(audit["disposition"].eq("selected").sum())
        if audit is not None
        else 0,
        "audit_count": len(audit) if audit is not None else 0,
        "conditions": sorted(
            {a.condition for a in annotations if a.condition}
            | (set(plan.conditions) if plan else set())
        ),
        "phases": sorted(
            {
                r.phase_summary.config.phase
                for r in window.import_results.values()
                if r.phase_summary and r.phase_summary.config.phase
            }
            | (set(plan.phases) if plan else set()),
            key=lambda label: ({"acquisition": 0, "reversal": 1}.get(label.casefold(), 2), label),
        ),
        "plan": plan.record() if plan else None,
        "busy": window._analysis_worker is not None,
        "ready": getattr(window, "_web_analysis_tables", None) is not None,
        "error": getattr(window, "_web_analysis_error", None),
    }


def apply(window: MainWindow, payload: object) -> None:
    if payload is None:
        window.apply_analysis_plan(None, web=True)
        return
    if not isinstance(payload, dict) or set(payload) != {
        "design",
        "conditions",
        "phases",
    }:
        raise ValueError("Invalid analysis configuration.")
    conditions, phases = payload.get("conditions"), payload.get("phases")
    if not isinstance(conditions, list) or not isinstance(phases, list):
        raise ValueError("Invalid analysis selections.")
    plan = AnalysisPlan(payload.get("design"), tuple(conditions), tuple(phases))
    available = configuration(window)
    if not set(plan.conditions).issubset(available["conditions"]) or not set(plan.phases).issubset(
        available["phases"]
    ):
        raise ValueError("Analysis selections are no longer available.")
    window.apply_analysis_plan(plan, web=True)


def _assigned_conditions(evidence_json: str) -> str | None:
    return _assigned_conditions_from_cells(json.loads(evidence_json))


def _assigned_conditions_from_cells(evidence: dict) -> str | None:
    conditions = {json.loads(key)[0] for key, info in evidence.items() if info["sources"]}
    return ", ".join(sorted(conditions)) or None


def _recording_accuracy(window, source_file):
    result = window.import_results.get(Path(source_file))
    if result and result.summary:
        return next(m for m in result.summary.metrics if m.name == "prl.proportion_correct")
    return None


def _sorted_positions(window, table, frame, rules):
    signature = tuple((r["column"], r["descending"]) for r in rules)
    cached = window._web_sort_cache.get(table)
    if cached is not None and cached[0] is frame and cached[1] == signature:
        return cached[2]

    # Only sort the requested keys. Individual evidence JSON can be wide and is
    # needed only for the displayed page unless it is explicitly a sort key.
    keys = {}
    directions = []
    for column, descending in signature:
        if column == "recording_proportion_correct" and table == "analysis_audit.csv":
            values = frame["source_file"].map(lambda path: _recording_accuracy(window, path))
            values = values.map(lambda m: m.value if m is not None else None)
        elif column == "treatment_group" and table == "condition_comparison.csv":
            values = frame["cell_evidence_json"].map(_assigned_conditions)
        elif column == "metric" and column in frame:
            values = frame[column].replace(METRIC_TITLES)
        elif column in frame:
            values = frame[column]
        else:
            continue  # A condition/phase column may be outside the current scope.
        keys[column] = values.reset_index(drop=True)
        directions.append(not descending)

    positions = (
        pd.DataFrame(keys)
        .sort_values(list(keys), ascending=directions, na_position="last", kind="stable")
        .index
        if keys
        else range(len(frame))
    )
    window._web_sort_cache[table] = (frame, signature, positions)
    return positions


def page(window: MainWindow, table: str, offset: int, limit: int) -> dict:
    tables = window._web_analysis_tables
    if not tables or table not in SHEETS or table not in tables:
        raise ValueError("Analysis results are unavailable.")
    if offset < 0 or not 1 <= limit <= 250:
        raise ValueError("Invalid page.")
    frame = tables[table]
    rules = window.analysis_sorts.get(table)
    if rules is None:
        rules = [
            {"column": key, "descending": False}
            for key in ("metric", "phase", "subject_id", "condition")
            if key in frame
        ]
    positions = _sorted_positions(window, table, frame, rules)

    preferred = {
        "pooled_metrics.csv": [
            "condition",
            "phase",
            "metric",
            "pooled_value",
            "valid_animal_n",
            "sum_numerator",
            "sum_denominator",
            "unit",
        ],
        "analysis_audit.csv": [
            "subject_id",
            "condition",
            "phase",
            "disposition",
            "source_file",
            "inclusion",
            "inclusion_reason",
            "import_status",
            "import_error",
        ],
        "condition_comparison.csv": [
            "subject_id",
            "treatment_group",
            "metric",
            *(key for key in frame.columns if key.startswith("[")),
        ],
        "animal_metrics.csv": [
            "subject_id",
            "condition",
            "phase",
            "metric",
            "value",
            "unit",
            "status",
            "reasons",
            "source_file",
        ],
    }
    front = [name for name in preferred.get(table, ()) if name in frame.columns]
    columns = front + [name for name in frame.columns if name not in front]
    subset = frame.iloc[positions[offset : offset + limit]].loc[:, columns]
    model = AnalysisModel(subset)
    rows = [
        [model.data(model.index(row, column)) for column in range(len(columns))]
        for row in range(len(subset))
    ]
    display_headers = [name if name.startswith("[") else name.replace("_", " ") for name in columns]
    cell_details = [["" for _ in columns] for _ in rows]
    if table == "condition_comparison.csv":
        _comparison_cells(subset, columns, display_headers, rows, cell_details)
    elif table == "analysis_audit.csv":
        # Show the reviewed recording even when a repeat prevents its use in the comparison.
        col = columns.index("disposition")
        columns.insert(col, "recording_proportion_correct")
        display_headers.insert(col, "Recording proportion correct")
        for i, path in enumerate(subset["source_file"]):
            result = window.import_results.get(Path(path))
            value, reason = "Import required", ""
            if result and result.error:
                value, reason = "Import failed", result.error
            elif result and result.summary:
                metric = _recording_accuracy(window, path)
                value = "Unavailable" if metric.value is None else str(metric.value)
                reason = "\n".join(metric.reasons)
            rows[i].insert(col, value)
            cell_details[i].insert(col, reason)
    return {
        "sort_rules": rules,
        "headers": columns,
        "display_headers": display_headers,
        "rows": rows,
        "cell_details": cell_details,
        "total": len(frame),
        "offset": offset,
    }


def _comparison_cells(subset, columns, headers, rows, details):
    treatment = columns.index("treatment_group")
    headers[treatment] = "Assigned conditions"
    cells = [(i, key) for i, key in enumerate(columns) if key.startswith("[")]
    for row, notes, record in zip(rows, details, subset.to_dict("records"), strict=True):
        evidence = json.loads(record["cell_evidence_json"])
        row[treatment] = _assigned_conditions_from_cells(evidence) or ""
        for i, key in cells:
            if key not in evidence:
                row[i] = "Outside group"
                continue
            info = evidence[key]
            if record[key] is None:
                # The analysis engine has already distinguished repeats, missing
                # partners and metric-specific unavailability. Preserve its reason.
                row[i] = " · ".join(info["reasons"]) or "Unavailable"
            else:
                row[i] = str(record[key])
            notes[i] = "\n".join(f"Source: {path}" for path in info["sources"])
