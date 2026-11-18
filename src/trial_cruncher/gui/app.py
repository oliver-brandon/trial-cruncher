"""Desktop application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from trial_cruncher.gui.web_shell import WebShell
from trial_cruncher.logging_config import configure_logging


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Trial Cruncher")
    window = WebShell()
    window.show()
    return app.exec()
