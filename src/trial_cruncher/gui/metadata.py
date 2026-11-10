"""Manual per-file annotations; never infer treatment or study inclusion."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.analysis_metadata import AnalysisMetadata


def inclusion_picker(included: bool | None = None) -> QComboBox:
    picker = QComboBox()
    for text, value in (("Not reviewed", None), ("Include", True), ("Exclude", False)):
        picker.addItem(text, value)
    picker.setCurrentIndex(1 if included is True else 2 if included is False else 0)
    return picker


@dataclass
class MetadataEditors:
    condition: QLineEdit
    cohort: QLineEdit
    order: QSpinBox
    inclusion: QComboBox
    reason: QPlainTextEdit

    def value(self) -> AnalysisMetadata:
        return AnalysisMetadata(
            self.condition.text().strip() or None,
            self.cohort.text().strip() or None,
            self.order.value() or None,
            self.inclusion.currentData(),
            self.reason.toPlainText().strip() or None,
        )


class MetadataDialog(QDialog):
    def __init__(
        self,
        paths: Sequence[Path],
        assignments: Mapping[Path, AnalysisMetadata],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Session metadata and study inclusion")
        self.resize(1280, 620)
        self.paths = tuple(paths)
        self._saved: dict[Path, AnalysisMetadata] | None = None
        layout = QVBoxLayout(self)
        note = QLabel(
            "Manual assignments for every selected file, including hidden rows. Save applies them "
            "immediately without recalculating metrics. Exclusions require a reason. "
            "Excluded and Not reviewed recordings remain in exports with their flags. "
            "Nothing is inferred from Med-PC Group or other headers."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        bulk = QHBoxLayout()
        self.bulk_field = QComboBox()
        self.bulk_field.addItems(["Condition / treatment", "Cohort", "Inclusion and reason"])
        self.bulk_text = QLineEdit()
        self.bulk_text.setPlaceholderText("Value (blank clears this field)")
        self.bulk_inclusion = inclusion_picker()
        self.bulk_reason = QLineEdit()
        self.bulk_reason.setPlaceholderText("Reason (required for exclusion)")
        self.apply_all = QPushButton("Apply field to all files")
        for widget in (
            self.bulk_field,
            self.bulk_text,
            self.bulk_inclusion,
            self.bulk_reason,
            self.apply_all,
        ):
            bulk.addWidget(widget)
        layout.addLayout(bulk)
        self.table = QTableWidget(len(paths), 6)
        self.table.setHorizontalHeaderLabels(
            [
                "Source file (full path)",
                "Condition / treatment",
                "Cohort",
                "Session order",
                "Analysis inclusion",
                "Reason",
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        for col, width in enumerate((400, 170, 135, 105, 135, 250)):
            self.table.setColumnWidth(col, width)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.editors: list[MetadataEditors] = []
        for row, path in enumerate(paths):
            value = assignments.get(path, AnalysisMetadata())
            item = QTableWidgetItem(str(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip("<qt>" + escape(str(path)) + "</qt>")
            self.table.setItem(row, 0, item)
            condition, cohort = QLineEdit(value.condition or ""), QLineEdit(value.cohort or "")
            condition.setPlaceholderText("Unassigned")
            cohort.setPlaceholderText("Unassigned")
            order = QSpinBox()
            order.setRange(0, 2_147_483_647)
            order.setSpecialValueText("Unassigned")
            order.setValue(value.session_order or 0)
            inclusion = inclusion_picker(value.included)
            reason = QPlainTextEdit(value.inclusion_reason or "")
            reason.setPlaceholderText("Required when excluded")
            self.editors.append(MetadataEditors(condition, cohort, order, inclusion, reason))
            for col, widget in enumerate((condition, cohort, order, inclusion, reason), 1):
                self.table.setCellWidget(row, col, widget)
            self.table.setRowHeight(row, 54)
        layout.addWidget(self.table)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.bulk_field.currentIndexChanged.connect(self._bulk_mode)
        self.apply_all.clicked.connect(self._apply_all)
        self._bulk_mode()

    def _bulk_mode(self, *args) -> None:
        inclusion = self.bulk_field.currentIndex() == 2
        self.bulk_text.setVisible(not inclusion)
        self.bulk_inclusion.setVisible(inclusion)
        self.bulk_reason.setVisible(inclusion)

    def _apply_all(self) -> None:
        for editors in self.editors:
            if self.bulk_field.currentIndex() == 0:
                editors.condition.setText(self.bulk_text.text())
            elif self.bulk_field.currentIndex() == 1:
                editors.cohort.setText(self.bulk_text.text())
            else:
                editors.inclusion.setCurrentIndex(self.bulk_inclusion.currentIndex())
                editors.reason.setPlainText(self.bulk_reason.text())

    def assignments(self) -> dict[Path, AnalysisMetadata]:
        if self._saved is not None:
            return dict(self._saved)
        return {
            path: value
            for path, editor in zip(self.paths, self.editors, strict=True)
            if (value := editor.value()).is_assigned
        }

    def accept(self) -> None:
        values = {}
        for row, (path, editor) in enumerate(zip(self.paths, self.editors, strict=True)):
            try:
                value = editor.value()
            except ValueError as exc:
                self.table.scrollToItem(self.table.item(row, 0))
                editor.reason.setFocus()
                QMessageBox.warning(self, "Check session metadata", f"{path}: {exc}")
                return
            if value.is_assigned:
                values[path] = value
        self._saved = values
        super().accept()
