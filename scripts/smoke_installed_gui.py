#!/usr/bin/env python3
"""Launch the installed desktop and verify completion of its synthetic GUI check."""

import json
import os
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: smoke_installed_gui.py INSTALLED_EXECUTABLE")
    executable = Path(sys.argv[1]).resolve(strict=True)
    expected = runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "src/trial_cruncher/version.py")
    )["__version__"]
    with tempfile.TemporaryDirectory(prefix="trial-desktop-check-") as temporary:
        run = subprocess.run(
            [str(executable), "--verify-install"],
            cwd=temporary,
            env=dict(os.environ, TRIAL_CRUNCHER_DEV="1"),
            timeout=240,
        )
        receipt = Path(temporary) / "trial-cruncher-install-check.json"
        if not receipt.is_file():
            raise RuntimeError(
                f"The desktop exited without a verification receipt ({run.returncode})."
            )
        result = json.loads(receipt.read_text(encoding="utf-8"))
        if run.returncode or result != {"version": expected, "verified": True}:
            raise RuntimeError(
                f"Installed desktop verification failed ({run.returncode}): {result}"
            )
        print(f"Installed Trial Cruncher {expected}: GUI, import, metrics and CSV verified.")


if __name__ == "__main__":
    main()
