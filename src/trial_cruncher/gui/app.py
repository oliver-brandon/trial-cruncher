"""Desktop application entry point."""

import sys

from trial_cruncher.logging_config import configure_logging
from trial_cruncher.version import APP_NAME, __version__


def main() -> int:
    configure_logging()
    from trial_cruncher.updates import run_velopack_startup

    run_velopack_startup()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from trial_cruncher.gui.web_shell import ASSET_DIRECTORY, WebShell

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(ASSET_DIRECTORY / "icons" / "trial-cruncher.png")))
    window = WebShell()
    window.show()
    if sys.argv[1:] == ["--verify-install"]:
        from trial_cruncher.gui.install_check import verify_install

        return verify_install(app, window)
    return app.exec()
