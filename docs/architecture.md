# Architecture

## Proposed processing pipeline

```text
Selected paths → discovery → format detection/readers → normalization
              → explicit paradigm/configuration → metrics → tables → exporters
```

Discovery, selection, Med-PC text extraction, and normalization of two confirmed PRL
programs are implemented, along with session/choice table builders and CSV export.
The metric protocol remains a contract only; there are no behavioral metric algorithms
or batch analysis runners. The Med-PC reader is exposed through Python, `--inspect-medpc`, and GUI
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
`prl.py` interprets the two confirmed programs without importing Qt, preserves raw
data, and reports invalid choices and saved-count inconsistencies. See
[the Med-PC specification](medpc.md) for supported encodings and missing-data policy.
`paradigms.py` carries a named, versioned
configuration without assuming automatic task identification. `metrics.py` consumes
canonical sessions and explicit task configuration. `tables.py` builds versioned
session and choice pandas tables with object dtype to preserve optional integers.
`exporters.py` implements the exporter protocol with an exclusive-create CSV writer
and orchestrates new export bundles with a manifest. See [CSV export](csv-export.md).

`processing.py` provides `ImportResult` and `import_medpc_file()`, independent of Qt.
Expected read/normalization failures become explicit errors; raw extraction survives
an unsupported program so its headers and source text can still be inspected.

`gui/` runs discovery, imports, and export in separate `QRunnable` jobs. The import worker
loops over a snapshot of selected paths, sends per-file results/progress, isolates
unexpected failures, and checks a cancellation event between files. Selection changes
and re-import controls are disabled while busy, but existing results remain browsable.
Re-import replaces previous results before starting, so failed re-reads cannot display
stale choices. Cancellation retains completed results. Close requests defer destruction
until the worker finishes; discovery and export are not cancellable, and a single file read is
not interruptible. No worker touches widgets or the choice table model.

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

Extend `processing.py` when batch metric analysis is implemented. Keep orchestration
independent of Qt and preserve per-input success/failure records. Do not represent a
failed file as a successful empty dataset. GUI imports currently process files serially
in one worker; parallel analysis and persistent result caching are not implemented.

Extend `tables.py` for future trial, subject, and group row levels. Session and choice
rows already carry direct source provenance; aggregated rows will require explicit
lineage listing every contributing source. Do not fabricate trials for non-trial tasks.

The current export manifest records software versions, source status/hash/warnings,
scope and serialization rules. Per-session metadata retains reader/normalizer versions,
raw acquisition fields, and time units/origin. Future metric exports must additionally
record versioned metric definitions and complete analysis configuration. Excel export
is not implemented. Both future formats and row levels must retain missing-versus-zero
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
