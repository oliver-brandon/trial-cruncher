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
from trial_cruncher.prl_metrics import METRIC_LABELS, PRLSessionSummary

SCHEMA_VERSION = "2"
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


def build_choice_table(sessions: Sequence[Session]) -> pd.DataFrame:
    rows = []
    for session in sessions:
        provenance = _provenance(session)
        for event in session.events:
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
                }
            )
    return pd.DataFrame(rows, columns=CHOICE_COLUMNS, dtype=object)
