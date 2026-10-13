# Trial Cruncher

**From raw trials to analysis-ready data.**

Trial Cruncher is a Python desktop application foundation for behavioral neuroscience
research. It is intended to turn raw experiment files into traceable subject, session,
trial, and group datasets for personal research and broader laboratory use. Tasks do
not need to have trials.

## Current functionality

- Installable `src/` package and help/version command line interface.
- PySide6 window with individual file and folder selection, configurable extensions,
  optional recursive discovery, duplicate removal, and clear selection.
- Filesystem discovery in a background worker, with visible discovery messages and
  structured JSON logs on standard error when a console is available.
- Canonical event/session/trial records and small reader, normalizer, metric, and
  exporter interfaces for future implementations.
- Synthetic unit tests, offscreen GUI integration tests, Ruff, and GitHub Actions.

**No behavioral files are parsed and no scientific metrics or exports are generated
yet.** Extensions identify candidates only. MATLAB and Med-PC reader implementations
require representative example files and documented schemas. Synthetic tests verify
software behavior, not scientific validity.

## Planned capabilities

Batch import of MATLAB (including v7.3) and Med-PC exports; task-specific normalization
and event identification; configurable and documented behavioral metrics; trial,
session, subject, and group tables; and CSV/Excel export with reproducibility metadata.
Planned paradigms include operant conditioning, reinforcement learning, probabilistic
reversal learning, and progressive ratio. None of their experimental assumptions
are embedded in this skeleton.

The eventual workflow is **Import Files → Select Paradigm → Configure Metrics →
Process Batch → Review Results → Export Tables**. Only file selection/discovery works
in this iteration.

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
  normalization.py         Raw-to-canonical conversion contract
  paradigms.py              Explicit task configuration
  metrics.py               Task-specific calculation contract
  exporters.py             Table export contract
  gui/                     PySide6 app, selection UI, discovery worker
tests/                     Synthetic core and offscreen GUI checks
docs/                      Architecture, metric standards, development
.github/workflows/ci.yml    Python 3.12/3.14 lint and test jobs
```

Batch orchestration and table generation are documented next-stage components,
not empty executable stages. See [architecture](docs/architecture.md) and
[metric conventions](docs/metrics.md).

## Project status and next milestones

1. Obtain de-identified MATLAB and Med-PC examples plus event codes, units, and schema
   documentation; implement one tested reader and normalizer.
2. Select one paradigm and agree on independently checkable metric definitions.
3. Add batch results with per-file failures, table builders, and export manifests.
4. Extend the GUI with task/configuration controls, progress, review, and export.

No software license has been selected. No author identity is declared.
