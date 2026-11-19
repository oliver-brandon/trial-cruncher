"""Synthetic project restoration and cross-view animal-analysis regression."""

import csv
import json
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QFileDialog
from qt_helpers import javascript, wait_until

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.analysis_plan import AnalysisPlan
from trial_cruncher.gui.web_shell import WebShell
from trial_cruncher.projects import save_project

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="Requires the embedded Chromium runtime",
)


def test_saved_project_review_and_analysis_parity(app, phase_input, tmp_path, monkeypatch):
    a = phase_input((1, 1, 1, 7), name="animal7-control.txt")
    b = phase_input((1, 7, 7, 7), name="animal7-drug.txt")
    duplicate1 = phase_input((1, 7), name="animal8-first.txt")
    duplicate2 = phase_input((1, 1, 7), name="animal8-repeat.txt")
    for path in (duplicate1, duplicate2):
        path.write_text(path.read_text().replace("Subject: 0007", "Subject: 0008"))
    paths = [a, b, duplicate1, duplicate2]
    metadata = {
        a: AnalysisMetadata("Control", "Cohort", included=True),
        b: AnalysisMetadata("Drug", "Cohort", included=True),
        duplicate1: AnalysisMetadata("Control", "Cohort", included=True),
        duplicate2: AnalysisMetadata("Control", "Cohort", included=True),
    }
    plan = AnalysisPlan("Cohort", "within-subjects", ("Control", "Drug"), ("Reversal",))
    project = tmp_path / "saved.tcproj.json"
    save_project(
        project,
        paths,
        dict.fromkeys(paths, "Reversal"),
        {},
        extensions=[".txt"],
        recursive=False,
        analysis_metadata=metadata,
        analysis_plan=plan,
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(project), ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    shell = WebShell()
    shell.show()

    def click(selector):
        wait_until(
            app,
            lambda: javascript(
                app,
                shell.page,
                f"Boolean(document.querySelector('{selector}')) && "
                f"!document.querySelector('{selector}').disabled",
            ),
            timeout=20,
        )
        javascript(app, shell.page, f"document.querySelector('{selector}').click()")

    try:
        wait_until(
            app, lambda: javascript(app, shell.page, "Boolean(window.trialReady)"), timeout=20
        )
        click("[data-workflow=project]")
        click("[data-action=open-project]")
        wait_until(app, lambda: shell.controller.selected_files == set(paths), timeout=20)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=20)
        assert shell.controller.metadata_assignments == metadata
        assert shell.controller.analysis_plan == plan
        click("[data-action=import]")
        wait_until(app, lambda: len(shell.controller.import_results) == 4, timeout=20)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=20)

        for path, expected in ((a, ("Control", "0.7500")), (b, ("Drug", "0.2500"))):
            row = shell.controller.overview.model.row(
                shell.controller.overview.model.index_for_path(path).row()
            )
            assert (row.text(14), row.text(11)) == expected

        click("[data-workflow=review]")
        click("[data-action=animal-analysis]")
        wait_until(
            app, lambda: javascript(app, shell.page, "!!document.querySelector('#animal-dialog')")
        )
        javascript(app, shell.page, "document.querySelector('#animal-dialog .primary').click()")
        wait_until(app, lambda: shell.controller._web_analysis_tables is not None, timeout=20)

        def shown_table(tab, first_header, required_header):
            def js(script):
                return javascript(app, shell.page, script)

            wait_until(app, lambda: js("!document.querySelector('.animal-preview').hidden"))
            js(
                "Array.from(document.querySelectorAll('.animal-preview nav button'))"
                f".find(b => b.textContent === {json.dumps(tab)}).click()"
            )
            # Read the actual rendered cell label, excluding collapsed evidence paths.
            script = """(() => {
                const table = document.querySelector('.animal-preview table');
                const headers = Array.from(table.querySelectorAll('th'), c => c.textContent);
                const rows = Array.from(table.querySelectorAll('tbody tr'), tr =>
                    Object.fromEntries(Array.from(tr.cells, (cell, i) => [
                        headers[i], (cell.querySelector('summary') || cell).textContent
                    ]))
                );
                return JSON.stringify({headers, rows});
            })()"""

            def ready():
                headings = json.loads(js(script))["headers"]
                return headings[:1] == [first_header] and required_header in headings

            wait_until(app, ready)
            return json.loads(js(script))["rows"]

        audit = shown_table("Analysis audit", "subject id", "Recording proportion correct")
        assert {Path(row["source file"]): row["condition"] for row in audit} == {
            path: value.condition for path, value in metadata.items()
        }
        repeats = {Path(r["source file"]): r for r in audit if r["subject id"] == "0008"}
        assert {r["disposition"] for r in repeats.values()} == {
            "Multiple Included recordings for this cell"
        }
        assert float(repeats[duplicate1]["Recording proportion correct"]) == 0.5
        assert float(repeats[duplicate2]["Recording proportion correct"]) == pytest.approx(2 / 3)

        compared = shown_table("Condition comparison", "subject id", "Assigned conditions")
        acc = {r["subject id"]: r for r in compared if r["metric"] == "Session proportion correct"}
        assert acc["0007"]["Assigned conditions"] == "Control, Drug"
        assert float(acc["0007"]['["Control", "Reversal"]']) == 0.75
        assert float(acc["0007"]['["Drug", "Reversal"]']) == 0.25
        assert "Multiple Included" in acc["0008"]['["Control", "Reversal"]']
        assert acc["0008"]['["Drug", "Reversal"]'] == "Missing selected recording"

        javascript(app, shell.page, "document.querySelector('#animal-dialog').close()")
        click("[data-workflow=export]")
        javascript(app, shell.page, "document.querySelector('#advanced-export').open=true")
        click("[data-action=detailed-csv]")
        wait_until(app, lambda: bool(list(tmp_path.glob("*/manifest.json"))), timeout=20)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=20)
        folder = next(tmp_path.glob("*/manifest.json")).parent
        with (folder / "sessions.csv").open(newline="", encoding="utf-8") as stream:
            sessions = {Path(row["source_file"]): row for row in csv.DictReader(stream)}
        for path, condition, value in ((a, "Control", 0.75), (b, "Drug", 0.25)):
            assert sessions[path]["analysis_condition"] == condition
            assert float(sessions[path]["prl.proportion_correct"]) == pytest.approx(value)
        with (folder / "animal_metrics.csv").open(newline="", encoding="utf-8") as stream:
            animal_values = {
                row["condition"]: float(row["value"])
                for row in csv.DictReader(stream)
                if row["metric"] == "prl.proportion_correct"
            }
        assert animal_values == {"Control": 0.75, "Drug": 0.25}
    finally:
        shell.close()
        app.processEvents()
