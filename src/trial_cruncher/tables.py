"""Versioned session and choice tables; no behavioral metrics are calculated."""

import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from trial_cruncher import __version__
from trial_cruncher.models import Session

SCHEMA_VERSION = "1"
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
SESSION_COLUMNS = PROVENANCE_COLUMNS + (
    "duration_s",
    "head_entries_recorded",
    "latency_available",
    "summary_checks_json",
    "metadata_json",
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


def build_session_table(sessions: Sequence[Session]) -> pd.DataFrame:
    rows = []
    for session in sessions:
        rows.append(
            {
                **_provenance(session),
                "duration_s": session.duration_s,
                "head_entries_recorded": session.metadata.get("head_entries_recorded"),
                "latency_available": session.metadata.get("latency_available"),
                "summary_checks_json": json_text(session.metadata.get("summary_checks")),
                "metadata_json": json_text(session.metadata),
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
