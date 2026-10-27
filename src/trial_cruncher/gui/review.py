"""Read-only session review. All widget/model updates happen on the GUI thread."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.models import Event
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
        self.tabs.setTabText(1, "Decoded choices")

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
            self.tabs.setTabText(1, f"Decoded choices ({len(session.events)})")
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
            self.tabs.setCurrentIndex(2)
