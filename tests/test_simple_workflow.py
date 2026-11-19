"""Exercise the compact data view and exports through the embedded interface."""

import csv
import json
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QFileDialog
from qt_helpers import javascript, wait_until

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.compact_results import DATA_COLUMNS, data_values
from trial_cruncher.gui.web_shell import WebShell

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="Requires the embedded Chromium runtime",
)


def test_data_view_and_compact_exports(app, phase_input, tmp_path, monkeypatch):
    good = phase_input((1, 1, 1, 7), name="good.txt")
    zero = phase_input((7, 7), name="zero.txt")
    zero.write_text(zero.read_text().replace("Subject: 0007", "Subject: 0008"))
    bad = phase_input((1, 7), name="invalid.txt")
    bad.write_text(bad.read_text().replace("  0: 1 1 2", "  0: 1 1 12"))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    shell = WebShell()
    shell.show()
    ctrl = shell.controller

    def js(script):
        return javascript(app, shell.page, script)

    def click(selector):
        query = f"document.querySelector('{selector}')"
        wait_until(app, lambda: js(f"!!{query} && !{query}.disabled"), timeout=15)
        js(f"{query}.click()")

    try:
        wait_until(app, lambda: js("Boolean(window.trialReady)"), timeout=20)
        ctrl.add_paths([str(good), str(zero), str(bad)])
        wait_until(app, lambda: not ctrl._is_working())
        ctrl.phase_assignments = dict.fromkeys([good, zero, bad], "Reversal")
        ctrl.metadata_assignments = dict.fromkeys(
            [good, zero, bad], AnalysisMetadata("Vehicle", "Cohort", included=True)
        )
        click("[data-action=import]")
        wait_until(
            app, lambda: len(ctrl.import_results) == 3 and not ctrl._is_working(), timeout=15
        )
        wait_until(app, lambda: js("document.querySelectorAll('#batch-table tbody tr').length===3"))
        headers = js(
            "JSON.stringify(Array.from(document.querySelectorAll('#batch-table th'), "
            "x => x.childNodes[0].textContent.trim()))"
        )
        assert json.loads(headers) == list(DATA_COLUMNS)
        rendered = json.loads(
            js(
                "JSON.stringify(Array.from(document.querySelectorAll('#batch-table tbody tr'), "
                "tr => ({path: tr.dataset.path, cells: Array.from(tr.cells, c => c.textContent)})))"
            )
        )
        rows_by_path = {row["path"]: row["cells"] for row in rendered}
        assert float(rows_by_path[str(good)][3]) == 0.75
        assert float(rows_by_path[str(zero)][3]) == 0
        assert rows_by_path[str(bad)][3] == "Withheld"
        js(
            f"Array.from(document.querySelectorAll('#batch-table tbody tr')).find("
            f"r => r.dataset.path === {json.dumps(str(good))}).click()"
        )
        wait_until(app, lambda: ctrl.overview.current_path() == good)
        rendered = json.loads(
            js(
                "JSON.stringify(Object.fromEntries(Array.from(document.querySelectorAll("
                "'#batch-table tbody tr'), tr => [tr.dataset.path, "
                "Array.from(tr.cells, td => td.firstChild.textContent)])))"
            )
        )
        for path, result in ctrl.import_results.items():
            for i, (cell, value) in enumerate(
                zip(rendered[str(path)], data_values(result), strict=True)
            ):
                if value is None:
                    assert cell in {"Withheld", "Unavailable"}
                elif i >= 3:
                    assert float(cell) == pytest.approx(value, abs=0.00005)
                else:
                    assert cell == value
        assert data_values(ctrl.import_results[zero])[3] == 0
        assert data_values(ctrl.import_results[bad])[3] is None
        click("[data-workflow=export]")
        click("[data-action=export-csv]")
        wait_until(
            app,
            lambda: bool(list(tmp_path.glob("*/data.csv"))) and not ctrl._is_working(),
            timeout=20,
        )
        csv_path = next(tmp_path.glob("*/data.csv"))
        with csv_path.open(newline="", encoding="utf-8") as f:
            csv_rows = list(csv.DictReader(f))
        assert list(csv_rows[0]) == list(DATA_COLUMNS)
        assert len(csv_rows) == 3
        assert any(
            float(row["Proportion correct"]) == 0.75
            for row in csv_rows
            if row["Proportion correct"]
        )
        assert any(
            row["Proportion correct"] and float(row["Proportion correct"]) == 0 for row in csv_rows
        )
        assert any(row["Proportion correct"] == "" for row in csv_rows)
        click("[data-action=export-excel]")
        wait_until(
            app,
            lambda: bool(list(tmp_path.glob("*/results.xlsx"))) and not ctrl._is_working(),
            timeout=20,
        )
        book = load_workbook(next(tmp_path.glob("*/results.xlsx")), read_only=True, data_only=True)
        assert tuple(next(book["Data"].values)) == DATA_COLUMNS
        assert book["Data"].max_row == 4
        metadata = book["Metadata"].values
        names = next(metadata)
        data_rows = list(book["Data"].values)
        for row in list(metadata)[:3]:
            linked = dict(zip(names, row, strict=True))
            number = linked["Data row"]
            session_row = data_rows[number - 1]
            csv_row = csv_rows[number - 2]
            for name, excel_value, expected in zip(
                DATA_COLUMNS,
                session_row,
                data_values(ctrl.import_results[Path(linked["Source file"])]),
                strict=True,
            ):
                if isinstance(expected, (int, float)):
                    assert excel_value == pytest.approx(expected)
                    assert float(csv_row[name]) == expected
                else:
                    assert excel_value == expected
                    assert csv_row[name] == (expected or "")
        book.close()
    finally:
        shell.close()
        app.processEvents()
