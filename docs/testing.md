# Testing

## Setup

Install Python 3.12+ and create an isolated environment in the checkout:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
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

To include the actual embedded Chromium renderer in the test run, use:

```sh
TRIAL_CRUNCHER_WEBENGINE_TESTS=1 pytest
```

On Windows PowerShell set `$env:TRIAL_CRUNCHER_WEBENGINE_TESTS = "1"` before
running `pytest`. The tests use a local WebEngine page, native picker test doubles,
synthetic recordings and the real background workers. Run these tests in an
environment that permits Chromium subprocesses. CI enables this suite in the Ubuntu full run and in the selected macOS and Windows tests.
For interactive desktop testing, launch `trial-cruncher --gui` with the normal
platform plugin and exercise the system file picker and display scaling.

The migration was also checked locally with the seven supplied partial recordings.
Exports launched through the embedded interface matched the pre-migration CSV
tables, Excel sheet values and structured manifests after excluding the export
timestamp. Source hashes and modification times matched. These checks cover
presentation and export parity for the supplied files.

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
`tests/test_excel.py` reloads Excel workbooks to verify native types, exact source
text/Decimal strings, missing and withheld values, quality reasons, complete long-text
chunks, formula-like literals, worksheet limits, invalid XML, and no-overwrite/write
failure safeguards. Export GUI and filtered-batch tests run for both CSV and Excel.
See [Excel export](excel-export.md) for the workbook schema and limitations.
`tests/test_partial_sessions.py` adds synthetic checks for observed-choice denominators
at short/timeout-length durations, unsupported-program raw preservation, corroborated
unused-tail exclusions, and refusing exclusions when counters or records conflict. Actual partial-session evidence and
its remaining boundaries are recorded in [partial-session validation](partial-session-validation.md).
`tests/test_prl_metrics.py` covers the approved hand-calculated examples, strict
withholding, saved-count disagreements, missing versus empty choices, independent
unavailability reasons, and warning-only cases. GUI/CSV integration checks cover
metric display, full export precision, per-result reasons/status, background
calculation, failed-file isolation, and clearing stale summaries on re-import.
`tests/test_overview.py` adds synthetic status/filter/numeric-sort checks and actual
Qt mouse selection through proxy rows, including duplicate filenames, hidden review
clearing, mid-import sorting/filtering and cancellation, malformed re-reads, and
full-batch export while filters hide rows. No new scientific definitions are added.
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
Import supported Med-PC files, switch between the review tabs, and include a
malformed/unsupported file to verify other sessions still import. Check warnings and
unavailable values, cancel a multi-file import, and re-import after a file changes.
Export CSV twice to the same parent folder, verify distinct folders and all four
files, inspect warnings and blank values, and test cancelling the folder picker.
Sort the overview numerically in both directions; verify missing values sort last.
Combine search/program/quality filters and confirm the visible/total count, select
rows with duplicate filenames from different folders, and check that filtering out
the selected row clears its review. Export with a filter active and confirm all
successful imports remain included. Confirm inputs and the first export remain unchanged.
Repeat with **Export Excel…**: inspect all five sheets, filters/frozen headers, source
IDs, missing/zero/false values, Quality reasons, and complete Provenance chunks. Open
`results.xlsx` in Microsoft Excel for native rendering verification when available.
Routine CI runs the full suite on Ubuntu with Python 3.12, scientific and export
compatibility checks on Ubuntu 3.14, and focused file-safety, project, and embedded
GUI checks on macOS and Windows with Python 3.12. Lint runs once in the Ubuntu 3.12 job. Tag pushes do not
start a duplicate ordinary CI run. For dependency upgrades or broader verification,
dispatch CI with **full_matrix** selected to run the full suite on all three systems
and both Python versions. Release jobs call this same full matrix for their exact
candidate commit. Each job has a 10-minute limit. During pytest, a test that stalls for 90 seconds prints thread stacks
and terminates that test process. A newer run on the same ref cancels the older run.
GUI tests drive dialog controls directly and report unexpected worker warnings as failures.
Native dialog appearance and display scaling need a desktop check on each target. Linux Qt may
require EGL/OpenGL libraries (`libegl1` and `libopengl0` on Ubuntu). Remote desktops
may need additional platform-specific Qt/X11 libraries.

## Contributions

Read the architecture documentation and the relevant code and tests first.
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
environment and all analysis configuration. Current CSV and Excel manifests record runtime
versions (including SciPy and h5py when installed), import/export scope, and the PRL definition set/version and strict
eligibility policy. Additional metric configuration must be recorded when implemented. Do not describe a passing test run as scientific validation.

No license or author identity has been assigned. Publishing and licensing decisions
remain with the repository owner.

## Batch performance measurements

These local measurements compare the cleanup with commit `7486825` on the same
Linux machine and Python environment. Import, model update, project, and export
times are medians of three runs. Synthetic recordings had 40 choices each. The
Qt model measurement starts with imported results and uses the offscreen platform.
The Excel workload includes the animal analysis tables.

| Operation | Before | After |
| --- | ---: | ---: |
| Discover 300 matching files among 6,000 directory entries | 80 ms | 18 ms |
| Import and calculate session and phase metrics for 360 files | 151 ms | 139 ms |
| Feed 360 results to the two batch views | 188 ms | 71 ms |
| Save a new 360-file project and load it | 64 ms | 36 ms |
| Export 32 recordings to Excel | 864 ms | 705 ms |
| Build the 14,400-row choice table, peak Python allocation | 22.3 MiB | 15.4 MiB |

Separately, all seven supplied partial-session recordings were exported with both
revisions in the same environment. CSV table bytes, workbook cell values, and
manifest contents matched after accounting for the export timestamp. Source file
hashes and modification times matched before and after.

## Phase metric verification

`tests/test_phase_metrics.py` covers the supplied hand-checked example, empty and
single-choice boundaries, first criterion/maintenance behavior, next-choice reward
independence, all 341 outcome sequences of length 0–4 against an independent
window/transition reference, strict withholding, missing phase, unused slots,
configuration hashes, literal phase labels, and stale phase export rejection.
The phase-dialog GUI tests cover cancel/save, bulk/custom assignments, duplicate
filenames, import snapshots, background execution, cancellation/failure, clearing,
and full-batch exports under active filters.

For desktop review, add files, open **Assign phases…**, set mixed labels (including
a custom reversal label), and save. Import, then inspect Phase metrics, criterion,
and each denominator. Edit assignments and export before re-importing to verify the
old reviewed phase is retained; re-import and confirm the new phase. Blank a phase,
re-import, and confirm session summaries still show while phase metrics are
unavailable. Export both formats and verify phase rows, annotations, and manifest
configuration hashes. Native Excel rendering needs separate verification.

## Project and freshness verification

`tests/test_projects.py` and `tests/test_project_gui.py` cover valid/malformed project
round trips, fixed configuration compatibility, missing sources, content hashing,
atomic saves, protection of originals/links/unrelated files, concurrent/external
edits, load failure isolation, background IO, busy/deferred-close behavior, changed
source invalidation, and re-import recovery. Export tests now require source hashes
to match; an old reviewed snapshot cannot be exported after its source changes.

For desktop review, save mixed per-file phases and discovery settings, open the
project in a new window, and verify every path/phase before importing. Use disposable
copies to test a changed and a missing input; confirm stale metrics clear and export
requires re-import. Save before re-import and verify the old reference hash remains.
Re-import and save again to update it. Check project Save As, picker cancellation,
and externally edited project rejection. Never alter research originals for tests.

`tests/test_proportion_correct.py` verifies 0, fractional, and 1 accuracy values,
plain numeric Excel formatting, renamed schema-4 columns and units, rejection of
old calculated snapshots, and safe percentage-project configuration upgrades. GUI
checks verify proportion labels/values and the explicit re-import/save migration flow.

`tests/test_phase_overview.py` checks stored metrics/ratio counts, missing/zero/withheld
states, full-precision numeric/boolean sorting, literal search, phase/status filters,
column layouts, mouse click-through, duplicate filenames, inactive-tab isolation,
cancellation/failure, stale sources, project load, and full-batch import/export scope.
For desktop review, select the upper **Phase results** tab, inspect each focused
layout, sort a denominator in both directions, filter out the selected row, and
switch upper tabs. The detailed review must never point to a hidden/different file.
Use a disposable source copy when checking source-change invalidation.

`tests/test_medpc_rate.py` covers recorded-S duration, manual-stop raw A[3] retention,
zero versus unavailable rates, missing/nonpositive/unrepresentable durations,
out-of-duration choices, strict count withholding, full export precision/provenance,
project updates, and rate sorting/filtering without phase assignments. Use the
**Session rate** batch layout and Session metrics tab for manual inspection.

`tests/test_phase_rate_export.py` checks that Phase metrics copies the exact session
rate/duration/count and preserves scope, unit, status, reasons, and result metadata
in both formats. Coverage includes unassigned phases, zero choices, invalid duration,
strict withholding, and warning-only results. Phase metric JSON remains eight metrics,
and Quality does not duplicate the rate as a phase metric. No recalculation occurs
in the export path. Export table/workbook versions are 6/5; scientific versions stay 4/2.

`tests/test_analysis_metadata.py` and `tests/test_metadata_gui.py` cover typed manual
metadata, reason validation, missing/false flags, no raw inference, unchanged metric
objects, immediate edits, numeric order sorting, view-only filters, all-record exports,
failed/unimported assignments, literal Excel text, project persistence/migration, and
background snapshots. For desktop review, set mixed inclusion states, filter to
Included, and confirm exports still contain every source with its explicit flag.
Save/load a project and verify annotations before and after re-import. Native dialogs
and native Excel rendering still need platform-specific verification.
