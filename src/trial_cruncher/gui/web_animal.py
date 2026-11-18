"""Web-facing animal analysis configuration and paged review."""

from trial_cruncher.aggregation import SHEETS
from trial_cruncher.analysis_plan import AnalysisPlan
from trial_cruncher.gui.animal_analysis import AnalysisModel
from trial_cruncher.gui.window import MainWindow


def configuration(window: MainWindow) -> dict:
    annotations = window.metadata_assignments.values()
    plan = window.analysis_plan
    return {
        "cohorts": sorted(
            {a.cohort for a in annotations if a.cohort} | ({plan.cohort} if plan else set())
        ),
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
        "cohort",
        "design",
        "conditions",
        "phases",
    }:
        raise ValueError("Invalid analysis configuration.")
    conditions, phases = payload.get("conditions"), payload.get("phases")
    if not isinstance(conditions, list) or not isinstance(phases, list):
        raise ValueError("Invalid analysis selections.")
    plan = AnalysisPlan(
        payload.get("cohort"), payload.get("design"), tuple(conditions), tuple(phases)
    )
    available = configuration(window)
    if (
        plan.cohort not in available["cohorts"]
        or not set(plan.conditions).issubset(available["conditions"])
        or not set(plan.phases).issubset(available["phases"])
    ):
        raise ValueError("Analysis selections are no longer available.")
    window.apply_analysis_plan(plan, web=True)


def page(window: MainWindow, table: str, offset: int, limit: int) -> dict:
    tables = getattr(window, "_web_analysis_tables", None)
    if not tables or table not in SHEETS or table not in tables:
        raise ValueError("Analysis results are unavailable.")
    if offset < 0 or not 1 <= limit <= 250:
        raise ValueError("Invalid page.")
    frame = tables[table]
    if table == "pooled_metrics.csv":
        front = [
            "condition",
            "phase",
            "metric",
            "pooled_value",
            "valid_animal_n",
            "sum_numerator",
            "sum_denominator",
            "unit",
        ]
        columns = front + [col for col in frame if col not in front]
    else:
        columns = list(frame.columns)
    subset = frame.iloc[offset : offset + limit].loc[:, columns]
    model = AnalysisModel(subset)
    rows = [
        [model.data(model.index(row, column)) for column in range(len(columns))]
        for row in range(len(subset))
    ]
    return {"headers": columns, "rows": rows, "total": len(frame), "offset": offset}
