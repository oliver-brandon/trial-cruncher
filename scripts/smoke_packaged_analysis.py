"""Check the packaged CLI on a small synthetic Med-PC recording."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    cli = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="trial-cruncher-smoke-") as temporary:
        source = Path(temporary) / "synthetic.txt"
        source.write_text(
            "File: synthetic\nSubject: 0007\nMSN: PRL_BO\nS: 10\n"
            "A:\n  0: 2 2 4\nB:\n  0: 1 1 1 1\nC:\n  0: 0.01 1.02 2.06 3.07\n",
            encoding="utf-8",
        )
        run = subprocess.run(
            [str(cli), "--inspect-medpc", str(source)], capture_output=True, text=True, timeout=60
        )
        if run.returncode != 0:
            raise RuntimeError(f"Packaged analysis failed ({run.returncode}): {run.stderr}")
        data = json.loads(run.stdout)
        if len(data["choices"]) != 4 or data["subject_id"] != "0007":
            raise RuntimeError("Unexpected packaged Med-PC result.")


if __name__ == "__main__":
    main()
