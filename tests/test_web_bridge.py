"""Validation at the embedded frontend boundary."""

import json

from trial_cruncher.gui.web_bridge import WebBridge
from trial_cruncher.gui.window import MainWindow


def test_bridge_rejects_invalid_actions_and_keeps_options(app):
    window = MainWindow()
    bridge = WebBridge(window)
    original = window.recursive.isChecked()
    try:

        def action(name, payload):
            return json.loads(bridge.action(name, json.dumps(payload)))

        assert "error" in action("set_options", {"recursive": "false"})
        assert window.recursive.isChecked() == original
        assert "error" in action("sort", {"view": "unknown", "column": 0, "descending": False})
        assert "error" in action("select", {"path": "/not-in-this-project"})
        assert "error" in action("import", {})
        assert "error" in json.loads(bridge.batch("unknown", 0, 20))
    finally:
        window.close()
