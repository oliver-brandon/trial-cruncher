#!/usr/bin/env python3
"""Print build metadata without importing Qt or requiring an installed application."""

import argparse
import json
import os
import re
import runpy
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = "src/trial_cruncher/version.py"


def metadata() -> dict[str, str]:
    values = runpy.run_path(str(ROOT / VERSION_PATH))
    channel, runtime = values["update_target"](
        os.environ.get("TRIAL_CRUNCHER_UPDATE_SYSTEM"),
        os.environ.get("TRIAL_CRUNCHER_UPDATE_MACHINE"),
    )
    return {
        "version": values["__version__"],
        "ui_version": values["__version__"],
        "app_name": values["APP_NAME"],
        "install_app_name": values["INSTALL_APP_NAME"],
        "bundle_app_name": values["BUNDLE_APP_NAME"],
        "archive_stem": values["ARCHIVE_STEM"],
        "bundle_identifier": values["BUNDLE_IDENTIFIER"],
        "update_package_id": values["UPDATE_PACKAGE_ID"],
        "update_channel": channel,
        "update_runtime": runtime,
        "update_repository_url": values["UPDATE_REPOSITORY_URL"],
        "update_release_tag": values["UPDATE_RELEASE_TAG"],
        "velopack_version": values["VELOPACK_VERSION"],
    }


def check(values: dict[str, str]) -> None:
    version = values["version"]
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Installer version must be numeric MAJOR.MINOR.PATCH.")
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if (
        "version" not in config["project"].get("dynamic", [])
        or config["tool"]["hatch"]["version"]["path"] != VERSION_PATH
    ):
        raise ValueError("Wheel and installer must use the same version source.")
    build_deps = config["project"]["optional-dependencies"]["build"]
    if f"velopack=={values['velopack_version']}" not in build_deps:
        raise ValueError("The Python Velopack SDK and installer CLI pins must match.")
    if values["update_release_tag"] != f"v{version}":
        raise ValueError("Stable release tag must match the package version.")
    if values["update_package_id"] != values["bundle_identifier"]:
        raise ValueError("The installed app and updater must share a package identity.")
    notes = (ROOT / "packaging/velopack/release-notes.md").read_text(encoding="utf-8").splitlines()
    if not notes or not notes[0].startswith("# ") or version not in notes[0].split():
        raise ValueError(f"Update release-notes.md for version {version}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--field")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        values = metadata()
        if args.check:
            check(values)
        if args.field:
            if args.field not in values:
                parser.error(f"Unknown metadata field: {args.field}")
            print(values[args.field])
        elif args.check:
            print(f"Validated {values['version']} for {values['update_channel']}.")
        else:
            print(json.dumps(values, indent=2))
    except (KeyError, ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
