"""Exercise the embedded frontend with synthetic files and the real background workers."""

import csv
import os

import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QFileDialog
from qt_helpers import javascript, wait_until

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.gui.web_shell import WebShell

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="WebEngine integration requires a working Chromium runtime",
)


def test_web_import_review_filter_and_export(app, phase_input, tmp_path, monkeypatch):
    first = phase_input(name="first.txt")
    second = phase_input(name="second.txt")
    second.write_text(second.read_text().replace("Subject: 0007", "Subject: 0008"))
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda *args: ([str(first), str(second)], "")
    )
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    project = tmp_path / "project.tcproj.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kw: (str(project), ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kw: (str(project), ""))
    shell = WebShell()
    shell.show()

    def click_action(name):
        selector = f"[data-action={name}]"
        wait_until(
            app,
            lambda: javascript(
                app,
                shell.page,
                f"Boolean(document.querySelector('{selector}')) && "
                f"!document.querySelector('{selector}').disabled",
            ),
            timeout=15,
        )
        javascript(app, shell.page, f"document.querySelector('{selector}').click()")

    try:
        wait_until(
            app, lambda: javascript(app, shell.page, "Boolean(window.trialReady)"), timeout=20
        )
        click_action("add-files")
        wait_until(app, lambda: len(shell.controller.selected_files) == 2)
        shell.controller.phase_assignments.update({first: "Acquisition", second: "Acquisition"})
        annotation = AnalysisMetadata(condition="Control", included=True)
        shell.controller.metadata_assignments.update({first: annotation, second: annotation})
        wait_until(
            app,
            lambda: javascript(
                app, shell.page, "!document.querySelector('[data-action=import]').disabled"
            ),
        )
        click_action("import")
        wait_until(app, lambda: len(shell.controller.import_results) == 2, timeout=15)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=15)
        wait_until(
            app,
            lambda: (
                javascript(
                    app, shell.page, "document.querySelectorAll('#batch-table tbody tr').length"
                )
                == 2
            ),
            timeout=15,
        )
        javascript(app, shell.page, "document.querySelector('[data-batch=sessions]').click()")
        wait_until(
            app,
            lambda: javascript(app, shell.page, "!!document.querySelector('#batch-quality')"),
        )

        javascript(
            app,
            shell.page,
            "document.querySelector('#batch-table thead th').dispatchEvent("
            "new KeyboardEvent('keydown', {key:'Enter', bubbles:true}))",
        )
        wait_until(
            app,
            lambda: javascript(
                app,
                shell.page,
                "document.querySelector('#batch-table thead th').getAttribute('aria-sort')"
                " !== 'none'",
            ),
        )
        next_path = javascript(
            app, shell.page, "document.querySelectorAll('#batch-table tbody tr')[1].dataset.path"
        )
        javascript(
            app,
            shell.page,
            "document.querySelector('#batch-table tbody tr').dispatchEvent("
            "new KeyboardEvent('keydown', {key:'ArrowDown', bubbles:true}))",
        )
        wait_until(app, lambda: str(shell.controller.overview.current_path()) == next_path)
        javascript(app, shell.page, "document.querySelector('[data-batch=phase]').click()")
        wait_until(app, lambda: shell.controller.batch_tabs.currentIndex() == 1)
        wait_until(
            app,
            lambda: javascript(app, shell.page, "Boolean(document.querySelector('#batch-layout'))"),
        )
        javascript(app, shell.page, "document.querySelector('[data-batch=sessions]').click()")
        wait_until(app, lambda: shell.controller.batch_tabs.currentIndex() == 0)
        wait_until(
            app,
            lambda: javascript(
                app,
                shell.page,
                "Boolean(document.querySelector('#batch-quality'))",
            ),
        )
        javascript(
            app,
            shell.page,
            "document.querySelector('#batch-search').value='first'; "
            "document.querySelector('#batch-search').dispatchEvent("
            "new Event('input', {bubbles:true}))",
        )
        wait_until(app, lambda: shell.controller.overview.proxy.rowCount() == 1)
        wait_until(
            app,
            lambda: (
                javascript(
                    app, shell.page, "document.querySelectorAll('#batch-table tbody tr').length"
                )
                == 1
            ),
        )
        javascript(app, shell.page, "document.querySelector('#batch-table tbody tr').click()")
        wait_until(app, lambda: shell.controller.overview.current_path() == first)
        click_action("animal-analysis")
        wait_until(
            app,
            lambda: javascript(
                app, shell.page, "Boolean(document.querySelector('#animal-dialog'))"
            ),
        )
        javascript(
            app,
            shell.page,
            "document.querySelectorAll('#animal-dialog select')[0].value='between-subjects';"
            "document.querySelectorAll('#animal-dialog input').forEach(x => x.checked=true);"
            "document.querySelector('#animal-dialog .primary').click()",
        )
        wait_until(app, lambda: shell.controller._web_analysis_tables is not None, timeout=15)
        wait_until(
            app,
            lambda: (
                javascript(
                    app, shell.page, "document.querySelectorAll('.animal-preview tbody tr').length"
                )
                > 0
            ),
            timeout=15,
        )
        javascript(
            app,
            shell.page,
            "document.querySelector('.animal-sorting summary').click();"
            "Array.from(document.querySelectorAll('.animal-sorting button')).find("
            "b => b.textContent === 'Add sort rule').click()",
        )
        wait_until(
            app, lambda: len(shell.controller.analysis_sorts.get("pooled_metrics.csv", [])) >= 3
        )
        wait_until(
            app,
            lambda: javascript(
                app,
                shell.page,
                "!document.querySelector('.animal-preview').inert && "
                "document.querySelectorAll('.animal-sorting select"
                '[aria-label="Sort direction"]\').length === 4',
            ),
        )
        javascript(
            app,
            shell.page,
            "const direction=document.querySelectorAll("
            "'.animal-sorting select[aria-label=\"Sort direction\"]')[0];"
            "direction.value='desc'; direction.dispatchEvent(new Event('change'))",
        )
        wait_until(
            app,
            lambda: shell.controller.analysis_sorts["pooled_metrics.csv"][0]["descending"],
        )
        rules = [dict(item) for item in shell.controller.analysis_sorts["pooled_metrics.csv"]]
        assert len({item["column"] for item in rules}) == len(rules)
        javascript(app, shell.page, "document.querySelector('#animal-dialog').close()")
        javascript(app, shell.page, "document.querySelector('[data-workflow=export]').click()")
        javascript(app, shell.page, "document.querySelector('#advanced-export').open=true")
        click_action("detailed-csv")
        wait_until(app, lambda: bool(list(tmp_path.glob("*/sessions.csv"))), timeout=15)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=15)
        assert "Saved" in shell.controller.export_status.text()
        assert list(tmp_path.glob("*/pooled_metrics.csv"))
        with next(tmp_path.glob("*/sessions.csv")).open(newline="", encoding="utf-8") as f:
            headers = next(csv.reader(f))
        assert "analysis_cohort" not in headers
        assert "analysis_session_order" not in headers
        wait_until(
            app,
            lambda: javascript(
                app, shell.page, "!document.querySelector('[data-action=detailed-excel]').disabled"
            ),
        )
        click_action("detailed-excel")
        wait_until(app, lambda: bool(list(tmp_path.glob("*/results.xlsx"))), timeout=15)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=15)
        book = load_workbook(next(tmp_path.glob("*/results.xlsx")), read_only=True)
        assert book["Choices"].max_row == 21
        book.close()
        javascript(app, shell.page, "document.querySelector('[data-workflow=project]').click()")
        click_action("save-project-as")
        wait_until(app, project.exists, timeout=15)
        wait_until(app, lambda: not shell.controller._is_working(), timeout=15)
        first.write_text(first.read_text() + "\n")
        click_action("check-sources")
        wait_until(app, lambda: first in shell.controller._source_issues, timeout=15)
        assert first not in shell.controller.import_results
        click_action("open-project")
        wait_until(app, lambda: not shell.controller.import_results, timeout=15)
        assert first in shell.controller.selected_files
        assert not shell.controller.import_results
        assert shell.controller.metadata_assignments[first] == annotation
        assert shell.controller.phase_assignments[first] == "Acquisition"
        assert shell.controller.analysis_sorts["pooled_metrics.csv"] == rules
        javascript(app, shell.page, "document.querySelector('[data-workflow=export]').click()")
        wait_until(
            app,
            lambda: (
                "project"
                in javascript(
                    app, shell.page, "document.querySelector('#export-folder-name').value"
                )
            ),
        )
    finally:
        shell.close()
        app.processEvents()


def test_web_failed_and_withheld_statuses(app, phase_input, monkeypatch):
    withheld = phase_input(name="withheld.txt")
    withheld.write_text(withheld.read_text().replace(" 0: 5 5 10", " 0: 5 5 11"))
    failed = phase_input(name="failed.txt", program="UNSUPPORTED")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda *args: ([str(withheld), str(failed)], "")
    )
    shell = WebShell()
    shell.show()
    try:
        wait_until(
            app, lambda: javascript(app, shell.page, "Boolean(window.trialReady)"), timeout=20
        )
        javascript(app, shell.page, "document.querySelector('[data-batch=sessions]').click()")
        javascript(app, shell.page, "document.querySelector('[data-action=add-files]').click()")
        wait_until(
            app,
            lambda: javascript(
                app, shell.page, "!document.querySelector('[data-action=import]').disabled"
            ),
        )
        javascript(app, shell.page, "document.querySelector('[data-action=import]').click()")
        wait_until(app, lambda: len(shell.controller.import_results) == 2, timeout=15)
        wait_until(
            app,
            lambda: (
                javascript(app, shell.page, "document.querySelector('#batch-table').innerText")
                and "Withheld"
                in javascript(app, shell.page, "document.querySelector('#batch-table').innerText")
                and "Failed"
                in javascript(app, shell.page, "document.querySelector('#batch-table').innerText")
            ),
            timeout=15,
        )
    finally:
        shell.close()
        app.processEvents()
