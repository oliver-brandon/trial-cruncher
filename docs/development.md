# Development

## Setup

Install Python 3.12+ and create an isolated environment in the checkout:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Use `.venv\Scripts\Activate.ps1` on Windows PowerShell. On Linux, `python3` may be
the command name; install the matching distribution `venv` package if ensurepip is
unavailable. This project uses standard `pyproject.toml` packaging with Hatchling;
no global Python package installation is needed.

Run `trial-cruncher --gui` (or `trial-cruncher-gui`). Use
`python -m trial_cruncher --version` to verify the active installation.

## Verification

```sh
pytest
ruff check .
ruff format --check .
python -m pip check
```

Use `ruff format .` to apply formatting. Tests exercise read-only discovery,
case-insensitive filtering, recursion, deduplication, access failures, symlink cycles,
missing-versus-zero values, CLI isolation from Qt, JSON logging, and GUI selection
through mocked native dialogs plus actual background discovery and Qt signals.
GUI import tests also cover mixed successes/warnings/failures, visible decoded values,
raw review after unsupported-program failures, stale-result removal on re-import,
background-thread execution, cancellation, and deferred close while a file is active.
CSV export tests cover provenance/JSON round trips, missing versus zero/false,
empty and invalid choices, excluded inputs, no-overwrite behavior, partial-write
cleanup, GUI background export, failure/retry, and deferred close. See
[csv-export.md](csv-export.md) for the versioned schema and limits.
`tests/test_prl_metrics.py` covers the approved hand-calculated examples, strict
withholding, saved-count disagreements, missing versus empty choices, independent
unavailability reasons, and warning-only cases. GUI/CSV integration checks cover
metric display, full export precision, per-result reasons/status, background
calculation, failed-file isolation, and clearing stale summaries on re-import.
All fixtures are synthetic. The GUI suite selects Qt's offscreen platform before
creating the application; this checks widgets and signals, not interactive desktop
rendering or native file dialog behavior.

`tests/test_medpc.py` adds synthetic Med-PC extraction/PRL decoding checks with
hand-constructed outcomes, source line/hash checks, missing-versus-empty arrays,
invalid choices, terminators, summary mismatches, and CLI status/logging checks.
These tests have no dependency on ignored local research data. For a real local
sample, run `trial-cruncher --inspect-medpc "data/your-session.txt"` and compare
the returned choices and summary checks with the source; exit code 2 means the
inspection completed with warnings. See [medpc.md](medpc.md) for interpretation rules
and the recorded scope of local sample validation. Never copy research recordings
into committed test fixtures without explicit approval.

For a desktop smoke test, launch the app, select both files and a folder, change
extensions and recursion, verify deduplication/messages, and clear the selection.
Import supported Med-PC files, switch between all four review tabs, and include a
malformed/unsupported file to verify other sessions still import. Check warnings and
unavailable values, cancel a multi-file import, and re-import after a file changes.
Export CSV twice to the same parent folder, verify distinct folders and all three
files, inspect warnings and blank values, and test cancelling the folder picker.
Confirm inputs and the first export remain unchanged. Current CI uses Ubuntu with Python 3.12 and 3.14;
macOS and Windows interactive behavior requires separate verification. Linux Qt may
require EGL/OpenGL libraries (`libegl1` and `libopengl0` on Ubuntu). Remote desktops
may need additional platform-specific Qt/X11 libraries.

## Contributions

Read `AGENTS.md`, architecture documentation, and the relevant code/tests first.
Keep a focused change with meaningful tests, actual validation results, and updated
documentation. Keep the core GUI-independent. Avoid adding generic plugin systems
before there are concrete implementations to extend.

Obtain de-identified examples and event/schema documentation before implementing a
parser. Document metric formulas using `metrics.md` before implementing calculations.
Record uncertain semantics explicitly and stop short of fabricating data or silently
discarding observations. Never commit real research files or secrets; ignored
`data/`, `outputs/`, and `local/` directories are provided for local work.

Dependencies use compatible minimum versions rather than a lockfile in this initial
foundation. For reproducible research deployments, record the actual resolved
environment and all analysis configuration. Current CSV manifests record runtime
versions, import/export scope, and the PRL definition set/version and strict
eligibility policy. Additional metric configuration must be recorded when implemented. Do not describe a passing development build as scientific validation.

No license or author identity has been assigned. Publishing and licensing decisions
remain with the repository owner.
