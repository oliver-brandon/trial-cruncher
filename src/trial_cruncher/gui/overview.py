"""Read-only batch overview; path identity survives proxy sorting and filtering."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.models import MetricResult
from trial_cruncher.prl_metrics import METRIC_LABELS
from trial_cruncher.processing import ImportResult

HEADERS = (
    "File",
    "Quality",
    "Subject",
    "Program",
    "Date (source text)",
    "Duration (s)",
    "Choices",
    "Correct",
    "Incorrect",
    "Rewarded",
    "Unrewarded",
    "Proportion correct",
    "Warnings",
    "Trials/min\n(Med-PC)",
)
METRIC_NAMES = tuple(METRIC_LABELS)
ATTENTION_STATES = frozenset(
    {"Warnings", "Withheld", "Unavailable metrics", "Failed", "Not imported", "Re-import required"}
)


@dataclass(frozen=True)
class OverviewRow:
    path: Path
    result: ImportResult | None = None
    state: str = "Not imported"
    source_issue: str | None = None

    @property
    def withheld(self) -> bool:
        summary = self.result.summary if self.result else None
        if summary is None:
            return False
        quality = summary.diagnostics
        return bool(
            quality.c_indices_have_gaps
            or quality.invalid_record_count
            or quality.post_terminator_count
            or any(value is False for value in quality.summary_checks.values())
        )

    @property
    def quality(self) -> str:
        if self.result is None:
            return self.state
        if self.result.error or self.result.session is None:
            return "Failed"
        if self.withheld:
            return "Withheld"
        if self.result.summary is None or any(m.value is None for m in self.result.summary.metrics):
            return "Unavailable metrics"
        return "Warnings" if self.warnings else "Available"

    @property
    def warnings(self) -> tuple[str, ...]:
        if self.result is None:
            return ()
        if self.result.session is not None:
            return self.result.session.warnings
        return self.result.raw["warnings"] if self.result.raw else ()

    def metric(self, column: int) -> MetricResult | None:
        if self.result and self.result.summary:
            name = METRIC_NAMES[6 if column == 13 else column - 6]
            return next((m for m in self.result.summary.metrics if m.name == name), None)
        return None

    def value(self, column: int) -> str | int | float | None:
        result = self.result
        session = result.session if result else None
        headers = result.raw["headers"] if result and result.raw else {}
        if column == 0:
            return self.path.name
        if column == 1:
            return self.quality
        if column == 2:
            return session.subject_id if session else headers.get("Subject") or None
        if column == 3:
            return session.metadata.get("program") if session else headers.get("MSN") or None
        if column == 4:
            return headers.get("Start Date") or None
        if column == 5:
            return session.duration_s if session else None
        if 6 <= column <= 11 or column == 13:
            metric = self.metric(column)
            return metric.value if metric else None
        if column == 12:
            return len(self.warnings) if result else None
        return None

    def text(self, column: int) -> str:
        value = self.value(column)
        if value is not None:
            if column in (11, 13):
                return f"{value:.4f}"
            return str(value)
        if (6 <= column <= 11 or column == 13) and self.withheld:
            return "Withheld"
        if column >= 5 and self.result is None:
            return "Pending" if self.state == "Pending" else "Not imported"
        return "Unavailable"

    def tooltip(self, column: int) -> str:
        lines = [str(self.path), f"Quality: {self.quality}"]
        if self.source_issue:
            lines.append(self.source_issue)
        if self.result and self.result.error:
            lines.append(self.result.error)
        if 6 <= column <= 11 or column == 13:
            metric = self.metric(column)
            if metric:
                lines += [METRIC_LABELS[metric.name], f"Status: {metric.status}", *metric.reasons]
        elif column == 1 and self.result and self.result.summary:
            lines += list(
                dict.fromkeys(reason for m in self.result.summary.metrics for reason in m.reasons)
            )
        elif column == 4:
            lines.append("Original Start Date text; sorted as text, not a guessed calendar date.")
        elif column == 5 and self.value(column) is None:
            lines.append("Task duration S is unavailable; header elapsed time is not substituted.")
        lines += list(self.warnings)
        return "\n".join(lines)

    @property
    def search_text(self) -> str:
        fields = [str(self.path), *(self.text(column) for column in range(1, 5)), *self.warnings]
        if self.source_issue:
            fields.append(self.source_issue)
        if self.result and self.result.error:
            fields.append(self.result.error)
        if self.result and self.result.summary:
            fields.extend(
                reason for metric in self.result.summary.metrics for reason in metric.reasons
            )
        return "\n".join(fields).casefold()


class OverviewModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.rows: list[OverviewRow] = []
        self._row_by_path: dict[Path, int] = {}

    def set_source_issues(self, issues: Mapping[Path, str]) -> None:
        self.beginResetModel()
        self.rows = [
            OverviewRow(
                row.path,
                row.result,
                "Re-import required" if row.path in issues else row.state,
                issues.get(row.path),
            )
            for row in self.rows
        ]
        self.endResetModel()

    def set_files(self, paths: Sequence[Path], results: Mapping[Path, ImportResult]) -> None:
        old_states = {row.path: row.state for row in self.rows}
        self.beginResetModel()
        self.rows = [
            OverviewRow(path, results.get(path), old_states.get(path, "Not imported"))
            for path in sorted(set(paths), key=str)
        ]
        self._row_by_path = {row.path: i for i, row in enumerate(self.rows)}
        self.endResetModel()

    def start_import(self) -> None:
        self.beginResetModel()
        self.rows = [OverviewRow(row.path, state="Pending") for row in self.rows]
        self.endResetModel()

    def set_result(self, result: ImportResult) -> None:
        row = self._row_by_path[result.source_file]
        self.rows[row] = OverviewRow(result.source_file, result)
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(HEADERS) - 1))

    def finish_import(self) -> None:
        for index, row in enumerate(self.rows):
            if row.result is None:
                self.rows[index] = OverviewRow(row.path, state="Not imported (cancelled)")
        if self.rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.rows) - 1, len(HEADERS) - 1)
            )

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return row.text(index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.tooltip(index.column())
        if role == Qt.ItemDataRole.UserRole:
            return row.path
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() >= 5:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return HEADERS[section]
            if role == Qt.ItemDataRole.ToolTipRole:
                if 6 <= section <= 11 or section == 13:
                    return (
                        METRIC_LABELS[METRIC_NAMES[6 if section == 13 else section - 6]]
                        + "; unavailable/withheld values sort last."
                    )
                if section == 4:
                    return "Original Start Date header, sorted as text; no date format is inferred."
        return super().headerData(section, orientation, role)


class OverviewProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.search = ""
        self.program: str | None = None
        self.quality = "All statuses"
        self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, row, parent) -> bool:
        entry = self.sourceModel().rows[row]
        quality = entry.quality
        category = "Not imported" if quality.startswith("Not imported") else quality
        if self.quality == "Needs attention":
            if category not in ATTENTION_STATES:
                return False
        elif self.quality != "All statuses" and category != self.quality:
            return False
        if self.program is not None and (entry.value(3) or "") != self.program:
            return False
        return self.search in entry.search_text

    def lessThan(self, left, right) -> bool:
        a, b = self.sourceModel().rows[left.row()], self.sourceModel().rows[right.row()]
        av, bv = a.value(left.column()), b.value(right.column())
        if (av is None) != (bv is None):
            # Qt reverses comparison arguments for descending order. Compensate so
            # unavailable values stay at the end in either direction.
            return av is not None if self.sortOrder() == Qt.SortOrder.AscendingOrder else av is None
        if isinstance(av, str):
            av, bv = av.casefold(), bv.casefold()
        if av == bv:
            return str(a.path) < str(b.path)
        return av < bv


class BatchOverview(QWidget):
    path_selected = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search file, subject, date, or warning…")
        self.search.setAccessibleName("Search batch sessions")
        self.search.setClearButtonEnabled(True)
        self.program = QComboBox()
        self.program.setAccessibleName("Filter by program")
        self.program.addItem("All programs", None)
        self.quality = QComboBox()
        self.quality.setAccessibleName("Filter by quality status")
        self.quality.addItems(
            (
                "All statuses",
                "Needs attention",
                "Available",
                "Warnings",
                "Withheld",
                "Unavailable metrics",
                "Failed",
                "Not imported",
                "Pending",
            )
        )
        self.reset_filters = QPushButton("Reset filters")
        filters.addWidget(self.search, 1)
        filters.addWidget(self.program)
        filters.addWidget(self.quality)
        filters.addWidget(self.reset_filters)
        layout.addLayout(filters)
        self.count_label = QLabel()
        self.count_label.setWordWrap(True)
        layout.addWidget(self.count_label)
        self.model = OverviewModel(self)
        self.proxy = OverviewProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setAccessibleName("Batch session overview")
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        # Keep the percentage visible before the five count columns on narrow windows.
        self.table.horizontalHeader().moveSection(11, 6)
        for column, width in enumerate(
            (220, 150, 80, 160, 130, 105, 95, 95, 95, 100, 110, 145, 90, 130)
        ):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table)
        self.table.selectionModel().currentRowChanged.connect(self._selection_changed)
        self.search.textChanged.connect(self._filter_changed)
        self.program.currentIndexChanged.connect(self._filter_changed)
        self.quality.currentIndexChanged.connect(self._filter_changed)
        self.reset_filters.clicked.connect(self.clear_filters)
        for signal in (
            self.proxy.rowsInserted,
            self.proxy.rowsRemoved,
            self.proxy.modelReset,
            self.proxy.layoutChanged,
            self.model.dataChanged,
        ):
            signal.connect(self._view_changed)
        self._view_changed()

    def current_path(self) -> Path | None:
        index = self.table.currentIndex()
        return index.data(Qt.ItemDataRole.UserRole) if index.isValid() else None

    def select_path(self, path: Path | None) -> None:
        previous = self.current_path()
        row = self.model._row_by_path.get(path)
        index = (
            self.proxy.mapFromSource(self.model.index(row, 0)) if row is not None else QModelIndex()
        )
        self.table.setCurrentIndex(index)
        if not index.isValid():
            self.table.clearSelection()
        if previous == self.current_path():
            self._selection_changed()

    def set_files(self, paths: Sequence[Path], results: Mapping[Path, ImportResult]) -> None:
        selected = self.current_path()
        self.model.set_files(paths, results)
        self._update_programs()
        self.select_path(selected)
        if self.current_path() is None and self.proxy.rowCount():
            self.table.setCurrentIndex(self.proxy.index(0, 0))

    def start_import(self) -> None:
        selected = self.current_path()
        self.model.start_import()
        # Preserve the chosen program filter while results are being re-read.
        self.select_path(selected)

    def set_result(self, result: ImportResult) -> None:
        selected = self.current_path()
        self.model.set_result(result)
        program = self.model.rows[self.model._row_by_path[result.source_file]].value(3) or ""
        if self.program.findData(program) < 0:
            self.program.addItem(program or "Unavailable program", program)
        if self.current_path() != selected:
            self.select_path(selected)
        elif selected == result.source_file:
            self._selection_changed()

    def finish_import(self) -> None:
        selected = self.current_path()
        self.model.finish_import()
        self._update_programs()
        self.select_path(selected)

    def _update_programs(self) -> None:
        selected = self.program.currentData()
        programs = {row.value(3) or "" for row in self.model.rows}
        if selected is not None:
            programs.add(selected)
        self.program.blockSignals(True)
        self.program.clear()
        self.program.addItem("All programs", None)
        for program in sorted(programs):
            self.program.addItem(program or "Unavailable program", program)
        self.program.setCurrentIndex(max(0, self.program.findData(selected)))
        self.program.blockSignals(False)

    def clear_filters(self) -> None:
        self.search.clear()
        self.program.setCurrentIndex(0)
        self.quality.setCurrentIndex(0)

    def _filter_changed(self, *args) -> None:
        selected = self.current_path()
        self.proxy.search = self.search.text().strip().casefold()
        self.proxy.program = self.program.currentData()
        self.proxy.quality = self.quality.currentText()
        self.proxy.invalidate()
        self.select_path(selected)
        self._view_changed()

    def _selection_changed(self, *args) -> None:
        self.path_selected.emit(self.current_path())

    def _view_changed(self, *args) -> None:
        visible, total = self.proxy.rowCount(), self.model.rowCount()
        prefix = "No files match the filters. " if total and not visible else ""
        self.count_label.setText(
            f"{prefix}Showing {visible} of {total} files. Import and export use the full batch."
        )
