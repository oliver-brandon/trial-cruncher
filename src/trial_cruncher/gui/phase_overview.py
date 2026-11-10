"""Batch phase comparisons projected from the authoritative import overview rows."""

from dataclasses import dataclass
from html import escape
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

from trial_cruncher.gui.overview import OverviewModel, OverviewRow
from trial_cruncher.models import MetricResult
from trial_cruncher.phase_metrics import METRIC_LABELS, PhaseSummary, RatioEvidence
from trial_cruncher.prl_metrics import MEDPC_RATE

HEADERS = (
    "File",
    "Subject",
    "Phase (imported)",
    "Phase status",
    "Choices\n(N)",
    "Proportion\ncorrect",
    "Perseverative\nerrors",
    "Regressive\nerrors",
    "Adjusted regressive\nproportion",
    "Postcriterion\nN (denominator)",
    "Criterion\nreached",
    "Criterion choice\n(1-based)",
    "Eligible\npairs",
    "Win-stay\ncorrect",
    "WS correct\nnumerator",
    "WS correct\ndenominator",
    "Win-stay\nincorrect",
    "WS incorrect\nnumerator",
    "WS incorrect\ndenominator",
    "Lose-shift\ncorrect",
    "LS correct\nnumerator",
    "LS correct\ndenominator",
    "Lose-shift\nincorrect",
    "LS incorrect\nnumerator",
    "LS incorrect\ndenominator",
    "Program",
    "Date (source text)",
    "Session\nchoices",
    "Task duration\nS (seconds)",
    "Trials/min\n(Med-PC)",
    "Rate status",
)
METRIC_COLUMNS = {5: 0, 6: 1, 7: 2, 8: 3, 13: 4, 16: 5, 19: 6, 22: 7}
RATIO_COLUMNS = {c: i for i, start in enumerate((13, 16, 19, 22)) for c in range(start, start + 3)}
VIEWS = {
    "Errors and criterion": tuple(range(11)),
    "Win-stay": (*range(4), 12, *range(13, 19)),
    "Lose-shift": (*range(4), 12, *range(19, 25)),
    "Session rate": (0, 1, 2, 27, 28, 29, 30),
    "All metrics": tuple(range(len(HEADERS))),
}
PHASE_STATES = {
    "available": "Available",
    "partially_available": "Some metrics unavailable",
    "unavailable": "Unavailable metrics",
    "phase_unassigned": "Phase unassigned",
    "withheld": "Withheld",
}


@dataclass(frozen=True)
class PhaseRow:
    source: OverviewRow

    @property
    def path(self) -> Path:
        return self.source.path

    @property
    def phase(self) -> PhaseSummary | None:
        result = self.source.result
        return (
            result.phase_summary
            if result and result.session and not result.error and not self.source.source_issue
            else None
        )

    @property
    def phase_key(self) -> str | None:
        return (self.phase.config.phase or "") if self.phase else None

    @property
    def status(self) -> str:
        if self.source.source_issue:
            return "Re-import required"
        result = self.source.result
        if result is None:
            return self.source.state
        if result.error or result.session is None:
            return "Failed"
        if self.phase is None:
            return "Unavailable metrics"
        status = PHASE_STATES[self.phase.status]
        return "Warnings" if status == "Available" and self.source.warnings else status

    @property
    def rate(self) -> MetricResult | None:
        result = self.source.result
        if self.source.source_issue or not result or result.error or not result.summary:
            return None
        return next((m for m in result.summary.metrics if m.name == MEDPC_RATE), None)

    @property
    def rate_status(self) -> str:
        metric = self.rate
        if metric is None:
            return self.status
        if metric.value is None:
            return "Withheld" if self.source.withheld else "Unavailable metrics"
        return "Warnings" if metric.warnings else "Available"

    def metric(self, column: int) -> MetricResult | None:
        if column == 29:
            return self.rate
        phase = self.phase
        if phase is None:
            return None
        if column in METRIC_COLUMNS:
            return phase.metrics[METRIC_COLUMNS[column]]
        if column in RATIO_COLUMNS:
            return phase.metrics[4 + RATIO_COLUMNS[column]]
        if column == 9:
            return phase.metrics[3]
        return None

    def ratio(self, column: int) -> RatioEvidence | None:
        if self.phase is None:
            return None
        if column in RATIO_COLUMNS:
            return self.phase.strategies[RATIO_COLUMNS[column]]
        return self.phase.diagnostics.adjusted_regressive if column in (8, 9) else None

    def value(self, column: int) -> str | int | float | bool | None:
        if column == 0:
            return self.path.name
        if column == 3:
            return self.status
        if column == 30:
            return self.rate_status
        if self.source.source_issue:
            return None
        if column in (1, 25, 26):
            return self.source.value({1: 2, 25: 3, 26: 4}[column])
        result = self.source.result
        if column in (27, 28, 29):
            if not result or result.error or not result.session:
                return None
            if column == 27:
                return result.summary.metrics[0].value if result.summary else None
            if column == 28:
                return result.session.duration_s
            return self.rate.value if self.rate else None
        phase = self.phase
        if phase is None:
            return None
        if column == 2:
            return phase.config.phase
        if column in METRIC_COLUMNS:
            return self.metric(column).value
        if column in RATIO_COLUMNS:
            evidence = self.ratio(column)
            return evidence.numerator if (column - 13) % 3 == 1 else evidence.denominator
        d = phase.diagnostics
        return {
            4: d.valid_choice_count,
            9: d.adjusted_regressive.denominator,
            10: d.criterion_reached,
            11: d.criterion_choice_ordinal,
            12: d.eligible_pair_count,
        }.get(column)

    def text(self, column: int) -> str:
        value = self.value(column)
        if value is not None:
            if isinstance(value, bool):
                return "Yes" if value else "No"
            return f"{value:.4f}" if isinstance(value, float) else str(value)
        if column == 2 and self.phase:
            return "Unassigned"
        if 4 <= column <= 24 and self.status == "Withheld":
            return "Withheld"
        if column in (27, 29) and self.rate_status == "Withheld":
            return "Withheld"
        if column not in (0, 1, 3, 25, 26) and self.source.result is None:
            return "Pending" if self.status == "Pending" else "Not imported"
        return "Unavailable"

    def tooltip(self, column: int) -> str:
        lines = [str(self.path), f"Phase status: {self.status}"]
        if column >= 27:
            lines = [
                str(self.path),
                f"Rate status: {self.rate_status}",
                "Whole-session Med-PC rate = 60 × recorded choices / S.",
                "Includes waiting/timeout time; independent of phase assignment.",
                f"Recorded choices: {self.value(27)}",
                f"Duration S (seconds): {self.value(28)}",
            ]
            if self.rate:
                lines += [
                    f"Session definition: {self.rate.definition_version}",
                    f"Unit: {self.rate.unit}",
                    f"Full value: {self.rate.value}",
                    *self.rate.reasons,
                ]
            if self.source.source_issue:
                lines.append(self.source.source_issue)
            if self.source.result and self.source.result.error:
                lines.append(self.source.result.error)
            return "\n".join((*lines, *self.source.warnings))
        if self.source.source_issue:
            lines.append(self.source.source_issue)
        if self.source.result and self.source.result.error:
            lines.append(self.source.result.error)
        phase = self.phase
        if phase:
            lines += [
                f"Imported phase: {phase.config.phase or 'Unassigned'}",
                f"Definition: {phase.definition_set} v{phase.definition_version}",
                f"Policy: {phase.eligibility_policy}",
            ]
            metric = self.metric(column)
            if metric:
                lines += [
                    METRIC_LABELS[metric.name],
                    f"Unit: {metric.unit}",
                    f"Full value: {metric.value if metric.value is not None else 'Unavailable'}",
                    *metric.reasons,
                ]
            else:
                lines += list(dict.fromkeys(reason for m in phase.metrics for reason in m.reasons))
            ratio = self.ratio(column)
            if ratio:
                numerator = ratio.numerator if ratio.numerator is not None else "Unavailable"
                denominator = ratio.denominator if ratio.denominator is not None else "Unavailable"
                lines += [
                    f"Numerator: {numerator}",
                    f"Denominator: {denominator}",
                ]
            if column in (7, 9, 10, 11) and phase.diagnostics.postcriterion_choice_count == 0:
                lines.append(
                    "No postcriterion choices: zero regressive errors does not establish "
                    "maintenance; adjusted proportion is undefined."
                )
        if column == 11:
            lines.append(
                "One-based ordinal of the choice completing the first three-correct run; "
                "not a trial ID."
            )
        if column == 26:
            lines.append(
                "Original Start Date header; sorted as text, not inferred chronological order."
            )
        lines += list(self.source.warnings)
        return "\n".join(lines)

    @property
    def search_text(self) -> str:
        return "\n".join(
            (
                str(self.path),
                self.text(1),
                self.text(2),
                self.text(25),
                self.text(26),
                self.tooltip(3),
            )
        ).casefold()


class PhaseModel(QAbstractTableModel):
    about_to_refresh = Signal()
    refreshed = Signal()

    def __init__(self, source: OverviewModel, parent=None) -> None:
        super().__init__(parent)
        self.source = source
        source.modelAboutToBeReset.connect(self._begin_reset)
        source.modelReset.connect(self._end_reset)
        source.dataChanged.connect(self._data_changed)

    def _begin_reset(self) -> None:
        self.about_to_refresh.emit()
        self.beginResetModel()

    def _end_reset(self) -> None:
        self.endResetModel()
        self.refreshed.emit()

    def _data_changed(self, top, bottom, *args) -> None:
        self.about_to_refresh.emit()
        self.dataChanged.emit(self.index(top.row(), 0), self.index(bottom.row(), len(HEADERS) - 1))
        self.refreshed.emit()

    def row(self, index: int) -> PhaseRow:
        return PhaseRow(self.source.rows[index])

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else self.source.rowCount()

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self.rowCount():
            return None
        row = self.row(index.row())
        if role == Qt.ItemDataRole.DisplayRole:
            return row.text(index.column())
        if role == Qt.ItemDataRole.ToolTipRole:
            return "<qt>" + escape(row.tooltip(index.column())).replace("\n", "<br>") + "</qt>"
        if role == Qt.ItemDataRole.UserRole:
            return row.path
        if role == Qt.ItemDataRole.TextAlignmentRole and (
            4 <= index.column() <= 24 or 27 <= index.column() <= 29
        ):
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(HEADERS):
            if role == Qt.ItemDataRole.DisplayRole:
                return HEADERS[section]
            if role == Qt.ItemDataRole.ToolTipRole:
                label = HEADERS[section].replace("\n", " ")
                if section in RATIO_COLUMNS:
                    label += f" — {list(METRIC_LABELS.values())[4 + RATIO_COLUMNS[section]]}"
                return (
                    label
                    + "; numeric columns sort at full precision, with unavailable values last."
                )
        return super().headerData(section, orientation, role)


class PhaseProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.search = ""
        self.phase: str | None = None
        self.status = "All statuses"
        self.rate_view = False
        self.setDynamicSortFilter(True)

    def filterAcceptsRow(self, index, parent) -> bool:
        row = self.sourceModel().row(index)
        status = row.rate_status if self.rate_view else row.status
        status = "Not imported" if status.startswith("Not imported") else status
        if self.status == "Needs attention":
            if status in ("Available", "Pending"):
                return False
        elif self.status != "All statuses" and status != self.status:
            return False
        if self.phase is not None and row.phase_key != self.phase:
            return False
        return self.search in row.search_text

    def lessThan(self, left, right) -> bool:
        a, b = self.sourceModel().row(left.row()), self.sourceModel().row(right.row())
        av, bv = a.value(left.column()), b.value(right.column())
        if (av is None) != (bv is None):
            return av is not None if self.sortOrder() == Qt.SortOrder.AscendingOrder else av is None
        if isinstance(av, str):
            av, bv = av.casefold(), bv.casefold()
        if av == bv:
            return str(a.path) < str(b.path)
        return av < bv


class BatchPhaseOverview(QWidget):
    path_selected = Signal(object)

    def __init__(self, source: OverviewModel, parent=None) -> None:
        super().__init__(parent)
        self._refreshing = False
        self._saved_path = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search file, subject, phase, or reason…")
        self.search.setAccessibleName("Search batch phase results")
        self.search.setClearButtonEnabled(True)
        self.phase_filter = QComboBox()
        self.phase_filter.setAccessibleName("Filter imported phase")
        self.phase_filter.addItem("All phases", None)
        self.status_filter = QComboBox()
        self.status_filter.setAccessibleName("Filter phase result status")
        self.status_filter.addItems(
            [
                "All statuses",
                "Needs attention",
                "Available",
                "Warnings",
                "Some metrics unavailable",
                "Unavailable metrics",
                "Phase unassigned",
                "Withheld",
                "Re-import required",
                "Failed",
                "Not imported",
                "Pending",
            ]
        )
        self.column_view = QComboBox()
        self.column_view.setAccessibleName("Phase metric columns")
        self.column_view.addItems(list(VIEWS))
        self.reset_filters = QPushButton("Reset filters")
        for widget in (
            self.search,
            self.phase_filter,
            self.status_filter,
            self.column_view,
            self.reset_filters,
        ):
            filters.addWidget(widget, 1 if widget is self.search else 0)
        layout.addLayout(filters)
        self.count_label = QLabel()
        self.count_label.setWordWrap(True)
        layout.addWidget(self.count_label)
        self.model = PhaseModel(source, self)
        self.proxy = PhaseProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setAccessibleName("Batch phase results")
        self.table.setModel(self.proxy)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setMinimumHeight(48)
        widths = (
            180,
            70,
            110,
            165,
            60,
            100,
            95,
            95,
            135,
            110,
            80,
            100,
            80,
            115,
            85,
            95,
            115,
            85,
            95,
            115,
            85,
            95,
            115,
            85,
            95,
            160,
            130,
            100,
            130,
            130,
            175,
        )
        for column, width in enumerate(widths):
            self.table.setColumnWidth(column, width)
        layout.addWidget(self.table)
        self.table.selectionModel().currentRowChanged.connect(self._selection_changed)
        self.search.textChanged.connect(self._filter_changed)
        self.phase_filter.currentIndexChanged.connect(self._filter_changed)
        self.status_filter.currentIndexChanged.connect(self._filter_changed)
        self.column_view.currentTextChanged.connect(self._columns_changed)
        self.reset_filters.clicked.connect(self.clear_filters)
        self.model.about_to_refresh.connect(self._remember_selection)
        self.model.refreshed.connect(self._refresh)
        for signal in (
            self.proxy.rowsInserted,
            self.proxy.rowsRemoved,
            self.proxy.modelReset,
            self.proxy.layoutChanged,
        ):
            signal.connect(self._view_changed)
        self._columns_changed()
        self._refresh()

    def current_path(self) -> Path | None:
        return self.table.currentIndex().data(Qt.ItemDataRole.UserRole)

    def select_path(self, path: Path | None) -> None:
        row = self.model.source._row_by_path.get(path)
        index = (
            self.proxy.mapFromSource(self.model.index(row, 0)) if row is not None else QModelIndex()
        )
        self.table.setCurrentIndex(index)
        if not index.isValid():
            self.table.clearSelection()
        self._selection_changed()

    def _remember_selection(self) -> None:
        self._saved_path = self.current_path()
        self._refreshing = True

    def _refresh(self) -> None:
        selected = self.phase_filter.currentData()
        phases = {self.model.row(i).phase_key for i in range(self.model.rowCount())}
        phases.discard(None)
        if selected is not None:
            phases.add(selected)
        self.phase_filter.blockSignals(True)
        self.phase_filter.clear()
        self.phase_filter.addItem("All phases", None)
        for phase in sorted(phases):
            self.phase_filter.addItem(phase or "Unassigned phase", phase)
        self.phase_filter.setCurrentIndex(max(0, self.phase_filter.findData(selected)))
        self.phase_filter.blockSignals(False)
        self._refreshing = False
        self.select_path(self._saved_path)
        self._view_changed()

    def clear_filters(self) -> None:
        self.search.clear()
        self.phase_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)

    def _filter_changed(self, *args) -> None:
        selected = self.current_path()
        self._refreshing = True
        self.proxy.search = self.search.text().strip().casefold()
        self.proxy.phase = self.phase_filter.currentData()
        self.proxy.status = self.status_filter.currentText()
        self.proxy.invalidate()
        self._refreshing = False
        self.select_path(selected)
        self._view_changed()

    def _columns_changed(self, *args) -> None:
        columns = VIEWS[self.column_view.currentText()]
        rate_view = self.column_view.currentText() == "Session rate"
        if self.proxy.rate_view != rate_view:
            self.proxy.rate_view = rate_view
            self.status_filter.setCurrentIndex(0)
            self.status_filter.setAccessibleName(
                "Filter session rate status" if rate_view else "Filter phase result status"
            )
            self._filter_changed()
        for column in range(len(HEADERS)):
            self.table.setColumnHidden(column, column not in columns)
        if self.proxy.sortColumn() not in columns:
            self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def _selection_changed(self, *args) -> None:
        if not self._refreshing:
            self.path_selected.emit(self.current_path())

    def _view_changed(self, *args) -> None:
        visible, total = self.proxy.rowCount(), self.model.rowCount()
        prefix = "No files match the filters. " if total and not visible else ""
        units = (
            "Med-PC rate uses whole-session choices and S (seconds)."
            if self.proxy.rate_view
            else "Phase ratios use 0–1."
        )
        self.count_label.setText(
            f"{prefix}Showing {visible} of {total} files. Import/export use the full batch. "
            f"{units} Unavailable is not zero. Labels are from the last import."
        )
