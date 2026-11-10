"""Versioned fixed-contingency, no-omission PRL phase calculations."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from trial_cruncher.models import MetricResult, Session
from trial_cruncher.prl_metrics import calculate_prl_summary

DEFINITION_SET = "prl-medpc-phase-behavior"
DEFINITION_VERSION = "1"
PROTOCOL_PROFILE = "fixed-contingency-no-omissions-v1"
POLICY = "strict-withholding-v2"
METRIC_LABELS = {
    "prl.phase.percent_correct": "Correct choices (%)",
    "prl.phase.perseverative_errors": "Perseverative errors",
    "prl.phase.regressive_errors": "Regressive errors",
    "prl.phase.adjusted_regressive_error_proportion": "Adjusted regressive-error proportion",
    "prl.phase.win_stay_correct": "Win-stay, correct lever",
    "prl.phase.win_stay_incorrect": "Win-stay, incorrect lever",
    "prl.phase.lose_shift_correct": "Lose-shift, correct lever",
    "prl.phase.lose_shift_incorrect": "Lose-shift, incorrect lever",
}
STRATEGIES = tuple(METRIC_LABELS)[4:]


@dataclass(frozen=True)
class PhaseConfig:
    phase: str | None
    assignment_source: str = "user_at_import"
    version: str = "1"
    protocol_profile: str = PROTOCOL_PROFILE
    confirmation_date: str = "2026-11-10"
    protocol_evidence: str = (
        "Owner confirmed fixed contingency per file; levers stay out until choice."
    )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def phase_config(phase: str | None) -> PhaseConfig:
    """Normalize user whitespace, never infer a phase from source labels."""
    if phase is not None and not isinstance(phase, str):
        raise ValueError("Phase must be a text label or None.")
    label = phase.strip() if phase is not None else None
    return PhaseConfig(label or None, "user_at_import" if label else "unassigned")


@dataclass(frozen=True)
class RatioEvidence:
    numerator: int | None = None
    denominator: int | None = None

    @property
    def undefined(self) -> bool | None:
        return None if self.denominator is None else self.denominator == 0


@dataclass(frozen=True)
class PhaseDiagnostics:
    valid_choice_count: int | None = None
    correct_choice_count: int | None = None
    incorrect_choice_count: int | None = None
    criterion_reached: bool | None = None
    criterion_choice_ordinal: int | None = None
    criterion_source_index: int | None = None
    postcriterion_choice_count: int | None = None
    eligible_pair_count: int | None = None
    adjusted_regressive: RatioEvidence = RatioEvidence()


@dataclass(frozen=True)
class PhaseSummary:
    source_file: Path
    source_sha256: str
    config: PhaseConfig
    metrics: tuple[MetricResult, ...]
    diagnostics: PhaseDiagnostics
    strategies: tuple[RatioEvidence, ...]
    reason_codes: tuple[tuple[str, ...], ...]
    choice_error_classes: tuple[str | None, ...]
    definition_set: str = DEFINITION_SET
    definition_version: str = DEFINITION_VERSION
    eligibility_policy: str = POLICY

    @property
    def status(self) -> str:
        if any("source_integrity" in codes for codes in self.reason_codes):
            return "withheld"
        if self.config.phase is None:
            return "phase_unassigned"
        available = sum(metric.value is not None for metric in self.metrics)
        return (
            "available"
            if available == len(self.metrics)
            else "partially_available"
            if available
            else "unavailable"
        )


def calculate_phase_metrics(session: Session, phase: str | None = None) -> PhaseSummary:
    """Validate full source integrity, then calculate within this source only."""
    base = calculate_prl_summary(session)
    config = phase_config(phase)
    reasons, codes = [], []
    if config.phase is None:
        reasons.append("Assign a phase and re-import to calculate phase metrics.")
        codes.append("phase_unassigned")
    # Counts are unavailable for damaged or missing C. Undefined empty percentages
    # alone do not imply corrupt source data.
    if base.metrics[0].value is None:
        reasons.extend(base.metrics[0].reasons)
        codes.append("source_integrity")
    values: list[int | float | None] = [None] * 8
    metric_reasons = [tuple(reasons) for _ in values]
    metric_codes = [tuple(codes) for _ in values]
    diagnostics = PhaseDiagnostics()
    strategies = tuple(RatioEvidence() for _ in STRATEGIES)
    classifications: tuple[str | None, ...] = (None,) * len(session.events)
    if not reasons:
        events = session.events
        correct = [event.attributes["correct"] for event in events]
        rewarded = [event.attributes["rewarded"] for event in events]
        n, n_correct = len(events), sum(correct)
        k = None
        streak = 0
        for ordinal, is_correct in enumerate(correct, 1):
            streak = streak + 1 if is_correct else 0
            if streak == 3:
                k = ordinal
                break
        post_count = n - k if k is not None else 0
        perseverative = sum(not c for c in correct[:k]) if k else n - n_correct
        regressive = sum(not c for c in correct[k:]) if k else 0
        pair_evidence = []
        for c, reward in ((True, True), (False, True), (True, False), (False, False)):
            pairs = [i for i in range(max(0, n - 1)) if correct[i] == c and rewarded[i] == reward]
            numerator = sum((correct[i] == correct[i + 1]) == reward for i in pairs)
            pair_evidence.append(RatioEvidence(numerator, len(pairs)))
        strategies = tuple(pair_evidence)
        diagnostics = PhaseDiagnostics(
            n,
            n_correct,
            n - n_correct,
            k is not None if n else None,
            k,
            events[k - 1].raw_values["index"] if k else None,
            post_count if n else None,
            max(0, n - 1),
            RatioEvidence(regressive, post_count) if n else RatioEvidence(),
        )
        if n:
            values[:4] = [
                100 * n_correct / n,
                perseverative,
                regressive,
                regressive / post_count if post_count else None,
            ]
            classifications = tuple(
                "correct" if c else "regressive" if k is not None and i > k else "perseverative"
                for i, c in enumerate(correct, 1)
            )
            if not post_count:
                metric_reasons[3] = ("No postcriterion choices; adjusted proportion is undefined.",)
                metric_codes[3] = ("no_postcriterion_choices",)
        else:
            for i in range(4):
                metric_reasons[i] = ("No recorded choices in this phase.",)
                metric_codes[i] = ("no_choices",)
        for i, pair in enumerate(strategies, 4):
            if pair.denominator:
                values[i] = pair.numerator / pair.denominator
            else:
                metric_reasons[i] = ("No eligible conditioning choices; probability is undefined.",)
                metric_codes[i] = ("zero_strategy_denominator",)
    metrics = tuple(
        MetricResult(
            name,
            DEFINITION_VERSION,
            value,
            "%"
            if i == 0
            else "count"
            if i in (1, 2)
            else "proportion"
            if i == 3
            else "probability",
            session.warnings,
            metric_reasons[i],
        )
        for i, (name, value) in enumerate(zip(METRIC_LABELS, values, strict=True))
    )
    return PhaseSummary(
        session.source_file,
        session.metadata["raw_medpc"]["source_sha256"],
        config,
        metrics,
        diagnostics,
        strategies,
        tuple(metric_codes),
        classifications,
    )
