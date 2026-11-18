"""Exclusive-create writers and complete session/choice export bundles."""

import csv
import logging
import platform
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd

from trial_cruncher import __version__, phase_metrics
from trial_cruncher.aggregation import AnalysisPlan, build_analysis
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.prl import CHOICE_STORAGE_POLICY
from trial_cruncher.prl_metrics import (
    DEFINITION_SET,
    DEFINITION_VERSION,
    ELIGIBILITY_POLICY,
    METRIC_LABELS,
    METRIC_UNITS,
)
from trial_cruncher.processing import ImportResult, validate_reviewed_result
from trial_cruncher.source_tracking import require_current_sources
from trial_cruncher.tables import (
    SCHEMA_VERSION,
    WHOLE_SESSION_RATE_COLUMN,
    build_choice_table,
    build_phase_table,
    build_session_table,
    json_text,
)

logger = logging.getLogger(__name__)
ExportFormat = Literal["csv", "xlsx"]


class Exporter(Protocol):
    def export(self, table: pd.DataFrame, destination: Path) -> Path:
        """Write a provenance-bearing table; refuse source paths and existing files."""
        ...


class CSVExporter:
    def __init__(self, source_paths: Sequence[Path] = ()) -> None:
        self.source_paths = {path.resolve() for path in source_paths}

    def export(self, table: pd.DataFrame, destination: Path) -> Path:
        """Never replace existing files (including symlinks) or a known input path."""
        if destination.resolve() in self.source_paths:
            raise ValueError("An export cannot use an input file's path.")
        # Exclusive creation is the overwrite guard, including concurrent attempts.
        stream = destination.open("x", encoding="utf-8", newline="")
        try:
            with stream:
                writer = csv.writer(stream)
                writer.writerow(table.columns)
                for row in table.itertuples(index=False, name=None):
                    writer.writerow(
                        ""
                        if value is None or pd.isna(value)
                        else str(value).lower()
                        if isinstance(value, bool)
                        else str(value)
                        for value in row
                    )
        except Exception:
            # The stream is closed even if flush/close failed. Open failures never
            # reach this block, so an existing destination cannot be removed.
            destination.unlink()
            raise
        return destination


def _dependency_versions() -> dict[str, str]:
    versions = {name: version(name) for name in ("pandas", "numpy", "openpyxl", "PySide6")}
    for optional in ("scipy", "h5py"):
        try:
            versions[optional] = version(optional)
        except PackageNotFoundError:
            continue
    return versions


def export_import_results(
    results: Mapping[Path, ImportResult],
    selected_paths: Sequence[Path],
    parent: Path,
    export_format: ExportFormat = "csv",
    *,
    assignments: Mapping[Path, AnalysisMetadata] | None = None,
    analysis_plan: AnalysisPlan | None = None,
) -> Path:
    """Export the reviewed snapshot into a fresh folder; record excluded inputs.

    All tables are built before writing. An ordinary write failure removes this
    attempt's folder. The manifest is written last as the completion marker.
    """
    if export_format not in ("csv", "xlsx"):
        raise ValueError("Export format must be csv or xlsx.")
    paths = tuple(sorted(set(selected_paths), key=str))
    sessions = []
    summaries = {}
    phases = {}
    annotations = {}
    inputs = []
    for path in paths:
        result = results.get(path)
        annotation = (
            result.analysis_metadata
            if result
            else (assignments or {}).get(path, AnalysisMetadata())
        )
        if not isinstance(annotation, AnalysisMetadata):
            raise ValueError(
                "Invalid manual analysis metadata; review assignments before exporting."
            )
        session = result.session if result and not result.error else None
        if session is not None:
            if analysis_plan is None:
                validate_reviewed_result(result)
            sessions.append(session)
            annotations[session.source_file] = annotation
            summaries[session.source_file] = result.summary
            phases[session.source_file] = result.phase_summary
        raw = result.raw if result else None
        inputs.append(
            {
                "source_file": str(path),
                "status": "exported"
                if session is not None
                else "failed"
                if result is not None
                else "not_imported",
                "error": result.error if result else None,
                "source_sha256": raw.get("source_sha256") if raw else None,
                "warnings": session.warnings if session else raw.get("warnings", ()) if raw else (),
                "analysis_metadata": asdict(annotation),
                "analysis_metadata_sha256": annotation.sha256,
                "analysis_metadata_source": "manual" if annotation.is_assigned else "unassigned",
                "analysis_inclusion_status": annotation.inclusion_status,
            }
        )
    if not sessions:
        raise ValueError("Import at least one supported session before exporting.")
    expected_hashes = {
        path: results[path].raw.get("source_sha256")
        for path in paths
        if results.get(path) and results[path].raw is not None
    }
    if analysis_plan is None:
        require_current_sources(expected_hashes)
        derived = {}
    else:
        # Analysis checks both review versions and source freshness for the batch.
        derived = build_analysis(analysis_plan, results, paths, assignments)
    tables = {
        "sessions.csv": build_session_table(sessions, summaries, annotations),
        "choices.csv": build_choice_table(sessions, phases, annotations),
        "phase_metrics.csv": build_phase_table(sessions, phases, summaries, annotations),
    }
    tables.update(derived)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "application_version": __version__,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "dependency_versions": _dependency_versions(),
        "snapshot": (
            "Reviewed import results; source hashes checked before export and before completion."
        ),
        "configuration": {
            "row_levels": ["session", "choice", "phase"],
            "session_filter": "Successful imports, including sessions with warnings",
            "analysis_inclusion": (
                "Manual study flags only: all successful recordings are exported, including "
                "Excluded and Not reviewed. Display filters do not change "
                "inclusion or export scope."
            ),
            "choice_filter": "All normalized choice events, including invalid decoded choices",
            "order": "Source path, then normalizer event order (Med-PC C index)",
            "metrics": [
                {
                    "name": name,
                    "definition_version": DEFINITION_VERSION,
                    "unit": METRIC_UNITS[name],
                }
                for name in METRIC_LABELS
            ],
            "metric_definition_set": DEFINITION_SET,
            "metric_definition_version": DEFINITION_VERSION,
            "metric_eligibility_policy": ELIGIBILITY_POLICY,
            "choice_storage_policy": CHOICE_STORAGE_POLICY,
            "medpc_trials_per_minute": {
                "formula": "60 * validated recorded choices / S",
                "scope": "whole session",
                "duration_source": "S (task-relative seconds)",
                "unit": "choices/min",
                "saved_A3": "raw only; not substituted",
                "phase_table_copy": {
                    "value_column": WHOLE_SESSION_RATE_COLUMN,
                    "count_column": "session_total_choices",
                    "duration_column": "whole_session_duration_s",
                    "scope_column": "whole_session_rate_scope",
                    "status_column": "whole_session_rate_status",
                    "result_column": "whole_session_rate_result_json",
                    "meaning": "Same whole-session result copied for convenience; not a phase rate",
                },
            },
            "proportion_correct_denominator": "Recorded choices; no configured target substitution",
            "task_configuration": (
                "User-assigned phase per source; raw acquisition fields in metadata_json"
            ),
            "phase_definition_set": phase_metrics.DEFINITION_SET,
            "phase_definition_version": phase_metrics.DEFINITION_VERSION,
            "phase_policy": phase_metrics.POLICY,
            "phase_metrics": list(phase_metrics.METRIC_LABELS),
            "phase_configurations": [
                {
                    "source_file": str(p),
                    "configuration_sha256": phase.config.sha256,
                    "configuration": asdict(phase.config),
                }
                for p, phase in phases.items()
            ],
        },
        "serialization": {
            "encoding": "UTF-8",
            "delimiter": ",",
            "missing_csv": "empty field",
            "booleans": "true/false",
            "missing_json": "null",
            "decimals_json": "strings",
            "array_indices_json": "object keys as strings",
        },
        "tables": {
            name: {"rows": len(table), "columns": list(table.columns)}
            for name, table in tables.items()
        },
        "inputs": inputs,
        **(
            {
                "aggregation": {
                    **analysis_plan.record(),
                    "plan_sha256": analysis_plan.sha256,
                    "analysis_table_version": "1",
                    "tables": list(derived),
                }
            }
            if analysis_plan
            else {}
        ),
    }
    workbook = None
    if export_format == "xlsx":
        from trial_cruncher.excel import build_workbook

        workbook = build_workbook(
            tables["sessions.csv"],
            tables["choices.csv"],
            manifest,
            tables["phase_metrics.csv"],
            derived,
        )
    manifest_text = json_text(manifest)
    destination = Path(tempfile.mkdtemp(prefix="trial-cruncher-export-", dir=parent.resolve()))
    try:
        source_paths = (*paths, *(session.source_file for session in sessions))
        if workbook is not None:
            from trial_cruncher.excel import save_workbook

            save_workbook(workbook, destination / "results.xlsx", source_paths)
        else:
            writer = CSVExporter(source_paths)
            for name, table in tables.items():
                writer.export(table, destination / name)
        require_current_sources(expected_hashes)
        with (destination / "manifest.json").open("x", encoding="utf-8") as stream:
            stream.write(manifest_text + "\n")
    except Exception:
        try:
            shutil.rmtree(destination)
        except OSError:
            logger.exception("Could not remove incomplete export folder %s", destination)
        raise
    finally:
        if workbook is not None:
            workbook.close()
    return destination
