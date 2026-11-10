# Architecture

## Proposed processing pipeline

```text
Selected paths → discovery → format detection/readers → normalization
              → explicit paradigm/configuration → metrics → tables → exporters
```

Discovery, selection, Med-PC text extraction, and normalization of three confirmed PRL
programs are implemented, along with session/choice table builders and CSV/Excel export.
Six PRL session-summary calculations and eight phase behavioral metrics are
implemented with strict withholding. User-assigned phases follow the confirmed
fixed-contingency/no-omission profile. Further metric families remain future work. The Med-PC reader is exposed through Python, `--inspect-medpc`, and GUI
import review with per-file results.

## Current components

`discovery.py` accepts files or directories, extensions, and recursion settings and
returns sorted unique absolute paths plus per-path issues. It reads filesystem
metadata only. Unmatched files inside folders are intentionally filtered. Explicit
unsupported files and inaccessible paths are reported. Directory symlinks encountered
within a traversal are reported and skipped; explicit roots resolve to their targets.

`models.py` provides `Session`, `Event`, and optional `Trial` collections. A session
retains its source file, subject/session IDs when known, metadata, and warnings.
Events use seconds relative to an origin documented by the normalizer in metadata.
Normalized semantic fields belong in `Event.attributes`, separate from original
`raw_values`; neither is a calculated behavioral metric. `Session.duration_s` is
optional and uses an explicit source definition, not a guessed header-time difference.
Raw source fields remain separate from `MetricResult`. Missing values use `None`;
empty trial collections support continuous or response-based sessions. A reader may
contain multiple sessions, so normalization returns a sequence (the initial Med-PC
reader supports one session per file). These records are containers; validation is
performed by readers and normalizers.
Frozen dataclasses are shallow and callers must treat their mappings as read-only.

`readers.py` defines the detection/extraction contract. `medpc.py` implements raw
extraction, retaining Decimal values, original array indices, text, file hash, and
line provenance. `normalization.py` defines the canonical conversion contract;
`prl.py` interprets the three confirmed program names without importing Qt, preserves raw
data, and reports invalid choices and saved-count inconsistencies. Normalizer version 2
recognizes fully corroborated unused zero tails without changing raw arrays. Its
`choice_storage_info()` helper is also used by the metric calculator to recheck
exclusions and reject stale storage metadata; see [unused slots](prl-unused-slots.md). See
[the Med-PC specification](medpc.md) for supported encodings and missing-data policy.
`paradigms.py` carries a named, versioned
configuration without assuming automatic task identification. `metrics.py` defines
the extensible metric contract. `prl_metrics.py` implements the six approved PRL
summaries under a fixed, versioned eligibility policy, without configurable overrides.
It consumes canonical choices and structured source/normalizer facts, returning
`MetricResult` values and separate diagnostics. Values never replace raw observations;
missing values carry reasons and availability status. `phase_metrics.py` calculates the phase-specific error/strategy definitions and
retains criterion, ratio, and configuration evidence separately from the session
summary. It rechecks source integrity before processing choice order.
`tables.py` builds versioned
session, choice, and phase pandas tables with object dtype to preserve optional integers.
`exporters.py` implements the exporter protocol with an exclusive-create CSV writer
and orchestrates new export bundles with a manifest. See [CSV export](csv-export.md)
and [Excel export](excel-export.md).

`processing.py` provides `ImportResult` and `import_medpc_file()`, independent of Qt.
It calculates the PRL summary after normalization and retains it in `ImportResult`,
so GUI/export use the same result. `ImportResult.phase_summary` additionally stores
the phase calculation and immutable, hashed configuration from import time. Expected read/normalization/calculation failures
become explicit errors; raw extraction survives
an unsupported program so its headers and source text can still be inspected.

`gui/` runs discovery, imports, and export in separate `QRunnable` jobs. The import worker
loops over a snapshot of selected paths, sends per-file results/progress, isolates
unexpected failures, and checks a cancellation event between files. Selection changes
and re-import controls are disabled while busy, but existing results remain browsable.
Re-import replaces previous results before starting, so failed re-reads cannot display
stale choices. Cancellation retains completed results. Close requests defer destruction
until the worker finishes; discovery and export are not cancellable, and a single file read is
not interruptible. No worker touches widgets or the choice table model.

`gui/overview.py` supplies a read-only `QAbstractTableModel` of per-file imported
snapshots and lifecycle states, plus a sorting/filtering proxy. Only GUI-thread
signal handlers update its rows. Typed numeric sorting uses unrounded values and
places missing values last in both directions; source date/ID strings stay textual.
Quality comes from structured summary diagnostics and existing availability/warnings,
not warning-text parsing or new calculations. Proxy rows carry full source paths so
sorting and duplicate filenames cannot misdirect the review. Filtering out a selected
source clears the review. Import/export operate on the authoritative complete path
set, never on proxy-visible rows. The model clears stale values at re-import start
and retains explicit cancelled/failed states. See [batch overview](batch-overview.md).

`gui/review.py` presents read-only details, source text, warnings/checks, and a
`QAbstractTableModel` backed by canonical events. The model is updated only on the
GUI thread via signal handlers, following Qt's
[table-model threading contract](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractTableModel.html).
Original array order and unavailable values remain visible. Text from files is
displayed as plain text, never rendered as HTML. Results are held in memory and are
not automatically persisted. The export worker receives a snapshot of import results
and selected paths; its signals report success or failure without manipulating widgets.
Export disables selection/import controls and retains the reviewed results on failure.

The CLI loads Qt only for `--gui`. Core imports do not initialize the GUI or logging.
Application logs are JSON records on standard error; discovery issues are also visible
in the window. This skeleton does not yet persist logs to disk.

## Next components and extension boundaries

Extend `processing.py` when additional configurable metric analysis is implemented. Keep orchestration
independent of Qt and preserve per-input success/failure records. Do not represent a
failed file as a successful empty dataset. GUI imports currently process files serially
in one worker; parallel analysis and persistent result caching are not implemented.

`gui/phases.py` provides a full-path per-file assignment dialog with custom/bulk labels.
Assignments are in-memory pending import configuration. ImportWorker copies the
mapping before work starts; phase editing is disabled during background operations.
A cancelled/failed re-import cannot retain old phase results. The phase review tab
shows its own availability, criterion evidence, and ratio counts without overwriting
the existing session summary status.

Extend `tables.py` for future trial, subject, and group row levels. Session and choice
rows already carry direct source provenance; aggregated rows will require explicit
lineage listing every contributing source. Do not fabricate trials for non-trial tasks.

The current export manifest records software versions, source status/hash/warnings,
scope and serialization rules. Per-session metadata retains reader/normalizer versions,
raw acquisition fields, and time units/origin. Schema 2 adds the six calculated
session columns and their status/reasons/diagnostics; the manifest records metric
definition IDs/versions and the strict withholding policy. Excel workbook layout
version 2 uses schema 3 tables, including Phase metrics, Quality, and
Provenance sheets. Phase configurations and definitions are recorded independently
of the existing session definitions. `excel.py` stores literal text, chunks long metadata, checks
worksheet/XML limits, and exclusively creates `results.xlsx`; the shared export
orchestrator writes its manifest last and cleans up failed attempts.
Future metrics must record their definitions and complete analysis configuration.
Future formats and row levels must retain missing-versus-zero
distinctions and input/overwrite protection.

For a new format, implement `Reader` and `Normalizer` using documented, de-identified
examples. Handle classic MATLAB with SciPy and MATLAB v7.3 with h5py only after its
actual nested layout/references are established. Med-PC exports similarly need a
documented dialect. The initial supported dialect is described in `medpc.md`;
additional dialects require their own examples. Fail clearly on unsupported structures
and ambiguous detection.

For a new task, add explicit configuration validation and metric implementations,
documented under `docs/metrics.md`. Version formulas and definitions separately from
package releases when semantics change. Start with an explicit mapping of available
implementations; use a plugin registry only if genuine extension needs emerge.

The separation allows future GUI, CLI, and programmatic clients to share the same
engine without importing GUI dependencies into calculations.
