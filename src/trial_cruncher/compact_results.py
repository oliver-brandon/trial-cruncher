"""Concise per-recording results derived from reviewed import snapshots."""

from collections.abc import Iterator

from trial_cruncher.models import MetricResult, Session
from trial_cruncher.processing import ImportResult

type Cell = str | int | float | None

COLUMN_GUIDE = {
    "ID": "Subject ID recorded in the source file.",
    "Phase": "Phase assigned when imported.",
    "Treatment": "Manually assigned condition or treatment.",
    "Proportion correct": "Correct recorded choices divided by recorded choices.",
    "Perseverative errors": "Incorrect choices before the first run of three correct choices.",
    "Regressive errors": "Incorrect choices after the criterion.",
    "Adjusted regressive proportion": "Regressive errors divided by postcriterion choices.",
    "Win-stay correct": "Probability of staying after a rewarded correct choice.",
    "Lose-shift correct": "Probability of shifting after an unrewarded correct choice.",
    "Win-stay incorrect": "Probability of staying after a rewarded incorrect choice.",
    "Lose-shift incorrect": "Probability of shifting after an unrewarded incorrect choice.",
    "Trials to criterion": (
        "Trial number completing the first run of three consecutive correct choices."
    ),
    "Trials/min": "Whole-session Med-PC rate: 60 × recorded choices / task duration S (seconds).",
}
DATA_COLUMNS = tuple(COLUMN_GUIDE)


_METRIC_NAMES = {
    "Proportion correct": "prl.proportion_correct",
    "Perseverative errors": "prl.phase.perseverative_errors",
    "Regressive errors": "prl.phase.regressive_errors",
    "Adjusted regressive proportion": "prl.phase.adjusted_regressive_error_proportion",
    "Win-stay correct": "prl.phase.win_stay_correct",
    "Lose-shift correct": "prl.phase.lose_shift_correct",
    "Win-stay incorrect": "prl.phase.win_stay_incorrect",
    "Lose-shift incorrect": "prl.phase.lose_shift_incorrect",
    "Trials/min": "prl.medpc_trials_per_minute",
}


def _metrics(result: ImportResult) -> dict[str, MetricResult]:
    session = result.summary.metrics if result.summary else ()
    phase = result.phase_summary.metrics if result.phase_summary else ()
    return {metric.name: metric for metric in (*session, *phase)}


def data_values(result: ImportResult) -> tuple[Cell, ...]:
    """Return stored values in display order, without recalculating metrics."""
    metrics = _metrics(result)
    phase = result.phase_summary
    values: dict[str, Cell] = {
        "ID": result.session.subject_id if result.session else None,
        "Phase": phase.config.phase if phase else None,
        "Treatment": result.analysis_metadata.condition,
        "Trials to criterion": phase.diagnostics.criterion_choice_ordinal if phase else None,
    }
    for column, name in _METRIC_NAMES.items():
        metric = metrics.get(name)
        values[column] = metric.value if metric else None
    return tuple(values[column] for column in DATA_COLUMNS)


def data_reasons(result: ImportResult) -> dict[str, str]:
    """Explain unavailable values independently for each displayed column."""
    metrics = _metrics(result)
    reasons: dict[str, str] = {}
    for column, name in _METRIC_NAMES.items():
        metric = metrics.get(name)
        if metric is None:
            reasons[column] = result.error or "Metric unavailable; import the recording."
        elif metric.value is None:
            reasons[column] = "; ".join(metric.reasons) or "Metric unavailable."
    phase = result.phase_summary
    if phase is None:
        reasons["Trials to criterion"] = result.error or "Phase results unavailable."
    elif phase.diagnostics.criterion_choice_ordinal is None:
        if phase.diagnostics.criterion_reached is False:
            reasons["Trials to criterion"] = (
                "Criterion of three consecutive correct choices was not reached."
            )
        else:
            reasons["Trials to criterion"] = (
                "; ".join(phase.metrics[0].reasons) or "Criterion unavailable."
            )
    return reasons


def trial_values(session: Session) -> Iterator[tuple[int, int | None, int | None]]:
    """Yield recorded choices in order, keeping undecodable outcomes missing."""
    choices = (event for event in session.events if event.name == "choice")
    for ordinal, event in enumerate(choices, 1):
        correct = event.attributes.get("correct")
        rewarded = event.attributes.get("rewarded")
        yield (
            ordinal,
            int(correct) if type(correct) is bool else None,
            int(rewarded) if type(rewarded) is bool else None,
        )
