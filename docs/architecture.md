# Architecture

## Proposed processing pipeline

```text
Selected paths → discovery → format detection/readers → normalization
              → explicit paradigm/configuration → metrics → tables → exporters
```

Discovery and selection are implemented. Reader/normalizer/metric/exporter protocols
are contracts only. There are no shipped parsers, analysis algorithms, batch analysis
runners, table builders, or export writers.

## Current components

`discovery.py` accepts files or directories, extensions, and recursion settings and
returns sorted unique absolute paths plus per-path issues. It reads filesystem
metadata only. Unmatched files inside folders are intentionally filtered. Explicit
unsupported files and inaccessible paths are reported. Directory symlinks encountered
within a traversal are reported and skipped; explicit roots resolve to their targets.

`models.py` provides `Session`, `Event`, and optional `Trial` collections. A session
retains its source file, subject/session IDs when known, metadata, and warnings.
Events use seconds relative to an origin documented by the normalizer in metadata.
Raw source fields remain separate from `MetricResult`. Missing values use `None`;
empty trial collections support continuous or response-based sessions. A reader may
contain multiple sessions, so normalization returns a sequence. These records are
initial contracts to refine with real examples; they do not validate a schema.
Frozen dataclasses are shallow and callers must treat their mappings as read-only.

`readers.py` separates content detection from extraction. `normalization.py` separates
source conventions from canonical records. `paradigms.py` carries a named, versioned
configuration without assuming automatic task identification. `metrics.py` consumes
canonical sessions and explicit task configuration. `exporters.py` accepts a pandas
table and destination; future implementations must guard inputs and existing files.

`gui/` invokes discovery through a `QRunnable` on a thread pool. Signals return results
to the UI thread. Selection controls are disabled during each discovery job, existing
selections survive errors, and issues remain visible until cleared. The initial
worker has no progress or cancellation interface. Application shutdown may wait for
ongoing traversal. Future long-running batch execution needs cancellation and progress
before it is exposed in the UI.

The CLI loads Qt only for `--gui`. Core imports do not initialize the GUI or logging.
Application logs are JSON records on standard error; discovery issues are also visible
in the window. This skeleton does not yet persist logs to disk.

## Next components and extension boundaries

Add `processing.py` when the first real reader/normalizer/metric chain exists. It
should orchestrate independent files, retain one explicit success/failure record per
input, continue after recoverable errors, and accept progress/cancellation callbacks
without importing Qt. Do not represent a failed file as a successful empty dataset.

Add `tables.py` with real output schemas. Support explicitly selected row levels:
trial, session, subject, and eventually group. Every exported row must retain
provenance. Trial/session rows can reference source file and source IDs directly;
aggregated rows require a stable row ID linked to a separate lineage table listing
all contributing source files/sessions. Do not fabricate trials for non-trial tasks.

An export manifest should capture source hashes, parser/normalizer versions,
application and dependency versions, paradigm/metric definition versions, complete
configuration, time origins/units, filtering rules, missing-data conventions, and
warnings. Neither hashing nor manifests are implemented yet. CSV and Excel exporters
should preserve missing-versus-zero distinctions and reject input paths or existing
destinations. Document format limitations rather than silently changing values.

For a new format, implement `Reader` and `Normalizer` using documented, de-identified
examples. Handle classic MATLAB with SciPy and MATLAB v7.3 with h5py only after its
actual nested layout/references are established. Med-PC exports similarly need a
documented dialect. Fail clearly on unsupported structures and ambiguous detection.

For a new task, add explicit configuration validation and metric implementations,
documented under `docs/metrics.md`. Version formulas and definitions separately from
package releases when semantics change. Start with an explicit mapping of available
implementations; use a plugin registry only if genuine extension needs emerge.

The separation allows future GUI, CLI, and programmatic clients to share the same
engine without importing GUI dependencies into calculations.
