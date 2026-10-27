# Session and choice CSV export (schema 1)

## GUI workflow

Import files, review the results, then click **Export CSV…** and choose a parent
folder. The application creates a fresh `trial-cruncher-export-<unique suffix>`
subfolder containing `sessions.csv`, `choices.csv`, and `manifest.json`. The saved
folder path is displayed as selectable text above the file list. Export always
includes **all successfully imported sessions in the list**, including those with
warnings, regardless of which file is highlighted. The button is disabled until a
successful import exists, and while discovery, import, or export is active.

Failed and unimported inputs have explicit statuses in the manifest; they are not
represented as successful empty sessions. Cancelling import leaves completed sessions
available for export and records remaining files as `not_imported`. Cancelling the
folder picker writes nothing. Export errors retain the imported results for retry.
Export runs in a background worker, so review stays responsive. Closing waits for
export to finish; an active export cannot be cancelled halfway through.

Exports use the **reviewed in-memory snapshot**. They do not re-read inputs or claim
the recorded hash describes a file subsequently changed on disk. Re-import first
when a newer source version is wanted. Export does not calculate metrics or infer
trial boundaries, trial/session IDs, or task parameters.

## Schemas and provenance

Each CSV has a header even when it has no data rows. Sessions are sorted by source
path; choices retain normalizer order (original Med-PC C-array index, not timestamp).
One imported file currently yields one session. Join choice rows to sessions by
`source_file` and `source_sha256`, not an invented session identifier.

Both tables have these columns:

| Columns | Meaning |
|---|---|
| `schema_version`, `application_version` | Export contract and installed application versions |
| `source_file`, `source_sha256`, `source_file_header` | Local input path, imported byte hash, and original `File:` header |
| `subject_id`, `session_id`, `program` | Source/normalized identifiers; unknown IDs stay missing |
| `reader_version`, `normalizer_version` | Versions responsible for the imported interpretation |
| `time_origin`, `time_unit` | For supported PRL, task start and seconds |
| `warnings_json` | Complete session warnings as a JSON list, repeated on every choice row |

Additional `sessions.csv` columns:

| Column | Meaning |
|---|---|
| `duration_s` | Task duration from `S`; no header-time substitution |
| `head_entries_recorded`, `latency_available` | Availability flags; false does not mean measured zero |
| `summary_checks_json` | Saved-count comparisons: true, false, or null (unavailable) |
| `metadata_json` | Complete session metadata, including raw Med-PC headers, scalars, arrays, source text, line numbers, warnings, and versions |

Additional `choices.csv` columns:

| Columns | Meaning |
|---|---|
| `event_name` | `choice`; these are events, not reconstructed trials |
| `source_array`, `source_index`, `source_line`, `raw_value` | Original array/zero-based index/one-based text line/Decimal value |
| `timestamp_s`, `outcome_code`, `correct`, `rewarded` | Existing normalized meaning, defined in [medpc.md](medpc.md) |
| `raw_values_json`, `attributes_json` | Complete event mappings, separate raw and normalized values |

Invalid choices remain rows, with blank decoded fields and warnings. Sparse indices
are not filled or renumbered. Terminators and values after terminators are not choice
rows, but survive in `metadata_json`. Missing `C`, empty `C`, and a terminated empty
sequence can all yield a header-only choices file; their distinct raw structure and
warnings remain in the session row. No head-entry or latency measurements are added.

## Serialization and limitations

CSV is UTF-8, comma-delimited, with standard double-quote escaping for commas,
quotes, and newlines. Missing scalar observations are empty fields; numerical zero
remains `0`/`0.0`, and booleans are `true` or `false`. An absent identifier is blank,
never filled from a filename. JSON cells use `null` for missing values and preserve
empty strings/collections separately. Decimal values in JSON are strings to avoid
precision loss; integer array indices become JSON object keys (strings). Original
source text preserves lexical formatting beyond parsed Decimal values. Existing
normalized timestamps/durations retain the normalizer's float representation.

CSV has no type schema: a blank scalar field cannot distinguish a missing value from
an empty string. Raw/JSON fields retain that distinction where present. Import CSV
using a text-aware reader and explicitly set identifiers and raw decimal columns to
text when needed; opening CSV directly in spreadsheet software may strip leading
zeros, round values, interpret dates, or treat source text as formulas. Export
preserves source strings verbatim rather than adding prefixes that change them.
For example, Python's `csv.DictReader` preserves `0007` as a string. Large JSON cells
may exceed spreadsheet cell limits; use a CSV/JSON reader for complete provenance.
The files contain original paths, identifiers, and source text: review before sharing.

The manifest records UTC export time, application/Python/dependency versions, row
counts and columns, input statuses/errors/hashes/warnings, scope/order/filtering
rules, and serialization conventions. Reader/normalizer versions and acquisition
configuration are retained per session. There are no metric definitions or analysis
configuration overrides in this milestone; the manifest records an empty metric list.

## Overwrite and failure guarantees

Each export reserves a new directory with an unpredictable unique suffix. CSV files
and the manifest are opened with exclusive creation: existing files, directories,
symlinks (including dangling links), and input paths are refused, never overwritten.
A repeat export creates another folder. The core CSV writer also rejects known input
paths if an input has since been deleted.

Tables and metadata are prepared before creating output files. Ordinary write
failures remove only the new attempt's folder; earlier exports and input files remain
untouched. If cleanup itself fails, the application logs the incomplete folder.
The manifest is written last. Abrupt process termination, machine failure, or failed
cleanup may leave incomplete output; a missing or invalid manifest means the bundle
is incomplete. This is not a crash-durable transaction or an archival backup system.

## Verification

Synthetic tests cover CSV quoting/Unicode, leading-zero IDs, warnings, missing versus
zero/false, invalid and sparse choices, terminators, raw metadata, empty tables,
failed/unimported inputs, repeated exports, source/existing-file/symlink/hard-link
protection, serialization/write failures, and retry. Offscreen GUI tests exercise the
actual button, mocked folder selection, background threads, busy controls, error
recovery, review responsiveness, and deferred close. These verify software behavior,
not scientific validity or native dialogs on every operating system.

On October 27, 2026, an offscreen GUI check exported the four supplied local recordings
to four session rows and 120 choice rows. All source indices/lines/raw values,
timestamps/outcomes, source text/headers, hashes, warnings, and 28 matching saved-count
checks were compared with the imported results. Input hashes and modification times
were unchanged. The completed export screen was visually inspected. Local outputs
remain under ignored `outputs/`; research recordings are not committed as fixtures.
