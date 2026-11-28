# Trial Cruncher

**From raw trials to analysis-ready data.**

Trial Cruncher is a Python desktop application for behavioral neuroscience
research. It is intended to turn raw experiment files into traceable subject, session,
trial, and group datasets for personal research and broader laboratory use. Tasks do
not need to have trials.

## Quick start for a recording batch

1. In **Import**, add the files or folder, assign phases and treatments, and choose **Import Med-PC**.
2. In **Review → Sessions**, read one row per recording. Hover over a column for its meaning or an unavailable metric for its reason. Select a row and choose **Inspect recording** to see its choices, counts, or source text.
3. In **Export**, edit **Folder name** if desired, then choose **Save Excel workbook…**. Start with **Data**, click an animal ID for its trials, and use **Metadata** to look up a recording or a blank result.

## Current functionality

- Installable `src/` package and help/version command line interface.
- Embedded Qt WebEngine workspace with native file and folder selection, configurable extensions,
  optional recursive discovery, duplicate removal, and clear selection. Import Med-PC
  sessions and review details, decoded choices, warnings/checks, and source text.
- Batch session overview with numeric sorting, text/program/quality filters, explicit
  missing and withheld values, and click-through review of each source.
- Batch phase-results comparison with error/criterion, win-stay, and lose-shift
  layouts, numerator/denominator columns, phase/status and metadata filters, and numeric sorting.
- Filesystem discovery in a background worker, with visible discovery messages and
  structured JSON logs on standard error when a console is available.
- Canonical event/session/trial records and small reader, normalizer, metric, and
  exporter interfaces for future implementations.
- A read-only Med-PC text reader and PRL normalizer for the confirmed `PRL_BO`,
  `PRL_OPTO`, and `PRL_OPTO_CORSTIM` programs, with choice decoding, source provenance, and saved-count
  consistency checks. Use the GUI, `--inspect-medpc FILE`, or the Python API.
- Background imports with progress, per-file failure isolation, and cancellation
  after the current file. Completed results remain available for review.
- Manual condition/treatment and Include/Exclude/Not reviewed
  assignments with exclusion reasons, saved in projects and retained in all exports.
- Save/load `.tcproj.json` projects with per-file phases, fixed analysis configuration,
  source hashes, and discovery settings; changed sources require re-import.
- Background CSV and Excel export to new folders with source metadata, warnings, missing values,
  and a manifest accounting for failed/unimported inputs.
- Synthetic unit tests, offscreen GUI integration tests, Ruff, and GitHub Actions.

**Med-PC import review is available in the GUI, CLI, and Python API.**
GUI CSV and Excel export of sessions and choices is available with provenance and an export
manifest. Seven PRL session-summary metrics are implemented with the approved strict
withholding policy. Eight phase-level accuracy, error, and strategy metrics are also
implemented with user-assigned phases and explicit criterion/denominator evidence.
Med-PC trials per minute uses validated recorded choices and S. The separately
defined MAT-derived rate and other metric families remain future work.
Extensions identify candidates only. Other formats/programs require representative
example files and documented schemas. Synthetic tests verify software behavior, not
scientific validity. See [Med-PC support and confirmed rules](docs/medpc.md).

## Planned capabilities

Batch import of MATLAB (including v7.3) and Med-PC exports; task-specific normalization
and event identification; configurable and documented behavioral metrics; trial,
session, subject, and group tables; and CSV/Excel export with reproducibility metadata.
Planned analysis paradigms include operant conditioning, reinforcement learning,
probabilistic reversal learning, and progressive ratio. The first normalizer is scoped
to three confirmed PRL program names; it does not impose their conventions on other tasks.

The eventual workflow is **Import Files → Select Paradigm → Configure Metrics →
Process Batch → Review Results → Export Tables**. The desktop currently supports file
selection, Med-PC import review, seven PRL session summaries, eight phase metrics,
manual phase assignment, and CSV/Excel export. Additional task configuration and
metric families remain future work.

## Install and update

The desktop distribution targets Windows x64 and Apple Silicon Macs. Once the
first stable release is published, use the Windows installer or the signed macOS
package from [Releases](https://github.com/oliver-brandon/trial-cruncher/releases).
Installed copies check for updates automatically and offer **Help → Check for
Updates…**. Ubuntu uses a Git checkout and a virtual environment.
See [desktop release setup](docs/desktop-releases.md) and [Ubuntu installation](docs/ubuntu-source.md).

## Installation from source

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
Qt's platform libraries are needed for interactive GUI use. The PySide6 distribution
includes Qt WebEngine and Qt WebChannel. The application loads its bundled HTML, CSS,
and JavaScript on launch and works offline.

The standard installation covers Med-PC import, analysis, projects, and both export
formats. If your own scripts use SciPy or h5py, install the optional libraries with
`python -m pip install -e '.[matlab]'`. Trial Cruncher currently supports discovery
of MATLAB files and requires Med-PC text for import.

The top tabs group controls by task. Start in **Import** to add recordings, assign
phases and metadata, and run **Import Med-PC**. **File options…** opens the extension
filter, subfolder setting, and Clear selection. After an import with usable results,
the window advances from Import to **Review**. The **Sessions** table shows File and Quality, followed by the same recording columns as the exported Data sheet. Select a row
for details, then choose **Export results…** for CSV or Excel.
**Project** holds open, save, and source-check controls.

Use the **Split view** selector at the upper right to choose **Batch only** or
**Detail only** for full-height tables. Switching back restores both panes and
keeps the selected recording. In split view, drag the divider to resize either pane.
The app remembers the main window’s position, size, and maximized state between launches.
On Wayland, the compositor controls window placement. The layout mode and split ratio are saved locally. Use arrow keys on the divider
for keyboard resizing. Drag a table header’s right edge to resize its column.
Large batches and decoded choice tables use page controls. **Diagnostics** beneath
a metric table opens its supporting counts and warnings.
**Messages** on the status bar opens the file and project log.

Choose **Add files…** or **Add folder…**. Defaults are `.mat`, `.txt`, `.med`, and `.mpc`;
change the comma-separated extension field for other naming conventions. Extensions
are case-insensitive. They apply to subsequent additions; **Clear selection** and
re-add to filter an existing selection. Folder traversal ignores files with other
extensions. Explicit mismatches, inaccessible paths, and skipped directory symlinks
appear under **Messages**. Symlinked folders must be selected explicitly.

Use **Session metadata…** to assign condition/treatment and study inclusion. Exclusions require a reason; the default is Not reviewed. Save
applies these annotations immediately, including to already reviewed results, without
changing calculations. Excluded recordings remain in exports with their flags.
See [manual analysis metadata](docs/analysis-metadata.md).

Click **Assign phases…** to label each file as Acquisition, Reversal, or a custom
phase (for example, Reversal 2). In either editor, search by source path, then click
individual checkboxes or filenames to build a selection. Shift-click extends a range.
The header checkbox selects all matching recordings across pages.
Choose the phase or metadata value, then click **Apply to selected**. The button shows
the number of selected files. **Apply to all files** is also available. Save, then click **Import Med-PC** to read
the full batch with those assignments. Blank phases leave phase metrics unavailable.
Each file has one fixed contingency under the confirmed no-omission protocol.
Pending phase edits apply only on re-import; exports use the reviewed snapshot. Under **More views → Session diagnostics**, the overview shows one row per file
with subject, program, recorded date, duration, seven metrics, and quality status. Sort
by clicking column headings; combine search, program, and quality filters to find
sessions needing attention. Click a row to review it below:

- **Session details:** identifiers, task duration from `S`, original headers, and provenance.
- **Session metrics:** summary cards above the complete table of five choice/outcome counts, proportion correct, and Med-PC trials
  per minute, with status,
  withholding reasons, and separate recorded-data diagnostics.
- **Phase metrics:** phase accuracy, perseverative/regressive errors, adjusted error
  proportion, and four win-stay/lose-shift probabilities, with criterion and
  numerator/denominator evidence. Undefined ratios remain unavailable.
- **Decoded choices:** source array index, time, correct/rewarded outcome, raw value,
  and source line. Missing decoded values display as **Unavailable**, not zero.
- **Warnings and checks:** per-file problems and saved-count comparisons.
- **Source text:** the read-only original decoded export text.

Quality distinguishes Available, Warnings, Withheld, Unavailable metrics, Failed,
and unimported/pending files. Missing values remain **Unavailable**, withheld metrics
say **Withheld**, and real zeroes stay numeric. A failed file does not stop other imports.
See [batch overview](docs/batch-overview.md) for status meanings and sorting rules.
Unsupported formats/programs, `.MPC` program source, and `._*` sidecars are
reported as failures if included. **Cancel after current file** keeps completed
results and leaves the remaining files unimported. Re-importing re-reads all listed
files and replaces their previous results; **Clear selection** clears the in-memory
review and overview filters. Closing during import cancels remaining files and waits for the current file.

**Overview filters affect the view only: import and export use the full batch.**
The visible/total count makes hidden rows explicit. Dates retain the source header
text and sort as text; no calendar format is inferred.

Choose **More views → Phase results** in the upper batch area to compare behavioral metrics across
sessions. Select **Errors and criterion**, **Win-stay**, **Lose-shift**, **Session rate**, or **All metrics**
to see the relevant values and denominators together. Search or filter by imported
phase/status; click a row for details. Zero denominators remain zero while undefined
ratios say **Unavailable**. See [batch phase results](docs/batch-phase-results.md).

Use **Export results…** to choose CSV or Excel and a parent folder. The application
suggests `YYYYMMDD-trial-cruncher-export-projectname` using the local date and saved
project filename. Unsaved projects use `unsaved`. You can replace the suggestion.
If the name already exists, the app creates a new folder ending in `-2`, `-3`, etc.
The concise Data table contains one row per
successfully imported recording, including rows hidden by filters and recordings
marked Excluded or Not reviewed. Failed and unimported paths appear in the metadata.

Data contains ID, Phase, Treatment, proportion correct, perseverative and regressive
errors, adjusted regressive proportion, four win-stay/lose-shift probabilities, trials
to criterion, and trials per minute. Proportion correct is a fraction from 0 to 1.
Trials to criterion is the ordinal of the choice completing three consecutive correct
choices. Trials/min is the whole-session Med-PC rate using recorded choices and S.

The concise CSV export contains `data.csv`, `trials.csv`, `metadata.csv`, and
`manifest.json`. The Excel export contains `results.xlsx` and `manifest.json`.
Open **Detailed exports** when you need the full versioned tables and animal
analysis tables.

An empty metric means it could not be calculated. A numeric zero is a result.
Metadata records warnings and reasons for unavailable metrics, plus source identifiers
and analysis settings. The source hashes are checked before and after export. Changed
or unavailable sources require re-import.

Discovery never writes to inputs. It does not check content validity or readability
beyond filesystem metadata. Full resolved paths are displayed and may appear in logs;
review logs before sharing them outside the laboratory.

The Excel workbook groups each animal's recorded choices on its own sheet, with
one block per recording. Choice is 1 for a correct choice and 0 for an incorrect
choice. Outcome is 1 for rewarded and 0 for unrewarded. An unknown choice or outcome
stays blank. A Metadata sheet carries the source and calculation details. See
[Excel export and safeguards](docs/excel-export.md).

## Pool animals and compare conditions

Assign a condition, phase, and **Include** to the intended recording for each
animal × condition × phase. Open **Animal analysis…**, choose within- or between-subjects,
and select the conditions and phases. **Apply and preview** shows the pooled
evidence, individual animal values, side-by-side comparisons, and a source audit.
The metric tables group rows by metric by default. Click a column heading for a quick sort,
or open **Sort rules** to set the first sort column and add tie-breakers, each ascending
or descending. Each results table remembers its own rules. Choose **Save project** to
keep the plan and these display preferences between launches. A detailed export with
an enabled plan includes all four analysis tables in their reproducible export order. See [aggregation and pairing](docs/aggregation-pairing-spec.md).

## Save and reopen an analysis

Use **Save project** to store the selected paths, phase assignments, analysis
configuration, source hashes, manual analysis metadata/inclusion, and discovery settings in a `.tcproj.json` file.
**Open project…** restores the setup and reports changed or missing sources. Click
**Import Med-PC** after opening to rebuild results; project files contain setup,
not cached calculations. **Check sources** refreshes source status without importing.
Both exports verify source content and require re-import of changed files.
See [saved projects and source verification](docs/projects.md).

## Testing

```sh
python -m pip install -e '.[test]'
pytest
ruff check .
ruff format --check .
```

Set `TRIAL_CRUNCHER_WEBENGINE_TESTS=1` to include embedded-renderer workflow tests.
GUI tests use Qt's offscreen platform automatically. On Linux without Qt runtime
libraries, install your distribution's EGL/OpenGL packages before running GUI tests
(Ubuntu CI uses `libegl1` and `libopengl0`). See [testing](docs/testing.md).

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
  prl_metrics.py           Approved PRL summaries and strict eligibility diagnostics
  phase_metrics.py         Phase errors/strategies, configuration, and ratio evidence
  projects.py              Validated project setup and atomic local saves
  source_tracking.py       Content fingerprints and stale-source checks
  tables.py                Versioned session/choice table schemas
  exporters.py             Exclusive-create CSV writer and CSV/Excel export bundles
  excel.py                 Literal Excel cells, quality sheet, and provenance chunks
  gui/                     Desktop shell, WebChannel bridge, Qt models and workers
  gui/web/                 Bundled HTML, CSS and JavaScript workspace
tests/                     Synthetic core and offscreen GUI checks
docs/                      Architecture, metric standards, testing
.github/workflows/ci.yml    Python 3.12/3.14 lint and test jobs
```

Animal aggregation and condition pairing are available through **Animal analysis…**. See [architecture](docs/architecture.md) and
[metric conventions](docs/metrics.md).

## Project status and next milestones

1. Expand independent validation beyond the seven supplied partial sessions. Five
   timeouts and two manual stops now pass local consistency checks, with unused
   trailing slots preserved raw under a versioned exclusion rule. See
   [partial-session validation](docs/partial-session-validation.md).
2. Review the seven implemented PRL summaries against additional independent examples.
3. Validate animal-level comparisons on a representative experiment with reviewed treatment assignments.
4. Add broader task configuration and, separately, MAT-derived trials per minute.

Trial Cruncher is released under the [MIT License](LICENSE). Created and maintained by Brandon Oliver.
