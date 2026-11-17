"""Excel serialization of reviewed tables, with literal text and lossless overflow."""

import json
import math
import re
from collections.abc import Sequence
from decimal import Decimal
from itertools import chain
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from trial_cruncher.aggregation import SHEETS
from trial_cruncher.analysis_metadata import ANNOTATION_COLUMNS, analysis_metadata_from_dict
from trial_cruncher.tables import WHOLE_SESSION_RATE_COLUMN, json_text

MAX_ROWS = 1_048_576
MAX_COLUMNS = 16_384
# Below Excel's 32,767-character and 253-line-feed cell limits, also for UTF-16.
TEXT_UNITS = 30_000
LINE_FEEDS = 250
INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
PROVENANCE_COLUMNS = ("kind", "sheet", "cell", "part", "parts", "text")
QUALITY_COLUMNS = (
    "record_type",
    "source_file",
    "input_status",
    "source_sha256",
    "error",
    "warnings_json",
    "metric",
    "value",
    "unit",
    "metric_status",
    "reasons_json",
    "definition_version",
    "policy",
) + ANNOTATION_COLUMNS


def _text_parts(text: str) -> list[str]:
    """Split without changing any character, including supplementary Unicode."""
    if INVALID_XML.search(text):
        raise ValueError("Text contains characters Excel cannot represent; use CSV export.")
    parts = []
    start = units = feeds = 0
    for index, char in enumerate(text):
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > TEXT_UNITS or feeds + (char == "\n") > LINE_FEEDS:
            parts.append(text[start:index])
            start, units, feeds = index, 0, 0
        units += size
        feeds += char == "\n"
    parts.append(text[start:])
    return parts


def _cell_value(value: Any) -> str | int | float | bool | None:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, str | bool):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Nonfinite decimal cannot be exported to Excel.")
        return str(value)  # Raw acquisition decimals retain precision and trailing zeros.
    if isinstance(value, int):
        return str(value) if len(str(abs(value))) > 15 else value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite number cannot be exported to Excel.")
        return value
    raise TypeError(f"Cannot export {type(value).__name__} to Excel.")


def _write_table(sheet: Worksheet, table: pd.DataFrame, overflow: list[tuple] | None) -> None:
    if len(table) + 1 > MAX_ROWS or len(table.columns) > MAX_COLUMNS:
        raise ValueError(f"{sheet.title} exceeds Excel's worksheet limits; use CSV export.")
    rows = [tuple(table.columns)]
    # Chain the header and body without making another copy of the table.
    for row_number, row in enumerate(chain(rows, table.itertuples(index=False, name=None)), 1):
        for column, original in enumerate(row, 1):
            value = _cell_value(original)
            cell = sheet.cell(row_number, column)
            if isinstance(value, str):
                try:
                    parts = _text_parts(value)
                except ValueError as exc:
                    raise ValueError(f"{sheet.title}!{cell.coordinate}: {exc}") from exc
                if len(parts) > 1:
                    if overflow is None:
                        raise ValueError("Provenance chunk exceeds Excel's text limits.")
                    first = len(overflow) + 2
                    overflow.extend(
                        ("overflow", sheet.title, cell.coordinate, i, len(parts), part)
                        for i, part in enumerate(parts, 1)
                    )
                    value = f"[Full text: Provenance rows {first}-{len(overflow) + 1}]"
                cell.value = value
                # openpyxl infers formulas and errors from strings unless overridden.
                cell.data_type = "s"
                cell.number_format = "@"
            else:
                cell.value = value
                if isinstance(value, int) and not isinstance(value, bool):
                    cell.number_format = "0"
                elif isinstance(value, float):
                    cell.number_format = (
                        "0.0000"
                        if table.columns[column - 1].endswith("proportion_correct")
                        else "0.###############"
                    )
    sheet.freeze_panes = "C2" if sheet.title in ("Quality", "Provenance") else "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 48
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="244761")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for column, label in enumerate(table.columns, 1):
        width = 48 if label in ("source_file", "text", "error") or label.endswith("_json") else 24
        if label == WHOLE_SESSION_RATE_COLUMN:
            width = 38
        sheet.column_dimensions[get_column_letter(column)].width = width


def build_workbook(
    sessions: pd.DataFrame,
    choices: pd.DataFrame,
    manifest: dict[str, Any],
    phases: pd.DataFrame,
    derived: dict[str, pd.DataFrame] | None = None,
) -> Workbook:
    """Prepare five sheets before reserving output; add Excel rules to the manifest."""
    quality = []
    by_source = {row["source_file"]: row for row in sessions.to_dict("records")}
    for item in manifest["inputs"]:
        common = {
            "source_file": item["source_file"],
            "input_status": item["status"],
            "source_sha256": item["source_sha256"],
            "error": item["error"],
            "warnings_json": json_text(item["warnings"]),
            **analysis_metadata_from_dict(item["analysis_metadata"]).export_fields(),
        }
        quality.append({**common, "record_type": "input"})
        session = by_source.get(item["source_file"])
        if session is not None:
            for metric in json.loads(session["metric_results_json"]):
                quality.append(
                    {
                        **common,
                        "record_type": "metric",
                        "metric": metric["name"],
                        "value": metric["value"],
                        "unit": metric["unit"],
                        "metric_status": metric["status"],
                        "reasons_json": json_text(metric["reasons"]),
                        "definition_version": metric["definition_version"],
                        "policy": session["metric_policy"],
                    }
                )
    for row in phases.to_dict("records"):
        for metric in json.loads(row["metric_results_json"]):
            quality.append(
                {
                    "record_type": "phase_metric",
                    **{key: row[key] for key in ANNOTATION_COLUMNS},
                    "source_file": row["source_file"],
                    "input_status": "exported",
                    "source_sha256": row["source_sha256"],
                    "warnings_json": row["warnings_json"],
                    "metric": metric["name"],
                    "value": metric["value"],
                    "unit": metric["unit"],
                    "metric_status": metric["status"],
                    "reasons_json": json_text(metric["reasons"]),
                    "definition_version": metric["definition_version"],
                    "policy": row["phase_policy"],
                }
            )
    quality_table = pd.DataFrame(
        [[row.get(column) for column in QUALITY_COLUMNS] for row in quality],
        columns=QUALITY_COLUMNS,
        dtype=object,
    )
    tables = {
        "Sessions": sessions,
        "Choices": choices,
        "Phase metrics": phases,
        "Quality": quality_table,
    }
    tables.update({SHEETS[name]: table for name, table in (derived or {}).items()})
    manifest["format"] = "xlsx"
    manifest["workbook_schema_version"] = "6"
    manifest["workbook"] = "results.xlsx"
    manifest["sheets"] = [*tables, "Provenance"]
    manifest["tables"] = {
        name: {"rows": len(table), "columns": list(table.columns)} for name, table in tables.items()
    }
    manifest["serialization"] = {
        "missing_excel": "blank cell; metric status and reasons retained",
        "empty_text": "blank cell; original values retained in raw JSON when present",
        "booleans": "native Excel booleans",
        "strings": "literal text, never formulas, links, dates, or error cells",
        "decimals": "exact text, including raw acquisition values",
        "large_integers": "more than 15 digits stored as exact text",
        "floats": "native Excel numbers; Excel numeric precision applies; raw JSON retained",
        "proportion_correct": "0 to 1 numeric proportion; no percent formatting",
        "missing_json": "null",
        "decimals_json": "strings",
        "array_indices_json": "object keys as strings",
        "overflow": (
            "Provenance rows keyed by original sheet and cell; concatenate text in part order"
        ),
        "provenance_manifest": (
            "Concatenate kind=manifest text in part order to recover manifest.json"
        ),
    }
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "Trial Cruncher"
    overflow: list[tuple] = []
    for name, table in tables.items():
        _write_table(workbook.create_sheet(name), table, overflow)
    parts = _text_parts(json_text(manifest))
    overflow.extend(
        ("manifest", None, None, i, len(parts), part) for i, part in enumerate(parts, 1)
    )
    _write_table(
        workbook.create_sheet("Provenance"),
        pd.DataFrame(overflow, columns=PROVENANCE_COLUMNS, dtype=object),
        None,
    )
    return workbook


def save_workbook(workbook: Workbook, destination: Path, source_paths: Sequence[Path] = ()) -> Path:
    """Exclusively create a workbook and remove only this file if writing fails."""
    if destination.resolve() in {path.resolve() for path in source_paths}:
        raise ValueError("An export cannot use an input file's path.")
    stream = destination.open("xb")
    try:
        with stream:
            workbook.save(stream)
    except Exception:
        destination.unlink()
        raise
    return destination
