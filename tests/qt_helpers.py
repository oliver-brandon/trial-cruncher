"""Pump the Qt event loop while awaiting a worker in offscreen tests."""

import time


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
