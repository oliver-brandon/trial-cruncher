"""Local desktop preferences shared by the window and embedded workspace."""

from PySide6.QtCore import QSettings

from trial_cruncher.version import APP_NAME


def workspace_settings() -> QSettings:
    return QSettings(APP_NAME, APP_NAME)
