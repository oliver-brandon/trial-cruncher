"""Compact tables derived from reviewed results and their existing provenance."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.compact_results import DATA_COLUMNS, data_reasons, data_values, trial_values
from trial_cruncher.processing import ImportResult

METADATA_COLUMNS = (
    "Source file",
    "Data row",
    "Status",
    "Subject ID",
    "Phase",
    "Treatment",
    "Inclusion",
    "Inclusion reason",
    "Source date",
    "Program",
    "SHA-256",
    "Warnings",
    "Error",
    "Metric unavailability",
)
TRIAL_COLUMNS = ("Source file", "ID", "Phase", "Treatment", "Trial", "Choice", "Outcome")


def compact_metadata(
    results: Mapping[Path, ImportResult],
    paths: Sequence[Path],
    assignments: Mapping[Path, AnalysisMetadata] | None,
    manifest: dict,
) -> pd.DataFrame:
    rows = []
    data_rows = {
        str(path): index
        for index, path in enumerate(
            (p for p in paths if p in results and results[p].session and not results[p].error), 2
        )
    }
    for item in manifest["inputs"]:
        path = Path(item["source_file"])
        result = results.get(path)
        annotation = (
            result.analysis_metadata
            if result
            else (assignments or {}).get(path, AnalysisMetadata())
        )
        raw = result.raw if result else None
        session = result.session if result else None
        phase = result.phase_summary.config.phase if result and result.phase_summary else None
        rows.append(
            (
                str(path),
                data_rows.get(str(path)),
                item["status"],
                session.subject_id if session else raw["headers"].get("Subject") if raw else None,
                phase,
                annotation.condition,
                annotation.inclusion_status,
                annotation.inclusion_reason,
                raw["headers"].get("Start Date") if raw else None,
                raw["headers"].get("MSN") if raw else None,
                item["source_sha256"],
                "\n".join(item["warnings"]),
                item["error"],
                "\n".join(f"{metric}: {reason}" for metric, reason in data_reasons(result).items())
                if result and session
                else None,
            )
        )
    return pd.DataFrame(rows, columns=METADATA_COLUMNS, dtype=object)


def compact_tables(
    results: Mapping[Path, ImportResult],
    paths: Sequence[Path],
    assignments: Mapping[Path, AnalysisMetadata] | None,
    manifest: dict,
) -> dict[str, pd.DataFrame]:
    data, trials = [], []
    for path in paths:
        result = results.get(path)
        if not result or not result.session or result.error:
            continue
        values = data_values(result)
        data.append(values)
        trials.extend((str(path), *values[:3], *trial) for trial in trial_values(result.session))
    return {
        "data.csv": pd.DataFrame(data, columns=DATA_COLUMNS, dtype=object),
        "trials.csv": pd.DataFrame(trials, columns=TRIAL_COLUMNS, dtype=object),
        "metadata.csv": compact_metadata(results, paths, assignments, manifest),
    }
