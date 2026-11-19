"""Readable compact workbook from the reviewed session snapshots."""

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter, quote_sheetname
from openpyxl.worksheet.hyperlink import Hyperlink

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.compact_export import compact_metadata
from trial_cruncher.compact_results import COLUMN_GUIDE, DATA_COLUMNS, data_values, trial_values
from trial_cruncher.excel import (
    MAX_COLUMNS,
    MAX_ROWS,
    PROVENANCE_COLUMNS,
    _cell_value,
    _text_parts,
)
from trial_cruncher.processing import ImportResult

MAX_SHEET_HYPERLINKS = 65_530


def _truncate_name(value: str, limit: int) -> str:
    value = value[:limit]
    while len(value.encode("utf-16-le")) // 2 > limit:
        value = value[:-1]
    return value


def _sheet_name(subject: str, used: set[str]) -> str:
    name = re.sub(r"[\[\]:*?/\\]", "_", subject).strip("'") or "Unassigned"
    name = _truncate_name(name, 31).strip("'") or "Unassigned"
    base = name
    number = 2
    while name.casefold() in used:
        suffix = f" ({number})"
        name = _truncate_name(base, 31 - len(suffix)).strip("'") + suffix
        number += 1
    used.add(name.casefold())
    return name


def _write_literal(sheet, row: int, col: int, value, overflow: list[tuple]) -> None:
    value = _cell_value(value)
    if value is None:
        return
    cell = sheet.cell(row, col)
    if isinstance(value, str):
        parts = _text_parts(value)
        if len(parts) > 1:
            overflow.extend(
                ("overflow", sheet.title, cell.coordinate, i, len(parts), part)
                for i, part in enumerate(parts, 1)
            )
            value = "[Full text in Metadata]"
        cell.value = value
        cell.data_type = "s"
        cell.number_format = "@"
    else:
        cell.value = value


def _write_frame(sheet, frame: pd.DataFrame, overflow: list[tuple]) -> None:
    if len(frame) + 1 > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        raise ValueError(f"{sheet.title} exceeds Excel worksheet limits; use CSV export.")
    for col, label in enumerate(frame.columns, 1):
        cell = sheet.cell(1, col, label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="244761")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        width = min(42, max(14, len(label) + 3))
        if sheet.title == "Data":
            width = min(17, max(12, len(label) + 3))
        if label in ("Source file", "Error", "Warnings", "Metric unavailability"):
            width = 45
        sheet.column_dimensions[get_column_letter(col)].width = width
    sheet.row_dimensions[1].height = 32
    for row_index, values in enumerate(frame.itertuples(index=False, name=None), 2):
        for col, value in enumerate(values, 1):
            _write_literal(sheet, row_index, col, value, overflow)
            if isinstance(value, float) and sheet.title == "Data":
                sheet.cell(row_index, col).number_format = "0.0000"
            elif frame.columns[col - 1] in ("Metric unavailability", "Warnings", "Error") and value:
                sheet.cell(row_index, col).alignment = Alignment(wrap_text=True, vertical="top")
    sheet.freeze_panes = "B2" if sheet.title == "Data" else "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(frame.columns))}{len(frame) + 1}"


def build_compact_workbook(
    results: Mapping[Path, ImportResult],
    paths: Sequence[Path],
    manifest: dict,
    assignments: Mapping[Path, AnalysisMetadata] | None = None,
) -> Workbook:
    """Build compact Data, animal choices and Metadata sheets."""
    selected = [
        results[p]
        for p in paths
        if p in results and results[p].session is not None and not results[p].error
    ]
    data = pd.DataFrame([data_values(r) for r in selected], columns=DATA_COLUMNS, dtype=object)
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "Trial Cruncher"
    overflow: list[tuple] = []
    _write_frame(workbook.create_sheet("Data"), data, overflow)
    locations = {}
    data_rows = {result.source_file: row for row, result in enumerate(selected, 2)}
    groups = defaultdict(list)
    for result in selected:
        subject = result.session.subject_id
        groups[(subject, None if subject else result.source_file)].append(result)
    used = {"data", "metadata", "history"}
    for (subject, _), sessions in groups.items():
        if len(sessions) * 4 - 1 > MAX_COLUMNS:
            raise ValueError(
                "Animal choices exceed Excel's worksheet column limit; use CSV export."
            )
        sheet = workbook.create_sheet(_sheet_name(subject or "Unassigned", used))
        sheet.freeze_panes = "A3"
        for index, result in enumerate(sessions):
            col = index * 4 + 1
            locations[str(result.source_file)] = f"{sheet.title}!{get_column_letter(col)}"
            id_cell = workbook["Data"].cell(data_rows[result.source_file], 1)
            if result.session.subject_id and len(selected) <= MAX_SHEET_HYPERLINKS:
                id_cell.hyperlink = Hyperlink(
                    ref=id_cell.coordinate,
                    location=f"{quote_sheetname(sheet.title)}!{get_column_letter(col)}1",
                    tooltip="Open this recording's choices",
                )
                id_cell.font = Font(color="2458A5", underline="single")
            phase = result.phase_summary.config.phase if result.phase_summary else None
            date = result.raw["headers"].get("Start Date") if result.raw else None
            for j, text in enumerate((phase, result.analysis_metadata.condition, date)):
                _write_literal(sheet, 1, col + j, text, overflow)
            for j, text in enumerate(("Trial", "Choice (correct)", "Outcome (rewarded)")):
                cell = sheet.cell(2, col + j, text)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="244761")
                cell.alignment = Alignment(wrap_text=True)
                sheet.column_dimensions[get_column_letter(col + j)].width = 23
            for ordinal, correct, rewarded in trial_values(result.session):
                if ordinal + 2 > MAX_ROWS:
                    raise ValueError(
                        "Animal choices exceed the worksheet row limit; use CSV export."
                    )
                for j, value in enumerate((ordinal, correct, rewarded)):
                    _write_literal(sheet, ordinal + 2, col + j, value, overflow)
    metadata = compact_metadata(results, paths, assignments, manifest)
    # Overflow is appended to Metadata. Preserve the existing serializer's
    # literal-text, Unicode and formula-injection protections.
    metadata.insert(
        2,
        "Choices location",
        pd.Series([locations.get(path) for path in metadata["Source file"]], dtype=object),
    )
    sheet = workbook.create_sheet("Metadata")
    _write_frame(sheet, metadata, overflow)
    guide_start = len(metadata) + 4
    guide = {
        "Choice": "1 = correct lever, 0 = incorrect lever.",
        "Outcome": "1 = rewarded, 0 = unrewarded.",
        "Blank cells": "Missing or unavailable. See the reason beside the source recording above.",
        **COLUMN_GUIDE,
    }
    if guide_start + len(guide) > MAX_ROWS:
        raise ValueError("Metadata exceeds Excel's worksheet row limit; use CSV export.")
    sheet.cell(guide_start, 1, "Column guide").font = Font(bold=True)
    for row, (name, meaning) in enumerate(guide.items(), guide_start + 1):
        sheet.cell(row, 1, name)
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=5)
        cell = sheet.cell(row, 2, meaning)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.row_dimensions[row].height = 29
    manifest["format"] = "xlsx"
    manifest["workbook"] = "results.xlsx"
    manifest["sheets"] = workbook.sheetnames
    manifest["choice_encoding"] = (
        "Choice: 1 correct, 0 incorrect; Outcome: 1 rewarded, 0 unrewarded; blank unavailable."
    )
    manifest["tables"] = {
        "Data": {"rows": len(data), "columns": list(DATA_COLUMNS)},
        "Metadata": {"rows": len(metadata), "columns": list(metadata.columns)},
    }
    manifest["animal_sheets"] = workbook.sheetnames[1:-1]
    manifest["serialization"] = {
        "missing": "blank cell; see Metadata for metric reasons",
        "text": "literal text, with overflow chunks in Metadata",
        "numbers": "native Excel numbers; displayed decimals do not change stored precision",
    }
    if overflow:
        start = sheet.max_row + 3
        if start + len(overflow) > MAX_ROWS:
            raise ValueError("Metadata exceeds Excel's worksheet row limit; use CSV export.")
        for i, label in enumerate(PROVENANCE_COLUMNS, 1):
            sheet.cell(start, i, label)
        for index, entry in enumerate(overflow, start + 1):
            kind, sheet_name, coordinate, part, parts, _ = entry
            if part == 1:
                cell = workbook[sheet_name][coordinate]
                cell.value = f"[Full text: Metadata rows {index}-{index + parts - 1}]"
                cell.data_type = "s"
            for col, value in enumerate(entry, 1):
                if value is not None:
                    cell = sheet.cell(index, col)
                    cell.value = value
                    if isinstance(value, str):
                        cell.data_type = "s"
    return workbook
