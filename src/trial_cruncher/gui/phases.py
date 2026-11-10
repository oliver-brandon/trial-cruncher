"""Explicit per-file phase assignment before an import snapshot is taken."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def phase_picker(value: str = "") -> QComboBox:
    picker = QComboBox()
    picker.setEditable(True)
    picker.addItems(["", "Acquisition", "Reversal"])
    picker.setCurrentText(value)
    picker.lineEdit().setPlaceholderText("Unassigned — or type a phase label")
    return picker


class PhaseDialog(QDialog):
    def __init__(
        self, paths: Sequence[Path], assignments: Mapping[Path, str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assign phases for import")
        self.resize(1000, 500)
        self.paths = tuple(paths)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Assign one phase per file. Type a custom label if needed. Blank phases leave "
            "phase metrics unavailable. Save, then Import Med-PC to apply these assignments."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        bulk = QHBoxLayout()
        self.bulk_phase = phase_picker()
        self.apply_all = QPushButton("Apply to all files")
        bulk.addWidget(self.bulk_phase)
        bulk.addWidget(self.apply_all)
        layout.addLayout(bulk)
        self.table = QTableWidget(len(paths), 2)
        self.table.setHorizontalHeaderLabels(["Source file (full path)", "Phase"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 650)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.pickers = []
        for row, path in enumerate(paths):
            item = QTableWidgetItem(str(path))
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.table.setItem(row, 0, item)
            picker = phase_picker(assignments.get(path, ""))
            self.pickers.append(picker)
            self.table.setCellWidget(row, 1, picker)
        layout.addWidget(self.table)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.apply_all.clicked.connect(self._apply_all)
        layout.addWidget(self.buttons)

    def _apply_all(self) -> None:
        for picker in self.pickers:
            picker.setCurrentText(self.bulk_phase.currentText())

    def assignments(self) -> dict[Path, str]:
        return {
            path: picker.currentText().strip()
            for path, picker in zip(self.paths, self.pickers, strict=True)
            if picker.currentText().strip()
        }
