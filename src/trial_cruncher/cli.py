"""Lightweight entry point; importing the CLI does not load Qt."""

import argparse

from trial_cruncher import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trial-cruncher", description="From raw trials to analysis-ready data."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--gui", action="store_true", help="Launch the file-selection window")
    args = parser.parse_args(argv)
    if args.gui:
        from trial_cruncher.gui.app import main as gui_main

        return gui_main()
    parser.print_help()
    return 0
