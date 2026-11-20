"""Frozen CLI entry point, with desktop launch delegated to the installed app."""

import os
import subprocess
import sys
from pathlib import Path

from trial_cruncher.cli import main
from trial_cruncher.version import APP_NAME, BUNDLE_APP_NAME


def launch_desktop() -> int:
    executable = Path(sys.executable).resolve()
    directory = executable.parent
    if sys.platform == "darwin":
        if directory.name == "bin" and directory.parent.name == "Resources":
            directory = directory.parent.parent / "MacOS"
            candidates = [directory / APP_NAME, directory / BUNDLE_APP_NAME]
        else:
            app = directory / f"{BUNDLE_APP_NAME}.app"
            candidates = [app / "Contents" / "MacOS" / BUNDLE_APP_NAME]
    elif sys.platform == "win32":
        candidates = [directory / f"{APP_NAME}.exe", directory / f"{BUNDLE_APP_NAME}.exe"]
    else:
        candidates = [directory / APP_NAME, directory / BUNDLE_APP_NAME]
    desktop = next((path for path in candidates if path.is_file()), None)
    if desktop is None:
        print(
            "Trial Cruncher desktop executable could not be found beside this CLI.", file=sys.stderr
        )
        return 1
    env = os.environ.copy()
    # PyInstaller adjusts this path for the CLI's temporary extraction. The desktop
    # has its own libraries and must not inherit a directory that will be deleted.
    for name in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        original = env.pop(name + "_ORIG", None)
        if original is None:
            env.pop(name, None)
        else:
            env[name] = original
    subprocess.Popen([str(desktop)], env=env, close_fds=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(gui_launcher=launch_desktop))
