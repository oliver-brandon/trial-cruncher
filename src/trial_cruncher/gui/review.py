"""Read-only session review. All widget/model updates happen on the GUI thread."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.models import Event
from trial_cruncher.prl_metrics import METRIC_LABELS, PRLSessionSummary
from trial_cruncher.processing import ImportResult


def display(value: object) -> str:
    if value is None:
        return "Unavailable"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


class ChoiceTableModel(QAbstractTableModel):
    HEADERS = ("C index", "Time (s)", "Correct", "Rewarded", "Code", "Raw C value", "Source line")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.events: tuple[Event, ...] = ()

    def set_events(self, events: tuple[Event, ...]) -> None:
        self.beginResetModel()
        self.events = events
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.events)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        event = self.events[index.row()]
        values = (
            event.raw_values.get("index"),
            event.timestamp_s,
            event.attributes.get("correct"),
            event.attributes.get("rewarded"),
            event.attributes.get("outcome_code"),
            event.raw_values.get("value"),
            event.raw_values.get("line_number"),
        )
        return display(values[index.column()])

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return super().headerData(section, orientation, role)


class ReviewPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.details = self._text_tab("Session details")
        self.metric_page = QWidget()
        metric_layout = QVBoxLayout(self.metric_page)
        metric_note = QLabel(
            "Recorded-choice summaries · definition 1 · strict withholding.\n"
            "Percent correct uses recorded choices, not the saved A[5] fraction."
        )
        metric_note.setWordWrap(True)
        metric_layout.addWidget(metric_note)
        self.metric_table = QTableWidget(0, 5)
        self.metric_table.setAccessibleName("Session metrics")
        self.metric_table.setHorizontalHeaderLabels(("Metric", "Value", "Unit", "Status", "Reason"))
        self.metric_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.metric_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.metric_table.verticalHeader().hide()
        self.metric_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.metric_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        metric_layout.addWidget(self.metric_table, 2)
        self.metric_diagnostics = QPlainTextEdit()
        self.metric_diagnostics.setAccessibleName("Metric diagnostics and warnings")
        self.metric_diagnostics.setReadOnly(True)
        metric_layout.addWidget(self.metric_diagnostics, 1)
        self.tabs.addTab(self.metric_page, "Session metrics")
        self.choice_model = ChoiceTableModel(self)
        self.choices = QTableView()
        self.choices.setAccessibleName("Decoded choices")
        self.choices.setModel(self.choice_model)
        self.choices.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.choices.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.choices.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.choices, "Decoded choices")
        self.warnings = self._text_tab("Warnings and checks")
        self.source = self._text_tab("Source text")
        self.clear()

    def _text_tab(self, name: str) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setReadOnly(True)
        widget.setAccessibleName(name)
        self.tabs.addTab(widget, name)
        return widget

    def clear(self, message: str = "Add files, then choose Import Med-PC to review them.") -> None:
        self.summary.setText(message)
        self.details.clear()
        self.warnings.clear()
        self.source.clear()
        self.choice_model.set_events(())
        self.metric_table.setRowCount(0)
        self.metric_diagnostics.setPlainText("No calculated metrics available.")
        self.tabs.setTabText(self.tabs.indexOf(self.choices), "Decoded choices")

    def show_metrics(self, summary: PRLSessionSummary) -> None:
        states = {
            "available": "Available",
            "available_with_warnings": "Available with warnings",
            "unavailable": "Unavailable",
        }
        self.metric_table.setRowCount(len(summary.metrics))
        for row, metric in enumerate(summary.metrics):
            value = display(metric.value)
            if metric.value is not None and metric.unit == "%":
                value = f"{metric.value:.2f}"
            fields = (
                METRIC_LABELS[metric.name],
                value,
                metric.unit,
                states[metric.status],
                "\n".join(metric.reasons),
            )
            for column, text in enumerate(fields):
                item = QTableWidgetItem(text)
                item.setToolTip("\n".join((metric.name, *metric.reasons, *metric.warnings)))
                self.metric_table.setItem(row, column, item)
        self.metric_table.resizeRowsToContents()
        quality = summary.diagnostics
        lines = [
            "Recorded-data diagnostics (not substitutes for withheld totals):",
            f"C present: {display(quality.c_present)}",
            f"Terminator observed: {display(quality.terminator_seen)}",
            f"Observed records before terminator: {display(quality.observed_record_count)}",
            f"Valid decoded records: {display(quality.decoded_choice_count)}",
            f"Invalid records: {display(quality.invalid_record_count)}",
            f"Values after terminator: {display(quality.post_terminator_count)}",
            f"C index gaps: {display(quality.c_indices_have_gaps)}",
            "",
            "Warnings:",
            *(summary.metrics[0].warnings or ("None.",)),
            "",
            "Saved-count comparisons are in Warnings and checks.",
        ]
        self.metric_diagnostics.setPlainText("\n".join(lines))

    def show_result(self, result: ImportResult) -> None:
        self.clear()
        raw, session = result.raw, result.session
        lines = [f"Source file: {result.source_file}"]
        messages = []
        if raw is not None:
            self.source.setPlainText(raw["source_text"])
        if session is not None:
            state = (
                f"Imported with {len(session.warnings)} warning(s)"
                if session.warnings
                else "Imported"
            )
            self.summary.setText(f"{result.source_file.name} — {state}")
            lines += [
                "",
                f"Program: {session.metadata['program']}",
                f"Subject: {display(session.subject_id)}",
                f"Experiment: {display(raw['headers'].get('Experiment'))}",
                f"Group: {display(raw['headers'].get('Group'))}",
                f"Box: {display(raw['headers'].get('Box'))}",
                f"Session ID: {display(session.session_id)}",
                f"Task duration (S, seconds): {display(session.duration_s)}",
                f"Choice records displayed: {len(session.events)}",
                "Choice timestamps: seconds from task start",
                "Head entries: not recorded",
                "Latency: unavailable",
                "Header times include program loading and are not task duration.",
            ]
            self.choice_model.set_events(session.events)
            self.tabs.setTabText(
                self.tabs.indexOf(self.choices), f"Decoded choices ({len(session.events)})"
            )
            if result.summary is not None:
                self.show_metrics(result.summary)
            messages += list(session.warnings) or ["No import warnings."]
            messages += ["", "Saved-count consistency checks (not scientific validation):"]
            states = {True: "Match", False: "Mismatch", None: "Unavailable"}
            messages += [
                f"{key}: {states[value]}"
                for key, value in session.metadata["summary_checks"].items()
            ]
        else:
            self.summary.setText(f"{result.source_file.name} — Import failed")
            messages += [result.error or "No session was returned."]
            if raw is not None:
                messages += list(raw["warnings"])
            lines += ["", "No decoded session is available. See Warnings and checks."]
        if raw is not None:
            lines += ["", "Original headers:"]
            lines += [f"{key}: {value}" for key, value in raw["headers"].items()]
            lines += ["", "Raw scalar variables (unchanged):"]
            lines += [f"{key}: {value}" for key, value in raw["scalars"].items()]
            lines += ["", "F, J, and A[4] are raw-only; see Source text."]
            lines += [
                "",
                "Provenance:",
                f"SHA-256: {raw['source_sha256']}",
                f"Reader version: {raw['reader_version']}",
            ]
            if session is not None:
                lines += [f"Normalizer version: {session.metadata['normalizer_version']}"]
        self.details.setPlainText("\n".join(lines))
        self.warnings.setPlainText("\n".join(messages))
        if session is None:
            self.tabs.setCurrentWidget(self.warnings)
