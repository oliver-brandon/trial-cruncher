"""Desktop application entry point."""

import sys

from PySide6.QtWidgets import QApplication

from trial_cruncher.gui.window import MainWindow
from trial_cruncher.logging_config import configure_logging


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Trial Cruncher")
    window = MainWindow()
    window.show()
    return app.exec()
