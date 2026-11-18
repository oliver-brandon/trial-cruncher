"""Read-only projections of the desktop models for the embedded frontend.

The existing Qt models remain responsible for sorting, filtering, formatting,
and the distinction between unavailable and zero-valued observations.
"""

from pathlib import Path

from PySide6.QtCore import Qt

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
    if section == "Session metrics":
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
