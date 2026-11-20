"""Fixed end-to-end check run by the release jobs on an installed desktop."""

import csv
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QFileDialog

from trial_cruncher.gui.web_shell import WebShell
from trial_cruncher.version import __version__


def verify_install(app: QApplication, window: WebShell) -> int:
    """Exercise shipped WebEngine resources, background processing and export."""

    def wait_for(predicate, description: str) -> None:
        deadline = time.monotonic() + 60
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for {description}")
            app.processEvents()
            time.sleep(0.01)

    def evaluate(expression: str):
        received = []
        window.page.runJavaScript(expression, received.append)
        wait_for(lambda: bool(received), "renderer response")
        return received[0]

    def click(action: str) -> None:
        button = f"document.querySelector('[data-action={action}]')"
        wait_for(lambda: evaluate(f"Boolean({button} && !{button}.disabled)"), action)
        evaluate(f"{button}.click()")

    # The outer verifier supplies an empty working directory. Use exclusive
    # creation for the receipt, even if invoked separately at a terminal.
    with Path("trial-cruncher-install-check.json").open("x", encoding="utf-8") as receipt:
        try:
            with TemporaryDirectory(prefix="trial-cruncher-verification-") as temporary:
                directory = Path(temporary)
                source = directory / "synthetic.txt"
                source.write_text(
                    "File: synthetic\nSubject: 0007\nMSN: PRL_BO\nS: 10\n"
                    "A:\n  0: 2 2 4\nB:\n  0: 1 1 1 1\nC:\n  0: 0.01 1.02 2.06 3.07\n",
                    encoding="utf-8",
                )
                wait_for(lambda: evaluate("Boolean(window.trialReady)"), "Qt WebChannel")
                # Substitute only the OS picker responses in this dedicated process.
                with (
                    patch.object(QFileDialog, "getOpenFileNames", return_value=([str(source)], "")),
                    patch.object(QFileDialog, "getExistingDirectory", return_value=temporary),
                ):
                    click("add-files")
                    click("import")
                    wait_for(
                        lambda: evaluate(
                            "document.querySelector('#batch-table')?.innerText.includes('0.5000')"
                        ),
                        "rendered recording metrics",
                    )
                    evaluate("document.querySelector('[data-workflow=export]').click()")
                    click("export-csv")
                    wait_for(
                        lambda: (
                            any(directory.glob("*/manifest.json"))
                            and not window.controller._is_working()
                        ),
                        "CSV export",
                    )
                (manifest_path,) = directory.glob("*/manifest.json")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                with manifest_path.with_name("data.csv").open(
                    encoding="utf-8", newline=""
                ) as stream:
                    (row,) = csv.DictReader(stream)
                if (
                    row["ID"] != "0007"
                    or float(row["Proportion correct"]) != 0.5
                    or float(row["Trials/min"]) != 24
                    or manifest["application_version"] != __version__
                    or Path(manifest["inputs"][0]["source_file"]).resolve() != source.resolve()
                ):
                    raise RuntimeError("Installed app produced incorrect values or provenance.")
                json.dump({"version": __version__, "verified": True}, receipt)
                return 0
        except Exception as error:
            json.dump({"error": str(error)}, receipt)
            return 1
        finally:
            window.close()
            app.processEvents()
