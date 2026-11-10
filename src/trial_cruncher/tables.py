"""Versioned tables of imported observations and previously calculated metrics."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from trial_cruncher import __version__
from trial_cruncher.models import Session
from trial_cruncher.phase_metrics import METRIC_LABELS as PHASE_METRIC_LABELS
from trial_cruncher.phase_metrics import STRATEGIES, PhaseSummary
from trial_cruncher.prl_metrics import METRIC_LABELS, PRLSessionSummary

SCHEMA_VERSION = "5"
PROVENANCE_COLUMNS = (
    "schema_version",
    "application_version",
    "source_file",
    "source_sha256",
    "source_file_header",
    "subject_id",
    "session_id",
    "program",
    "reader_version",
    "normalizer_version",
    "time_origin",
    "time_unit",
    "warnings_json",
)
SESSION_COLUMNS = (
    PROVENANCE_COLUMNS
    + (
        "duration_s",
        "head_entries_recorded",
        "latency_available",
        "summary_checks_json",
        "metadata_json",
    )
    + tuple(METRIC_LABELS)
    + (
        "metric_definition_set",
        "metric_definition_version",
        "metric_policy",
        "metric_results_json",
        "metric_diagnostics_json",
    )
)
CHOICE_COLUMNS = PROVENANCE_COLUMNS + (
    "event_name",
    "source_array",
    "source_index",
    "source_line",
    "raw_value",
    "timestamp_s",
    "outcome_code",
    "correct",
    "rewarded",
    "raw_values_json",
    "attributes_json",
    "phase",
    "phase_error_classification",
    "phase_criterion_completed_here",
)
PHASE_COLUMNS = (
    PROVENANCE_COLUMNS
    + (
        "phase",
        "phase_status",
        "phase_definition_set",
        "phase_definition_version",
        "phase_policy",
        "configuration_sha256",
        "configuration_json",
        "omission_count",
        "omission_count_basis",
        "valid_choice_count",
        "correct_choice_count",
        "incorrect_choice_count",
        "session_total_choices",
        "criterion_reached",
        "criterion_choice_ordinal",
        "criterion_source_index",
        "postcriterion_choice_count",
        "eligible_pair_count",
        "adjusted_regressive_numerator",
        "adjusted_regressive_denominator",
    )
    + tuple(PHASE_METRIC_LABELS)
    + tuple(
        f"{name}_{suffix}"
        for name in STRATEGIES
        for suffix in ("numerator", "denominator", "undefined")
    )
    + (
        "metric_results_json",
        "metric_reason_codes_json",
        "source_diagnostics_json",
        "choice_storage_json",
    )
)


def json_text(value: Any) -> str:
    """Retain Decimal precision as strings; reject unsupported/nonfinite objects."""

    def encode(item: Any) -> str:
        if isinstance(item, Path | Decimal):
            return str(item)
        raise TypeError(f"Cannot export {type(item).__name__} as JSON.")

    return json.dumps(value, default=encode, ensure_ascii=False, allow_nan=False)


def _provenance(session: Session) -> dict[str, Any]:
    metadata = session.metadata
    raw = metadata.get("raw_medpc", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "application_version": __version__,
        "source_file": str(session.source_file),
        "source_sha256": raw.get("source_sha256"),
        "source_file_header": raw.get("headers", {}).get("File"),
        "subject_id": session.subject_id,
        "session_id": session.session_id,
        "program": metadata.get("program"),
        "reader_version": raw.get("reader_version"),
        "normalizer_version": metadata.get("normalizer_version"),
        "time_origin": metadata.get("time_origin"),
        "time_unit": metadata.get("time_unit"),
        "warnings_json": json_text(session.warnings),
    }


def build_session_table(
    sessions: Sequence[Session], summaries: Mapping[Path, PRLSessionSummary] | None = None
) -> pd.DataFrame:
    rows = []
    for session in sessions:
        summary = summaries.get(session.source_file) if summaries is not None else None
        metric_values = {metric.name: metric.value for metric in summary.metrics} if summary else {}
        rows.append(
            {
                **_provenance(session),
                "duration_s": session.duration_s,
                "head_entries_recorded": session.metadata.get("head_entries_recorded"),
                "latency_available": session.metadata.get("latency_available"),
                "summary_checks_json": json_text(session.metadata.get("summary_checks")),
                "metadata_json": json_text(session.metadata),
                **metric_values,
                "metric_definition_set": summary.definition_set if summary else None,
                "metric_definition_version": summary.definition_version if summary else None,
                "metric_policy": summary.eligibility_policy if summary else None,
                "metric_results_json": json_text(
                    [{**asdict(metric), "status": metric.status} for metric in summary.metrics]
                )
                if summary
                else None,
                "metric_diagnostics_json": json_text(asdict(summary.diagnostics))
                if summary
                else None,
            }
        )
    # Object dtype prevents optional integer indices/codes from becoming floats.
    return pd.DataFrame(rows, columns=SESSION_COLUMNS, dtype=object)


def build_choice_table(
    sessions: Sequence[Session], phases: Mapping[Path, PhaseSummary] | None = None
) -> pd.DataFrame:
    rows = []
    for session in sessions:
        provenance = _provenance(session)
        phase = phases.get(session.source_file) if phases is not None else None
        for ordinal, event in enumerate(session.events):
            if event.name != "choice":
                continue
            rows.append(
                {
                    **provenance,
                    "event_name": event.name,
                    "source_array": event.raw_values.get("array"),
                    "source_index": event.raw_values.get("index"),
                    "source_line": event.raw_values.get("line_number"),
                    "raw_value": event.raw_values.get("value"),
                    "timestamp_s": event.timestamp_s,
                    "outcome_code": event.attributes.get("outcome_code"),
                    "correct": event.attributes.get("correct"),
                    "rewarded": event.attributes.get("rewarded"),
                    "raw_values_json": json_text(event.raw_values),
                    "attributes_json": json_text(event.attributes),
                    "phase": phase.config.phase if phase else None,
                    "phase_error_classification": phase.choice_error_classes[ordinal]
                    if phase
                    else None,
                    "phase_criterion_completed_here": (
                        ordinal + 1 == phase.diagnostics.criterion_choice_ordinal
                        if phase and phase.choice_error_classes[ordinal] is not None
                        else None
                    ),
                }
            )
    return pd.DataFrame(rows, columns=CHOICE_COLUMNS, dtype=object)


def build_phase_table(
    sessions: Sequence[Session],
    phases: Mapping[Path, PhaseSummary],
    summaries: Mapping[Path, PRLSessionSummary],
) -> pd.DataFrame:
    rows = []
    for session in sessions:
        phase = phases[session.source_file]
        diagnostic = phase.diagnostics
        row = {
            **_provenance(session),
            "phase": phase.config.phase,
            "phase_status": phase.status,
            "phase_definition_set": phase.definition_set,
            "phase_definition_version": phase.definition_version,
            "phase_policy": phase.eligibility_policy,
            "configuration_sha256": phase.config.sha256,
            "configuration_json": json_text(asdict(phase.config)),
            "omission_count": 0,
            "omission_count_basis": "owner-confirmed no-omission protocol",
            **{
                key: value
                for key, value in asdict(diagnostic).items()
                if key != "adjusted_regressive"
            },
            "session_total_choices": summaries[session.source_file].metrics[0].value,
            "adjusted_regressive_numerator": diagnostic.adjusted_regressive.numerator,
            "adjusted_regressive_denominator": diagnostic.adjusted_regressive.denominator,
            **{metric.name: metric.value for metric in phase.metrics},
            "metric_results_json": json_text(
                [{**asdict(m), "status": m.status} for m in phase.metrics]
            ),
            "metric_reason_codes_json": json_text(
                dict(zip(PHASE_METRIC_LABELS, phase.reason_codes, strict=True))
            ),
            "source_diagnostics_json": json_text(
                asdict(summaries[session.source_file].diagnostics)
            ),
            "choice_storage_json": json_text(session.metadata["choice_storage"]),
        }
        for name, evidence in zip(STRATEGIES, phase.strategies, strict=True):
            row.update(
                {
                    f"{name}_numerator": evidence.numerator,
                    f"{name}_denominator": evidence.denominator,
                    f"{name}_undefined": evidence.undefined,
                }
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=PHASE_COLUMNS, dtype=object)
