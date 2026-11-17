"""Exercise the selection gestures in both assignment dialogs on synthetic paths."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.gui.metadata import MetadataDialog
from trial_cruncher.gui.phases import PhaseDialog


@pytest.mark.parametrize("field", ["Phase", "Cohort", "Condition / treatment"])
def test_apply_to_selected_files(tmp_path, field):
    app = QApplication.instance() or QApplication([])
    paths = [tmp_path / str(i) / "same.txt" for i in range(5)]
    original = AnalysisMetadata(condition="Vehicle", cohort="First", session_order=3)
    if field == "Phase":
        dialog = PhaseDialog(paths, dict.fromkeys(paths, "Acquisition"))
        dialog.bulk_phase.setCurrentText("Reversal 2")
    else:
        dialog = MetadataDialog(paths, dict.fromkeys(paths, original))
        dialog.bulk_field.setCurrentText(field)
        dialog.bulk_text.setText("Second")
    dialog.show()
    app.processEvents()
    table = dialog.table

    def click_file(row, modifier=Qt.KeyboardModifier.NoModifier):
        position = table.visualItemRect(table.item(row, 0)).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, modifier, position)

    try:
        assert not table.apply_selected.isEnabled()
        click_file(0)
        click_file(2, Qt.KeyboardModifier.ShiftModifier)
        assert set(table.selected_rows()) == {0, 1, 2}
        click_file(1, Qt.KeyboardModifier.ControlModifier)
        click_file(4, Qt.KeyboardModifier.ControlModifier)
        assert table.apply_selected.text().endswith("(3)")
        QTest.mouseClick(table.apply_selected, Qt.MouseButton.LeftButton)
        for i, path in enumerate(paths):
            selected = i in (0, 2, 4)
            value = dialog.assignments()[path]
            if field == "Phase":
                assert value == ("Reversal 2" if selected else "Acquisition")
            else:
                assert value.condition == (
                    "Second" if selected and field != "Cohort" else "Vehicle"
                )
                assert value.cohort == ("Second" if selected and field == "Cohort" else "First")
                assert value.session_order == 3
        table.clearSelection()
        assert not table.apply_selected.isEnabled()
    finally:
        dialog.reject()
