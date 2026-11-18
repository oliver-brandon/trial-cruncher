"""Pump the Qt event loop while awaiting a worker in offscreen tests."""

import time
from contextlib import contextmanager


def wait_until(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), "Background operation did not finish"


def javascript(app, page, expression):
    result = []
    page.runJavaScript(expression, result.append)
    wait_until(app, lambda: bool(result), timeout=10)
    return result[0]


@contextmanager
def answer_dialog(monkeypatch, dialog_type, interact):
    """Drive the real dialog controls without a blocking nested Qt event loop."""
    handled = []
    failures = []

    def run(dialog):
        handled.append(dialog_type)
        dialog.open()
        try:
            interact(dialog)
            assert not dialog.isVisible(), f"{dialog_type.__name__} was left open"
        except Exception as exc:
            # The caller may be a Qt slot. Re-raise in the test after the click.
            failures.append(exc)
        finally:
            if dialog.isVisible():
                dialog.reject()
        return dialog.result()

    with monkeypatch.context() as patch:
        patch.setattr(dialog_type, "exec", run)
        yield
    if failures:
        raise failures[0]
    assert handled == [dialog_type], f"Expected one {dialog_type.__name__}"
