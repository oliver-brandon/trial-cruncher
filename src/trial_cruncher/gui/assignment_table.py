"""Row selection shared by the file assignment dialogs."""

import sys

from PySide6.QtWidgets import QAbstractItemView, QPushButton, QTableWidget

TOGGLE_KEY = "Command" if sys.platform == "darwin" else "Ctrl"
SELECTION_HINT = (
    f"Click file names to select rows. Shift-click a range or {TOGGLE_KEY}-click individual files."
)


class AssignmentTable(QTableWidget):
    def __init__(self, rows: int, columns: int) -> None:
        super().__init__(rows, columns)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.apply_selected = QPushButton()
        self.apply_selected.setAutoDefault(False)
        self.itemSelectionChanged.connect(self._update_button)
        self._update_button()

    def selected_rows(self) -> list[int]:
        return [index.row() for index in self.selectionModel().selectedRows(0)]

    def _update_button(self) -> None:
        count = len(self.selected_rows())
        self.apply_selected.setText(f"Apply to selected ({count})")
        self.apply_selected.setEnabled(count > 0)
