"""Approved PRL session-summary definitions, version 4; whole-session Med-PC rate."""

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from trial_cruncher.models import MetricResult, Session
from trial_cruncher.prl import NORMALIZER_VERSION, SUPPORTED_PROGRAMS, choice_storage_info

DEFINITION_SET = "prl-session-summary"
DEFINITION_VERSION = "4"
ELIGIBILITY_POLICY = "strict-withholding-v2"
MEDPC_RATE = "prl.medpc_trials_per_minute"
METRIC_LABELS = {
    "prl.choice_count": "Recorded choices",
    "prl.correct_choice_count": "Correct choices",
    "prl.incorrect_choice_count": "Incorrect choices",
    "prl.rewarded_choice_count": "Rewarded choices",
    "prl.unrewarded_choice_count": "Unrewarded choices",
    "prl.proportion_correct": "Proportion correct",
    MEDPC_RATE: "Trials/min (Med-PC)",
}
METRIC_UNITS = {
    name: "proportion"
    if name == "prl.proportion_correct"
    else "choices/min"
    if name == MEDPC_RATE
    else "count"
    for name in METRIC_LABELS
}
_TERMINATOR = Decimal("-987.987")
_OUTCOMES = {1: (True, True), 2: (True, False), 6: (False, True), 7: (False, False)}


@dataclass(frozen=True)
class PRLDiagnostics:
    """Observed records, not substitutes for withheld session totals."""

    c_present: bool
    terminator_seen: bool | None
    observed_record_count: int | None
    decoded_choice_count: int | None
    invalid_record_count: int | None
    post_terminator_count: int | None
    c_indices_have_gaps: bool | None
    summary_checks: Mapping[str, bool | None]
    raw_c_entry_count: int | None = None
    unused_slot_count: int | None = None


@dataclass(frozen=True)
class PRLSessionSummary:
    metrics: tuple[MetricResult, ...]
    diagnostics: PRLDiagnostics
    definition_set: str = DEFINITION_SET
    definition_version: str = DEFINITION_VERSION
    eligibility_policy: str = ELIGIBILITY_POLICY


def calculate_prl_summary(session: Session) -> PRLSessionSummary:
    """Calculate from the confirmed normalizer's events and structured provenance.

    Does not read files, mutate inputs, parse warning messages, infer omissions,
    or recalculate saved counters. Unsupported interpretation versions fail closed.
    """
    metadata = session.metadata
    raw = metadata.get("raw_medpc", {})
    if (
        metadata.get("program") not in SUPPORTED_PROGRAMS
        or metadata.get("normalizer_version") != NORMALIZER_VERSION
        or raw.get("reader_version") != "1"
        or raw.get("format") != "medpc-text"
        or raw.get("source_file") != session.source_file
    ):
        raise ValueError(
            "PRL metrics require reader version 1 and normalizer version 2; re-import."
        )

    storage = choice_storage_info(raw)
    if metadata.get("choice_storage") != storage:
        raise ValueError(
            "Choice storage metadata does not match the imported C records; re-import."
        )
    unused_indices = set(storage["unused_slot_indices"])

    choices = raw["arrays"].get("C")
    checks = dict(metadata["summary_checks"])
    reasons: list[str] = []
    counts: Counter[int] = Counter()
    if choices is None:
        reasons.append("C is missing; no observed choice sequence is available.")
        diagnostics = PRLDiagnostics(False, None, None, None, None, None, None, checks)
    else:
        indices = sorted(choices)
        gaps = any(index != expected for expected, index in enumerate(indices))
        if gaps:
            reasons.append("C indices are not contiguous from zero.")
        before_terminator = []
        terminated = False
        after_count = 0
        for index in indices:
            if index in unused_indices:
                continue
            if terminated:
                after_count += 1
            elif choices[index] == _TERMINATOR:
                terminated = True
            else:
                before_terminator.append(index)
        # A stale or manually altered canonical sequence must not look complete.
        if len(session.events) != len(before_terminator) or any(
            event.name != "choice"
            or event.raw_values.get("array") != "C"
            or event.raw_values.get("index") != index
            or event.raw_values.get("value") != choices[index]
            for event, index in zip(session.events, before_terminator, strict=True)
        ):
            raise ValueError("Normalized choice events do not match the imported C records.")
        invalid_count = 0
        for event in session.events:
            code = event.attributes.get("outcome_code")
            if (
                code not in _OUTCOMES
                or event.timestamp_s is None
                or event.attributes.get("correct") is not _OUTCOMES[code][0]
                or event.attributes.get("rewarded") is not _OUTCOMES[code][1]
            ):
                invalid_count += 1
            else:
                counts[code] += 1
        if invalid_count:
            reasons.append(f"C contains {invalid_count} invalid choice record(s).")
        if after_count:
            reasons.append(f"C contains {after_count} value(s) after the terminator.")
        diagnostics = PRLDiagnostics(
            True,
            terminated,
            len(before_terminator),
            sum(counts.values()),
            invalid_count,
            after_count,
            gaps,
            checks,
            raw_c_entry_count=storage["raw_c_entry_count"],
            unused_slot_count=storage["unused_slot_count"],
        )
    mismatches = [key for key, matches in checks.items() if matches is False]
    if mismatches:
        reasons.append(f"Saved count mismatch: {', '.join(mismatches)}.")

    total = sum(counts.values())
    correct = counts[1] + counts[2]
    rate_reasons = list(reasons)
    duration = session.duration_s
    rate = None
    if duration is None or not math.isfinite(duration) or duration <= 0:
        rate_reasons.append("Med-PC rate requires a finite, positive task duration S.")
    elif any(
        event.timestamp_s is not None and event.timestamp_s > duration for event in session.events
    ):
        rate_reasons.append("Med-PC rate is unavailable because a choice timestamp exceeds S.")
    elif not rate_reasons:
        rate = 60 * total / duration
        if not math.isfinite(rate):
            rate = None
            rate_reasons.append("Med-PC rate cannot be represented as a finite number.")
    # One final division; no rounding or accuracy derived from the saved A[5].
    values = (
        total,
        correct,
        counts[6] + counts[7],
        counts[1] + counts[6],
        counts[2] + counts[7],
        correct / total if total else None,
        rate,
    )
    metrics = []
    for name, value in zip(METRIC_LABELS, values, strict=True):
        metric_reasons = tuple(rate_reasons if name == MEDPC_RATE else reasons)
        if metric_reasons:
            value = None
        elif name == "prl.proportion_correct" and total == 0:
            metric_reasons = ("Proportion correct has no denominator: zero recorded choices.",)
        metrics.append(
            MetricResult(
                name,
                DEFINITION_VERSION,
                value,
                METRIC_UNITS[name],
                warnings=session.warnings,
                reasons=metric_reasons,
            )
        )
    return PRLSessionSummary(tuple(metrics), diagnostics)
