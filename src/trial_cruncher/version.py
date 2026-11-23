"""Canonical desktop package identity, release version, and supported update feeds."""

import platform

__version__ = "0.1.1"
APP_NAME = INSTALL_APP_NAME = "Trial Cruncher"
BUNDLE_IDENTIFIER = UPDATE_PACKAGE_ID = "com.trialcruncher.app"
UPDATE_CHANNEL_PREFIX = "stable"
UPDATE_REPOSITORY_URL = "https://github.com/oliver-brandon/trial-cruncher"
UPDATE_TAG_PREFIX = "v"
VELOPACK_VERSION = "1.2.0"

BUNDLE_APP_NAME = f"{APP_NAME} v{__version__}"
ARCHIVE_STEM = f"Trial-Cruncher-v{__version__}"
UPDATE_RELEASE_TAG = f"{UPDATE_TAG_PREFIX}{__version__}"


def update_target(system_name: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """Return (stable channel, Velopack runtime) for a published desktop target."""
    system = (system_name or platform.system()).strip().lower()
    arch = (machine or platform.machine()).strip().lower()
    if system == "windows" and arch in {"amd64", "x86_64", "x64"}:
        runtime = "win-x64"
    elif system in {"darwin", "macos"} and arch in {"arm64", "aarch64"}:
        runtime = "osx-arm64"
    else:
        raise ValueError(f"No Trial Cruncher installer target for {system}/{arch}.")
    return f"{UPDATE_CHANNEL_PREFIX}-{runtime}", runtime
