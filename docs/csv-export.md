# Session, choice, and phase CSV export (schema 5)

## GUI workflow

Import files, review the results, then click **Export CSV…** and choose a parent
folder. The application creates a fresh `trial-cruncher-export-<unique suffix>`
subfolder containing `sessions.csv`, `choices.csv`, `phase_metrics.csv`, and `manifest.json`. The saved
folder path is displayed as selectable text above the overview. Export always
includes **all successfully imported sessions in the list**, including those with
warnings, regardless of which file is highlighted or hidden by overview filters. Sorting and
filtering change only the GUI view; the visible/total file count states that import
and export use the full batch. The button is disabled until a
successful import exists, and while discovery, import, or export is active.

Failed and unimported inputs have explicit statuses in the manifest; they are not
represented as successful empty sessions. Cancelling import leaves completed sessions
available for export and records remaining files as `not_imported`. Cancelling the
folder picker writes nothing. Export errors retain the imported results for retry.
Export runs in a background worker, so review stays responsive. Closing waits for
export to finish; an active export cannot be cancelled halfway through.

Exports use the **reviewed in-memory snapshot**, with current source hashes verified
before writing and again before the completion manifest. Changed, missing, unreadable,
or unstable imported sources block that export attempt and require re-import. No new
metric values are calculated during export. The GUI clears affected stale results;
other successfully imported sources remain available. See [source verification](projects.md).
Missing/stale interpretation versions also require re-import. Original source data
is never overwritten, and phase labels come from the reviewed import snapshot.

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
| `prl.choice_count`, `prl.correct_choice_count`, `prl.incorrect_choice_count` | Calculated recorded/correct/incorrect choice counts |
| `prl.rewarded_choice_count`, `prl.unrewarded_choice_count`, `prl.proportion_correct` | Calculated outcome counts and proportion correct using recorded choices |
| `metric_definition_set`, `metric_definition_version`, `metric_policy` | `prl-session-summary`, `3`, and `strict-withholding-v2` |
| `metric_results_json` | All seven results: stable name, definition version, numeric value or null, unit, availability status, reasons, and warnings |
| `metric_diagnostics_json` | C presence, terminator observation, observed/decoded/invalid record counts, post-terminator entries, index gaps, and saved-count checks |

The seven calculated columns follow [the approved definitions](prl-session-metrics.md).
Strict withholding leaves all seven blank for incomplete/invalid C or a saved-count
mismatch; raw choices and diagnostic counts are retained. Explicit empty eligible C
has five zero counts and a blank proportion, while missing C gives seven blank values.
Availability reasons stay in `metric_results_json`. GUI proportion rounding does not
affect CSV precision. Saved `A[5]` remains raw and separate.

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
configuration are retained per session. The manifest lists all seven metric IDs, units,
definition version, definition set, strict eligibility policy, and the recorded-choice
proportion denominator. There are no user-configurable policy overrides. Schema 2
extends schema 1 with the calculated session columns and metric metadata; choice
columns are unchanged apart from their bundle schema-version value.

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

Excel export is also available with the same session/choice schema and a dedicated
Quality sheet, literal text cells, and complete provenance chunks. See
[Excel export](excel-export.md) for its distinct serialization rules.

Normalizer and metric definition version 2 recognize fully corroborated unused trailing
slots ([rule](prl-unused-slots.md)). Choices contain only recorded events; Sessions
`metadata_json` retains every raw slot and its source line, plus `choice_storage` with
the policy, raw count, excluded count, and excluded indices. `metric_diagnostics_json`
reports raw entries and unused slots separately from choice counts. The manifest
records `choice_storage_policy=validated-zero-tail-v1`. These storage additions were introduced with schema 2; schema 3 retains them
and adds the phase table and choice annotations described below.

## Phase results (introduced in schema 3)

Use **Assign phases…** before importing. Assignments are per source path and may use
custom labels. An empty label is not inferred from filenames: all eight phase
metrics are unavailable until assigned and re-imported. Session summaries retain
their separate eligibility/status. Saving a pending phase edit never changes an
already reviewed export snapshot.

`phase_metrics.csv` has one row per successful source, even if phase is unassigned
or metrics are withheld. It retains the shared source provenance columns, phase
label/status, the eight `prl.phase.*` values, configuration JSON/SHA-256, definition
set/version/policy, recorded/correct/incorrect choice counts, whole-session count,
criterion reached and one-based choice ordinal/zero-based C index, postcriterion
count, adjusted-error numerator/denominator, and all four strategy numerator,
denominator, and undefined flags. `metric_results_json` and
`metric_reason_codes_json` preserve per-value status/reasons; raw source diagnostics
and unused-slot metadata are separate. `omission_count=0` is explicitly labeled as
an owner-confirmed protocol assertion, not a measurement from cues.

`choices.csv` gains `phase`, `phase_error_classification`, and
`phase_criterion_completed_here`. Classification is `correct`, `perseverative`, or
`regressive` only for eligible assigned phases; otherwise it is blank. The criterion
flag is true only on the choice completing the first run of three correct choices,
false on other eligible choices, and blank when classification is unavailable.
Original C indices and raw observations are unchanged.

The manifest adds the phase definition set/version, metric IDs, strict policy, and
per-source configuration snapshots/hashes. Technical source identity is the existing
pair `(source_file, source_sha256)`; biological IDs are never invented. The new
phase set is version 2; session summaries use definition version 4. Export rejects
missing or stale phase results/configuration/provenance before creating files.

Probability/adjusted proportion scales are 0–1; phase accuracy is also a 0–1 proportion.
Known zero denominators retain zero and an undefined flag, while withheld denominators
stay blank with a missing flag. Neither becomes a fabricated zero probability.
The phase table does not invent a phase-specific rate. The whole-session Med-PC
rate is in Sessions, and the separate MAT rate remains deferred. See the
[phase specification](medpc-behavioral-metrics-spec.md) for formulas and examples.

Schema 4 replaces percentage columns with `prl.proportion_correct` and
`prl.phase.proportion_correct`, with unit `proportion` and range 0–1. Old percentage
exports retain their original scale and filenames; they are never rewritten. See
[accuracy scale migration](proportion-correct.md).

## Med-PC session rate in schema 5

Sessions gains `prl.medpc_trials_per_minute` (choices/min), with recorded choices
in `prl.choice_count` and duration in `duration_s` from S. It is calculated as
`60 * choices / S`, including waiting/timeouts. Source A[3] remains raw and may differ
because it was rounded or not finalized. Definition set version 4 and the manifest
record the formula, whole-session scope, source, unit, availability, and reasons.
Invalid duration or a choice beyond S makes the rate blank without withholding
otherwise eligible choice/phase metrics. See [rate definition](medpc-trials-per-minute.md).
