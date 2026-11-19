"""Exercise staged multi-file editing and backend validation with synthetic recordings."""

import json
import os

import pytest
from qt_helpers import javascript, wait_until

from trial_cruncher.gui.web_assignments import assignment_page, save_assignments
from trial_cruncher.gui.web_shell import WebShell
from trial_cruncher.gui.window import MainWindow


def test_assignment_pages_and_atomic_failure(app, phase_input):
    window = MainWindow()
    files = [phase_input(name=f"{i}.txt") for i in range(3)]
    window.selected_files.update(files)
    window.overview.set_files(files, {})
    try:
        assert assignment_page(window, 1, 1)["rows"][0]["id"] == str(files[1])
        rows = assignment_page(window, 0, 3)["rows"]
        payload = {
            "kind": "metadata",
            "changes": [
                {
                    "id": row["id"],
                    "before": row["metadata"],
                    "value": {**row["metadata"], "condition": "A"},
                }
                for row in rows
            ],
        }
        payload["changes"][1]["value"]["included"] = False
        with pytest.raises(ValueError, match="reason"):
            save_assignments(window, payload)
        assert window.metadata_assignments == {}
        payload["changes"][1]["value"]["inclusion_reason"] = "Equipment"
        save_assignments(window, payload)
        assert window.metadata_assignments[files[1]].included is False
        with pytest.raises(ValueError, match="changed"):
            save_assignments(window, payload)
        with pytest.raises(ValueError, match="selection"):
            save_assignments(
                window,
                {
                    "kind": "phase",
                    "changes": [{"id": "/unknown", "before": "", "value": "Reversal"}],
                },
            )
        assert not window.phase_assignments
    finally:
        window.close()


@pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="Requires the embedded Chromium runtime",
)
def test_select_individual_files_cancel_and_save_in_web_editor(app, phase_input):
    files = [phase_input(name=f"recording-{i}.txt") for i in range(3)]
    shell = WebShell()
    shell.show()

    def js(code):
        return javascript(app, shell.page, code)

    def click(selector):
        js(f"document.querySelector({json.dumps(selector)}).click()")

    def open_editor(action):
        click(f'[data-action="{action}"]')
        wait_until(app, lambda: js("document.querySelectorAll('#assignments tbody tr').length===3"))

    try:
        shell.controller.add_paths([str(p) for p in files])
        wait_until(app, lambda: js("document.querySelectorAll('#batch-table tbody tr').length===3"))
        open_editor("phase")
        js(
            "const bulk=document.querySelector('.assignment-entry input');"
            "bulk.value='Acquisition';"
            "bulk.dispatchEvent(new Event('input'))"
        )
        click("#assignments .assignment-tools button:last-child")
        click("#assignments .primary")
        wait_until(app, lambda: js("!document.querySelector('#assignments')"))
        assert shell.controller.phase_assignments == dict.fromkeys(files, "Acquisition")
        for save in (False, True):
            open_editor("metadata")
            js(
                "(()=>{const input=document.querySelector('.assignment-entry input');"
                "input.value='Vehicle'; input.dispatchEvent(new Event('input'))})()"
            )
            for i in (1, 3):
                click(f"#assignments tbody tr:nth-child({i}) input[type=checkbox]")
            click("#assignments .assignment-tools button")
            if save:
                click("#assignments .primary")
            else:
                click("#assignments footer button:nth-last-child(2)")
            wait_until(app, lambda: js("!document.querySelector('#assignments')"))
            expected = {files[0], files[2]} if save else set()
            assert set(shell.controller.metadata_assignments) == expected
        assert all(
            value.condition == "Vehicle" for value in shell.controller.metadata_assignments.values()
        )
    finally:
        shell.close()
        app.processEvents()
