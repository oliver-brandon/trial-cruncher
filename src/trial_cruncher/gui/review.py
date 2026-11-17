"""Read-only session review. All widget/model updates happen on the GUI thread."""

from pathlib import Path

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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.models import Event
from trial_cruncher.phase_metrics import METRIC_LABELS as PHASE_LABELS
from trial_cruncher.phase_metrics import PhaseSummary
from trial_cruncher.prl_metrics import DEFINITION_VERSION, METRIC_LABELS, PRLSessionSummary
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
        layout.setContentsMargins(0, 0, 0, 0)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.details = self._text_tab("Session details")
        self.metric_page = QWidget()
        metric_layout = QVBoxLayout(self.metric_page)
        self.metric_note = QLabel(
            f"Recorded-choice summaries · definition {DEFINITION_VERSION} · strict withholding.\n"
            "Proportion correct uses recorded choices, not the saved A[5] fraction."
        )
        self.metric_note.setWordWrap(True)
        metric_layout.addWidget(self.metric_note)
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
        self.metric_diagnostics_toggle = self._add_diagnostics(
            metric_layout, self.metric_diagnostics
        )
        self.tabs.addTab(self.metric_page, "Session metrics")
        self.phase_page = QWidget()
        phase_layout = QVBoxLayout(self.phase_page)
        self.phase_label = QLabel()
        self.phase_label.setTextFormat(Qt.TextFormat.PlainText)
        self.phase_label.setWordWrap(True)
        phase_layout.addWidget(self.phase_label)
        self.phase_table = QTableWidget(0, 7)
        self.phase_table.setWordWrap(False)
        self.phase_table.verticalHeader().hide()
        self.phase_table.setHorizontalHeaderLabels(
            ["Metric", "Value", "Unit", "Numerator", "Denominator", "Status", "Reason"]
        )
        self.phase_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.phase_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.phase_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        phase_layout.addWidget(self.phase_table, 2)
        self.phase_diagnostics = QPlainTextEdit()
        self.phase_diagnostics.setReadOnly(True)
        self.phase_diagnostics_toggle = self._add_diagnostics(phase_layout, self.phase_diagnostics)
        self.tabs.addTab(self.phase_page, "Phase metrics")
        self.analysis_details = self._text_tab("Analysis metadata")
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

    @staticmethod
    def _add_diagnostics(layout: QVBoxLayout, details: QPlainTextEdit) -> QToolButton:
        toggle = QToolButton()
        toggle.setText("Diagnostics")
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setArrowType(Qt.ArrowType.RightArrow)
        toggle.setCheckable(True)
        toggle.toggled.connect(details.setVisible)
        toggle.toggled.connect(
            lambda open_: toggle.setArrowType(
                Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
            )
        )
        layout.addWidget(toggle)
        details.hide()
        layout.addWidget(details, 1)
        return toggle

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
        self.phase_table.setRowCount(0)
        self.phase_label.setText("No imported phase results.")
        self.phase_diagnostics.clear()
        self.analysis_details.clear()
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
            if metric.value is not None and metric.unit in ("proportion", "choices/min"):
                value = f"{metric.value:.4f}"
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
            f"Raw C entries: {display(quality.raw_c_entry_count)}",
            f"Unused array slots (retained raw): {display(quality.unused_slot_count)}",
            f"Choice records before terminator: {display(quality.observed_record_count)}",
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

    def show_phase_metrics(self, phase: PhaseSummary) -> None:
        self.phase_label.setText(
            f"Imported phase: {phase.config.phase or 'Unassigned'} · "
            f"definition {phase.definition_version}\n"
            "One fixed contingency per file; no omissions (owner-confirmed protocol)."
        )
        self.phase_table.setRowCount(len(phase.metrics))
        for row, metric in enumerate(phase.metrics):
            evidence = (
                phase.strategies[row - 4]
                if row >= 4
                else phase.diagnostics.adjusted_regressive
                if row == 3
                else None
            )
            value = display(metric.value)
            if isinstance(metric.value, float):
                value = (
                    f"{metric.value:.4f}"
                    if metric.name.endswith("proportion_correct")
                    else f"{metric.value:.4g}"
                )
            fields = (
                PHASE_LABELS[metric.name],
                value,
                metric.unit,
                display(evidence.numerator) if evidence else "—",
                display(evidence.denominator) if evidence else "—",
                "Withheld"
                if "source_integrity" in phase.reason_codes[row]
                else metric.status.replace("_", " ").capitalize(),
                "\n".join(metric.reasons),
            )
            for column, text in enumerate(fields):
                item = QTableWidgetItem(text)
                item.setToolTip("\n".join((metric.name, *metric.reasons, *metric.warnings)))
                self.phase_table.setItem(row, column, item)
        self.phase_table.resizeRowsToContents()
        d = phase.diagnostics
        status = {
            "available": "Available",
            "partially_available": "Some metrics unavailable",
            "unavailable": "Unavailable",
            "withheld": "Withheld",
            "phase_unassigned": "Phase not assigned",
        }[phase.status]
        self.phase_diagnostics.setPlainText(
            "\n".join(
                (
                    f"Phase result: {status}",
                    f"Recorded choices: {display(d.valid_choice_count)}",
                    f"Criterion reached: {display(d.criterion_reached)}",
                    f"Criterion choice (one-based): {display(d.criterion_choice_ordinal)}",
                    f"Criterion C index (zero-based): {display(d.criterion_source_index)}",
                    f"Postcriterion choices: {display(d.postcriterion_choice_count)}",
                    f"Eligible pairs: {display(d.eligible_pair_count)}",
                    "Omissions: 0 — protocol assertion, not measured from cues.",
                    f"Configuration SHA-256: {phase.config.sha256}",
                )
            )
        )

    def show_analysis_metadata(self, path: Path, a: AnalysisMetadata) -> None:
        order = a.session_order if a.session_order is not None else "Unassigned"
        self.analysis_details.setPlainText(
            "\n".join(
                (
                    f"Source file: {path}",
                    "Manual study annotations — independent of metric validity.",
                    "Included, Excluded, and Not reviewed records all remain in exports.",
                    "",
                    f"Condition / treatment: {a.condition or 'Unassigned'}",
                    f"Cohort: {a.cohort or 'Unassigned'}",
                    f"Session order: {order}",
                    f"Analysis inclusion: {a.inclusion_status}",
                    f"Reason: {a.inclusion_reason or 'Not assigned'}",
                    "",
                    f"Metadata version: {a.version}",
                    f"Metadata SHA-256: {a.sha256}",
                )
            )
        )

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
            if result.phase_summary is not None:
                self.show_phase_metrics(result.phase_summary)
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
        a = result.analysis_metadata
        self.show_analysis_metadata(result.source_file, a)
        self.summary.setText(self.summary.text() + f" · Analysis: {a.inclusion_status}")
        lines += [
            "",
            "Manual analysis metadata (separate from original headers):",
            f"Condition / treatment: {a.condition or 'Unassigned'}",
            f"Cohort: {a.cohort or 'Unassigned'}",
            f"Session order: {a.session_order if a.session_order is not None else 'Unassigned'}",
            f"Analysis inclusion: {a.inclusion_status}",
            f"Reason: {a.inclusion_reason or 'Not assigned'}",
            f"Analysis metadata version: {a.version}",
            f"Analysis metadata SHA-256: {a.sha256}",
        ]
        self.details.setPlainText("\n".join(lines))
        self.warnings.setPlainText("\n".join(messages))
        if session is None:
            self.tabs.setCurrentWidget(self.warnings)
