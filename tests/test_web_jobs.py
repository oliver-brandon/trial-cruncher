"""Use the embedded controls to cancel imports and reject stale exports."""

import os
from threading import Event

import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox
from qt_helpers import javascript, wait_until

from trial_cruncher.gui import import_worker
from trial_cruncher.gui.web_shell import WebShell

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="Requires the embedded Chromium runtime",
)


def test_cancel_preserves_completed_source_and_export_rechecks_it(
    app, phase_input, tmp_path, monkeypatch
):
    first, second = (phase_input(name=name) for name in ("a.txt", "b.txt"))
    entered, release = Event(), Event()
    original = import_worker.import_medpc_file

    def delayed(path, phase, annotation):
        entered.set()
        if not release.wait(timeout=15):
            raise TimeoutError("Timed out waiting for the test to request cancellation.")
        return original(path, phase, annotation)

    monkeypatch.setattr(import_worker, "import_medpc_file", delayed)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, msg: errors.append(msg))
    shell = WebShell()
    shell.show()
    controller = shell.controller

    def click(selector):
        query = f"document.querySelector('{selector}')"
        wait_until(app, lambda: javascript(app, shell.page, f"!!{query} && !{query}.disabled"))
        javascript(app, shell.page, f"{query}.click()")

    try:
        controller.add_paths([str(first), str(second)])
        wait_until(app, lambda: javascript(app, shell.page, "Boolean(window.trialReady)"))
        click("[data-action=import]")
        wait_until(app, entered.is_set)
        click("[data-action=cancel]")
        wait_until(app, lambda: not controller.cancel_button.isEnabled())
        release.set()
        wait_until(app, lambda: not controller._is_working())
        assert set(controller.import_results) == {first}
        assert controller.overview.model.row(1).quality == "Not imported (cancelled)"
        first.write_text(first.read_text() + "\n")
        click("[data-workflow=export]")
        click("[data-action=export-csv]")
        wait_until(app, lambda: bool(errors))
        assert "re-import" in errors[0].lower()
        assert first not in controller.import_results
        assert not list(tmp_path.glob("*/manifest.json"))
    finally:
        release.set()
        shell.close()
        app.processEvents()
