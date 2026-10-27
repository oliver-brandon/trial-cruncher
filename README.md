# Trial Cruncher

**From raw trials to analysis-ready data.**

Trial Cruncher is a Python desktop application foundation for behavioral neuroscience
research. It is intended to turn raw experiment files into traceable subject, session,
trial, and group datasets for personal research and broader laboratory use. Tasks do
not need to have trials.

## Current functionality

- Installable `src/` package and help/version command line interface.
- PySide6 window with individual file and folder selection, configurable extensions,
  optional recursive discovery, duplicate removal, and clear selection. Import Med-PC
  sessions and review details, decoded choices, warnings/checks, and source text.
- Filesystem discovery in a background worker, with visible discovery messages and
  structured JSON logs on standard error when a console is available.
- Canonical event/session/trial records and small reader, normalizer, metric, and
  exporter interfaces for future implementations.
- A read-only Med-PC text reader and PRL normalizer for the confirmed `PRL_BO` and
  `PRL_OPTO_CORSTIM` programs, with choice decoding, source provenance, and saved-count
  consistency checks. Use the GUI, `--inspect-medpc FILE`, or the Python API.
- Background imports with progress, per-file failure isolation, and cancellation
  after the current file. Completed results remain available for review.
- Synthetic unit tests, offscreen GUI integration tests, Ruff, and GitHub Actions.

**Med-PC import review is available in the GUI, CLI, and Python API.**
No behavioral metric suite or CSV/Excel exports are implemented.
Extensions identify candidates only. Other formats/programs require representative
example files and documented schemas. Synthetic tests verify software behavior, not
scientific validity. See [Med-PC support and confirmed rules](docs/medpc.md).

## Planned capabilities

Batch import of MATLAB (including v7.3) and Med-PC exports; task-specific normalization
and event identification; configurable and documented behavioral metrics; trial,
session, subject, and group tables; and CSV/Excel export with reproducibility metadata.
Planned analysis paradigms include operant conditioning, reinforcement learning,
probabilistic reversal learning, and progressive ratio. The first normalizer is scoped
to two confirmed PRL programs; it does not impose their conventions on other tasks.

The eventual workflow is **Import Files → Select Paradigm → Configure Metrics →
Process Batch → Review Results → Export Tables**. The desktop currently supports file
selection and Med-PC import review; task configuration, metrics, and export are future work.

## Installation and launch

Use Python 3.12 or newer in a virtual environment. From the repository directory:

```sh
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e .
trial-cruncher --help
trial-cruncher --version
trial-cruncher --gui
# Inspect one supported Med-PC session without launching Qt:
trial-cruncher --inspect-medpc "data/your-session.txt"
```

`trial-cruncher-gui` also launches the desktop window. `python -m trial_cruncher`
supports the same CLI options. Some Linux systems name Python `python3` and require
their `python3-venv` package to create virtual environments. A graphical desktop and
Qt's platform libraries are needed for interactive GUI use.

Choose **Add files…** or **Add folder…**. Defaults are `.mat`, `.txt`, `.med`, and `.mpc`;
change the comma-separated extension field for other naming conventions. Extensions
are case-insensitive. They apply to subsequent additions; **Clear selection** and
re-add to filter an existing selection. Folder traversal ignores files with other
extensions. Explicit mismatches, inaccessible paths, and skipped directory symlinks
appear in Discovery messages. Symlinked folders must be selected explicitly.

Click **Import Med-PC** to read all files in the list, then click a file to review it:

- **Session details:** identifiers, task duration from `S`, original headers, and provenance.
- **Decoded choices:** source array index, time, correct/rewarded outcome, raw value,
  and source line. Missing decoded values display as **Unavailable**, not zero.
- **Warnings and checks:** per-file problems and saved-count comparisons.
- **Source text:** the read-only original decoded export text.

Each file is marked Imported, Warnings, or Failed; a failed file does not stop other
imports. Unsupported formats/programs, `.MPC` program source, and `._*` sidecars are
reported as failures if included. **Cancel after current file** keeps completed
results and leaves the remaining files unimported. Re-importing re-reads all listed
files and replaces their previous results; **Clear selection** clears the in-memory
review. Closing during import cancels remaining files and waits for the current file.

Discovery never writes to inputs. It does not check content validity or readability
beyond filesystem metadata. Full resolved paths are displayed and may appear in logs;
review logs before sharing them outside the laboratory.

## Development

```sh
python -m pip install -e '.[dev]'
pytest
ruff check .
ruff format --check .
```

GUI tests use Qt's offscreen platform automatically. On Linux without Qt runtime
libraries, install your distribution's EGL/OpenGL packages before running GUI tests
(Ubuntu CI uses `libegl1` and `libopengl0`). See [development](docs/development.md).

## Structure

```text
src/trial_cruncher/
  cli.py, __main__.py       CLI entry points; lazy GUI import
  discovery.py             Read-only discovery and per-path issues
  logging_config.py        Structured application logging
  models.py                Canonical records and calculated results
  readers.py               Content detection and raw extraction contract
  medpc.py                 Med-PC text extraction and raw provenance
  normalization.py         Raw-to-canonical conversion contract
  prl.py                   Confirmed PRL choice decoding and count validation
  processing.py            GUI-independent single-file import results/errors
  paradigms.py              Explicit task configuration
  metrics.py               Task-specific calculation contract
  exporters.py             Table export contract
  gui/                     PySide6 review panels, choice table, background workers
tests/                     Synthetic core and offscreen GUI checks
docs/                      Architecture, metric standards, development
.github/workflows/ci.yml    Python 3.12/3.14 lint and test jobs
```

Batch analysis and output table generation are documented next-stage components,
not empty executable stages. See [architecture](docs/architecture.md) and
[metric conventions](docs/metrics.md).

## Project status and next milestones

1. Validate further session variants, including an actual early-stopped or timed-out recording.
2. Agree on independently checkable PRL metric definitions before calculating metrics.
3. Add batch metric calculation, output table builders, and export manifests.
4. Extend the GUI with task/configuration controls and export.

No software license has been selected. No author identity is declared.
