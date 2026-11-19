"""Read-only projections of the desktop models for the embedded frontend.

The existing Qt models remain responsible for sorting, filtering, formatting,
and the distinction between unavailable and zero-valued observations.
"""

from itertools import islice
from pathlib import Path

from PySide6.QtCore import Qt

from trial_cruncher.compact_results import COLUMN_GUIDE, DATA_COLUMNS, data_reasons, trial_values
from trial_cruncher.gui.window import MainWindow

MAX_PAGE_SIZE = 500


def _bounds(offset: int, limit: int) -> tuple[int, int]:
    if type(offset) is not int or type(limit) is not int:
        raise ValueError("Page offset and limit must be integers.")
    if offset < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(
            f"Page offset must be nonnegative and limit between 1 and {MAX_PAGE_SIZE}."
        )
    return offset, limit


def batch(window: MainWindow, view: str, offset: int = 0, limit: int = 100) -> dict:
    """Return one page from the filtered, sorted session or phase proxy."""
    offset, limit = _bounds(offset, limit)
    if view == "data":
        return compact_batch(window, offset, limit)
    if view == "sessions":
        overview = window.overview
    elif view == "phases":
        overview = window.phase_overview
    else:
        raise ValueError("Unknown batch view.")
    proxy = overview.proxy
    header = overview.table.horizontalHeader()
    columns = [
        header.logicalIndex(i)
        for i in range(proxy.columnCount())
        if not overview.table.isColumnHidden(header.logicalIndex(i))
    ]
    headers = [str(proxy.headerData(i, Qt.Orientation.Horizontal) or "") for i in columns]
    numeric = [
        (5 <= i <= 13 or i == 16)
        if view == "sessions"
        else (4 <= i <= 24 or 27 <= i <= 29 or i == 33)
        for i in columns
    ]
    rows = []
    for position in range(offset, min(offset + limit, proxy.rowCount())):
        index = proxy.index(position, 0)
        source_row = proxy.mapToSource(index).row()
        entry = proxy.sourceModel().row(source_row)
        path = entry.path
        result = window.import_results.get(path)
        imported_phase = (
            result.phase_summary.config.phase if result and result.phase_summary else None
        )
        assigned_phase = window.phase_assignments.get(path)
        rows.append(
            {
                "path": str(path),
                "cells": [str(proxy.index(position, col).data() or "") for col in columns],
                "pending_phase": bool(
                    result and result.phase_summary and assigned_phase != imported_phase
                ),
                "imported_phase": imported_phase,
                "assigned_phase": assigned_phase,
            }
        )
    current = overview.table.currentIndex()
    selected = overview.current_path()
    return {
        "headers": headers,
        "columns": columns,
        "numeric": numeric,
        "rows": rows,
        "total": proxy.rowCount(),
        "batch_total": proxy.sourceModel().rowCount(),
        "offset": offset,
        "selected": str(selected) if selected is not None else None,
        "selected_position": current.row() if current.isValid() else None,
        "sort_column": proxy.sortColumn(),
        "sort_descending": proxy.sortOrder() == Qt.SortOrder.DescendingOrder,
    }


def compact_batch(window: MainWindow, offset: int, limit: int) -> dict:
    proxy = window.overview.proxy
    records = []
    for position in range(proxy.rowCount()):
        entry = proxy.sourceModel().row(proxy.mapToSource(proxy.index(position, 0)).row())
        result = entry.result
        usable = result is not None and result.session is not None and not entry.source_issue
        if usable:
            values = entry.compact_values
        else:
            subject = result.raw["headers"].get("Subject") if result and result.raw else None
            values = (subject, window.phase_assignments.get(entry.path), entry.annotation.condition)
            values += (None,) * (len(DATA_COLUMNS) - len(values))
        records.append((entry, values, usable))
    column, descending = getattr(window, "_compact_sort", (0, False))

    def sort_key(record):
        value = record[1][column]
        return value.casefold() if isinstance(value, str) else value

    present = sorted(
        (r for r in records if r[1][column] is not None), key=sort_key, reverse=descending
    )
    missing = [r for r in records if r[1][column] is None]
    records = present + missing
    rows = []
    for entry, values, usable in records[offset : offset + limit]:
        reasons = data_reasons(entry.result) if usable else {}
        state = (
            "Re-import required"
            if entry.source_issue
            else "Failed"
            if entry.result and entry.result.error
            else entry.state
        )
        cells = []
        for i, value in enumerate(values):
            if value is None:
                if i == 0:
                    cells.append(f"File: {entry.path.name}")
                elif i in (1, 2):
                    cells.append("Unassigned")
                else:
                    cells.append("Withheld" if entry.withheld else "Unavailable" if usable else "—")
            elif isinstance(value, float):
                cells.append(f"{value:.4f}")
            else:
                cells.append(str(value))
        rows.append(
            {
                "path": str(entry.path),
                "cells": cells,
                "row_state": "Withheld" if entry.withheld else state if not usable else "",
                "state_detail": entry.source_issue or (entry.result.error if entry.result else ""),
                "tooltips": [
                    reasons.get(name, "") or (str(value) if value is not None else "")
                    for name, value in zip(DATA_COLUMNS, values, strict=True)
                ],
                "pending_phase": bool(
                    entry.result
                    and entry.result.phase_summary
                    and window.phase_assignments.get(entry.path)
                    != entry.result.phase_summary.config.phase
                ),
                "imported_phase": entry.result.phase_summary.config.phase
                if entry.result and entry.result.phase_summary
                else None,
                "assigned_phase": window.phase_assignments.get(entry.path),
            }
        )
    selected = window.overview.current_path()
    return {
        "headers": DATA_COLUMNS,
        "descriptions": tuple(COLUMN_GUIDE.values()),
        "columns": list(range(len(DATA_COLUMNS))),
        "numeric": [i >= 3 for i in range(len(DATA_COLUMNS))],
        "rows": rows,
        "total": len(records),
        "batch_total": proxy.sourceModel().rowCount(),
        "offset": offset,
        "selected": str(selected) if selected else None,
        "sort_column": column,
        "sort_descending": descending,
    }


def batch_tooltip(window: MainWindow, view: str, path: str, column: int) -> str:
    """Return detailed provenance for a visible row and its original model column."""
    if view == "sessions":
        overview = window.overview
    elif view == "phases":
        overview = window.phase_overview
    else:
        raise ValueError("Unknown batch view.")
    if type(column) is not int or not 0 <= column < overview.proxy.columnCount():
        raise ValueError("Unknown table column.")
    candidate = Path(path)
    source = overview.model.source if view == "phases" else overview.model
    index = source.index_for_path(candidate)
    if not index.isValid():
        raise ValueError("Unknown selected source.")
    if view == "phases":
        index = overview.model.index(index.row(), 0)
    if not overview.proxy.mapFromSource(index).isValid():
        raise ValueError("Source is hidden by the current filters.")
    return overview.proxy.sourceModel().row(index.row()).tooltip(column)


def _widget_table(table) -> dict:
    headers = [
        table.horizontalHeaderItem(i).text() if table.horizontalHeaderItem(i) else ""
        for i in range(table.columnCount())
    ]
    rows = []
    for row in range(table.rowCount()):
        rows.append(
            [
                table.item(row, col).text() if table.item(row, col) else ""
                for col in range(table.columnCount())
            ]
        )
    return {"headers": headers, "rows": rows}


def detail_section(window: MainWindow, section: str, offset: int = 0, limit: int = 100) -> dict:
    """Read only the active inspector section, with bounded choice pages."""
    offset, limit = _bounds(offset, limit)
    review = window.review
    if section == "Trials":
        path = window._reviewed_path
        result = window.import_results.get(path)
        session = (
            result.session
            if result and not result.error and path not in window._source_issues
            else None
        )
        total = review.choice_model.rowCount() if session else 0
        content = {
            "headers": ["Trial", "Choice", "Outcome"],
            "rows": list(islice(trial_values(session), offset, offset + limit)) if session else [],
            "total": total,
            "offset": offset,
            "note": (
                "Choice: 1 = correct, 0 = incorrect. Outcome: 1 = rewarded, "
                "0 = unrewarded. — = unavailable."
            ),
        }
    elif section == "Session metrics":
        content = {
            "note": review.metric_note.text(),
            "table": _widget_table(review.metric_table),
            "diagnostics": review.metric_diagnostics.toPlainText(),
        }
    elif section == "Phase metrics":
        content = {
            "note": review.phase_label.text(),
            "table": _widget_table(review.phase_table),
            "diagnostics": review.phase_diagnostics.toPlainText(),
        }
    elif section == "Decoded choices":
        model = review.choice_model
        content = {
            "headers": list(model.HEADERS),
            "rows": [
                [model.index(row, col).data() for col in range(model.columnCount())]
                for row in range(offset, min(offset + limit, model.rowCount()))
            ],
            "total": model.rowCount(),
            "offset": offset,
        }
    else:
        fields = {
            "Session details": review.details,
            "Analysis metadata": review.analysis_details,
            "Warnings and checks": review.warnings,
            "Source text": review.source,
        }
        if section not in fields:
            raise ValueError("Unknown inspector section.")
        content = fields[section].toPlainText()
    summary = review.summary.text()
    path = window._reviewed_path
    index = window.overview.model.index_for_path(path)
    if index.isValid():
        row = window.overview.model.row(index.row())
        if row.withheld:
            summary += " · Metrics withheld"
        result = row.result
        if result and result.phase_summary:
            imported = result.phase_summary.config.phase
            pending = window.phase_assignments.get(path)
            if pending != imported:
                summary += (
                    f" · Imported phase: {imported or 'Unassigned'}. "
                    f"Re-import to apply: {pending or 'Unassigned'}."
                )
    return {"summary": summary, "content": content}
