"""Configure an animal analysis and inspect tables computed in a background worker."""

from pathlib import Path

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QObject, QRunnable, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableView,
    QTabWidget,
    QVBoxLayout,
)

from trial_cruncher.aggregation import SHEETS, AnalysisPlan, build_analysis
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.phase_metrics import METRIC_LABELS as PHASE_LABELS
from trial_cruncher.prl_metrics import METRIC_LABELS as SESSION_LABELS
from trial_cruncher.processing import ImportResult
from trial_cruncher.source_tracking import SourcesChangedError


def _choices(labels, selected):
    widget = QListWidget()
    for label in labels:
        item = QListWidgetItem(label, widget)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if label in selected else Qt.CheckState.Unchecked)
    return widget


def _checked(widget):
    return tuple(
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).checkState() == Qt.CheckState.Checked
    )


class PlanDialog(QDialog):
    EDIT_METADATA = 2

    def __init__(self, conditions, phases, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Animal analysis")
        self.plan = plan
        layout = QFormLayout(self)
        self.design = QComboBox()
        self.design.addItems(["between-subjects", "within-subjects"])
        self.design.setPlaceholderText("Choose comparison design")
        self.design.setCurrentIndex(-1)
        if plan:
            self.design.setCurrentText(plan.design)
        self.conditions = _choices(
            sorted(conditions | (set(plan.conditions) if plan else set())),
            plan.conditions if plan else (),
        )

        def phase_order(label):
            return ({"acquisition": 0, "reversal": 1}.get(label.casefold(), 2), label)

        self.phases = _choices(
            sorted(phases | (set(plan.phases) if plan else set()), key=phase_order),
            plan.phases if plan else (),
        )
        layout.addRow(
            QLabel("Use Session metadata to Include one recording per animal, condition and phase.")
        )
        for label, control in (
            ("Design", self.design),
            ("Conditions", self.conditions),
            ("Phases", self.phases),
        ):
            layout.addRow(label, control)
        if not conditions:
            layout.addRow(QLabel("Assign a condition to the recordings in Session metadata."))
            edit = QPushButton("Open session metadata…")
            edit.clicked.connect(lambda: self.done(self.EDIT_METADATA))
            layout.addRow(edit)
        if not phases:
            layout.addRow(QLabel("Use Assign phases… and Import Med-PC to load phase results."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.addButton("Apply and preview", QDialogButtonBox.ButtonRole.AcceptRole)
        clear = buttons.addButton("Disable analysis", QDialogButtonBox.ButtonRole.ResetRole)
        clear.clicked.connect(self.disable)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def disable(self):
        self.plan = None
        super().accept()

    def accept(self):
        try:
            self.plan = AnalysisPlan(
                self.design.currentText(),
                _checked(self.conditions),
                _checked(self.phases),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Check analysis scope", str(exc))
            return
        super().accept()


class AnalysisSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    changed = Signal(object)


class AnalysisWorker(QRunnable):
    def __init__(
        self,
        plan: AnalysisPlan,
        results: dict[Path, ImportResult],
        paths: set[Path],
        annotations: dict[Path, AnalysisMetadata],
    ):
        super().__init__()
        self.args = (plan, dict(results), tuple(paths), dict(annotations))
        self.signals = AnalysisSignals()

    @Slot()
    def run(self):
        try:
            tables = build_analysis(*self.args)
        except Exception as exc:
            if isinstance(exc, SourcesChangedError):
                self.signals.changed.emit(exc.checks)
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(tables)


METRIC_TITLES = {**SESSION_LABELS, **PHASE_LABELS}
METRIC_TITLES["prl.proportion_correct"] = "Session proportion correct"
METRIC_TITLES["prl.phase.proportion_correct"] = "Phase proportion correct"


class AnalysisModel(QAbstractTableModel):
    def __init__(self, frame: pd.DataFrame, parent=None):
        super().__init__(parent)
        self.frame = frame

    def rowCount(self, parent=None):
        return 0 if parent and parent.isValid() else len(self.frame)

    def columnCount(self, parent=None):
        return 0 if parent and parent.isValid() else len(self.frame.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            value = self.frame.iat[index.row(), index.column()]
            if role == Qt.ItemDataRole.ToolTipRole:
                return "" if value is None else str(value)
            if self.frame.columns[index.column()] == "metric":
                return METRIC_TITLES.get(value, value)
            if isinstance(value, float):
                return f"{value:.6g}"
            return "" if value is None else str(value)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return (
                self.frame.columns[section].replace("_", " ")
                if not self.frame.columns[section].startswith("[")
                else self.frame.columns[section]
            )
        return super().headerData(section, orientation, role)


class AnalysisReview(QDialog):
    def __init__(self, plan, tables, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Animal analysis results")
        self.resize(1150, 620)
        layout = QVBoxLayout(self)
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setText(" · ".join((plan.design, ", ".join(plan.conditions), ", ".join(plan.phases))))
        layout.addWidget(label)
        tabs = QTabWidget()
        for filename in (
            "pooled_metrics.csv",
            "condition_comparison.csv",
            "animal_metrics.csv",
            "analysis_audit.csv",
        ):
            view = QTableView()
            frame = tables[filename]
            if filename == "pooled_metrics.csv":
                front = [
                    "condition",
                    "phase",
                    "metric",
                    "pooled_value",
                    "valid_animal_n",
                    "sum_numerator",
                    "sum_denominator",
                    "unit",
                ]
                frame = frame[front + [col for col in frame if col not in front]]
            view.setModel(AnalysisModel(frame, view))
            view.setAlternatingRowColors(True)
            view.horizontalHeader().setDefaultSectionSize(132)
            if "metric" in frame:
                view.setColumnWidth(frame.columns.get_loc("metric"), 230)
            tabs.addTab(view, SHEETS[filename])
        layout.addWidget(tabs)
        done = QPushButton("Close")
        done.clicked.connect(self.accept)
        layout.addWidget(done)
