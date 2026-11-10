"""Lightweight entry point; importing the CLI does not load Qt."""

import argparse
import json
import logging
from pathlib import Path

from trial_cruncher import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trial-cruncher", description="From raw trials to analysis-ready data."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--gui", action="store_true", help="Launch the file-selection window")
    modes.add_argument(
        "--inspect-medpc",
        type=Path,
        metavar="FILE",
        help="Read one PRL Med-PC export and print decoded choices and validation warnings",
    )
    args = parser.parse_args(argv)
    if args.gui:
        from trial_cruncher.gui.app import main as gui_main

        return gui_main()
    if args.inspect_medpc:
        from trial_cruncher.logging_config import configure_logging
        from trial_cruncher.medpc import MedPCReader
        from trial_cruncher.prl import PRLNormalizer

        configure_logging()
        try:
            raw = MedPCReader().read(args.inspect_medpc)
            (session,) = PRLNormalizer().normalize(raw, args.inspect_medpc)
        except (ValueError, OSError) as exc:
            logging.getLogger(__name__).error(
                str(exc), extra={"path": args.inspect_medpc, "operation": "inspect_medpc"}
            )
            return 1
        print(
            json.dumps(
                {
                    "source_file": str(session.source_file),
                    "source_sha256": raw["source_sha256"],
                    "program": session.metadata["program"],
                    "subject_id": session.subject_id,
                    "session_id": session.session_id,
                    "duration_s": session.duration_s,
                    "head_entries_recorded": False,
                    "latency_available": False,
                    "summary_checks": session.metadata["summary_checks"],
                    "normalizer_version": session.metadata["normalizer_version"],
                    "choice_storage": session.metadata["choice_storage"],
                    "warnings": session.warnings,
                    "choices": [
                        {
                            "source_index": event.raw_values["index"],
                            "source_line": event.raw_values["line_number"],
                            "raw_value": str(event.raw_values["value"]),
                            "timestamp_s": event.timestamp_s,
                            **event.attributes,
                        }
                        for event in session.events
                    ],
                },
                indent=2,
                allow_nan=False,
            )
        )
        return 2 if session.warnings else 0
    parser.print_help()
    return 0
