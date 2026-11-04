"""Exclusive-create writers and complete session/choice export bundles."""

import csv
import logging
import platform
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Protocol

import pandas as pd

from trial_cruncher import __version__
from trial_cruncher.prl_metrics import (
    DEFINITION_SET,
    DEFINITION_VERSION,
    ELIGIBILITY_POLICY,
    METRIC_LABELS,
)
from trial_cruncher.processing import ImportResult
from trial_cruncher.tables import (
    SCHEMA_VERSION,
    build_choice_table,
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


def export_import_results(
    results: Mapping[Path, ImportResult],
    selected_paths: Sequence[Path],
    parent: Path,
    export_format: ExportFormat = "csv",
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
    inputs = []
    for path in paths:
        result = results.get(path)
        session = result.session if result and not result.error else None
        if session is not None:
            if result.summary is None:
                raise ValueError("Session metrics are missing; re-import before exporting.")
            sessions.append(session)
            summaries[session.source_file] = result.summary
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
            }
        )
    if not sessions:
        raise ValueError("Import at least one supported session before exporting.")
    tables = {
        "sessions.csv": build_session_table(sessions, summaries),
        "choices.csv": build_choice_table(sessions),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "application_version": __version__,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "dependency_versions": {
            name: version(name)
            for name in ("pandas", "numpy", "scipy", "h5py", "openpyxl", "PySide6")
        },
        "snapshot": "In-memory import results; sources were not re-read at export time.",
        "configuration": {
            "row_levels": ["session", "choice"],
            "session_filter": "Successful imports, including sessions with warnings",
            "choice_filter": "All normalized choice events, including invalid decoded choices",
            "order": "Source path, then normalizer event order (Med-PC C index)",
            "metrics": [
                {
                    "name": name,
                    "definition_version": DEFINITION_VERSION,
                    "unit": "%" if name == "prl.percent_correct" else "count",
                }
                for name in METRIC_LABELS
            ],
            "metric_definition_set": DEFINITION_SET,
            "metric_definition_version": DEFINITION_VERSION,
            "metric_eligibility_policy": ELIGIBILITY_POLICY,
            "percent_correct_denominator": "Recorded choices; no configured target substitution",
            "task_configuration": "No overrides; raw acquisition fields are in metadata_json",
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
    }
    workbook = None
    if export_format == "xlsx":
        from trial_cruncher.excel import build_workbook

        workbook = build_workbook(tables["sessions.csv"], tables["choices.csv"], manifest)
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
