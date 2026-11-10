# Excel export

After importing, click **Export Excel…** and choose a parent folder. A new uniquely
named `trial-cruncher-export-*` folder contains `results.xlsx` and `manifest.json`.
Export runs in the background, and the saved location appears above the overview.
The workbook has five sheets, frozen headers, filters, and formatted numeric cells.

Export uses the full reviewed batch, including rows hidden by overview filters.
Successful imports with warnings or withheld metrics are included. Failed and
unimported files are accounted for. Source hashes are checked before writing and before the completion manifest;
changes or unavailable sources block the attempt and require re-import. Closing during export waits for completion;
errors retain imported results for retry. Cancelling the folder picker writes nothing.

## Sheets and versions

- **Sessions:** one row per successful session, with the same columns and values as
  CSV schema 7: identifiers, duration, seven PRL session metrics, versions, checks, warnings,
  metric statuses/reasons, diagnostics, and original source metadata/text.
- **Choices:** all normalized choice records in source/index order, including invalid
  decoded choices. Source array index, line, exact raw value, time in seconds,
  outcomes, and provenance remain available. An empty sequence produces headers only.
- **Phase metrics:** one row per successful source, with assigned phase, eight
  metrics, criterion evidence, ratio numerators/denominators, undefined flags,
  per-metric reasons, configuration hashes, and source/unused-slot diagnostics.
  It also includes `whole_session_medpc_trials_per_minute`, explicitly copied from
  the whole session, with duration, scope, unit, status/reasons, and original result
  metadata. Missing phase leaves phase metrics unavailable while the session rate
  retains its independent status.
- **Quality:** one `input` row for every selected path, plus seven `metric` rows and eight
  `phase_metric` rows for each successful session. Input rows report `exported`, `failed`, or `not_imported`,
  hash, error, and warnings. Metric rows add the existing value, unit, availability
  status, reasons, definition version, and eligibility policy. Withheld metrics retain
  their defined `unavailable` status and explicit withholding reasons. This sheet
  introduces no new metric definitions or quality calculations.
- **Provenance:** numbered text chunks containing the complete manifest and any text
  that exceeds the workbook's per-cell storage budget. It uses the columns `kind`,
  `sheet`, `cell`, `part`, `parts`, and `text`.

The workbook layout is version **6** (`workbook_schema_version`), and the shared
session/choice/phase table schema is version **7** (`schema_version`). `manifest.json` records runtime
versions, metric definitions/policy, UTC export time, input outcomes, table columns
and row counts, ordering, and Excel serialization rules. The same manifest is embedded
in Provenance so the workbook can be interpreted independently of the companion file.

## Values and complete provenance

Missing and withheld numeric values are blank. Zero is numeric zero; booleans are
native true/false values. Reasons and raw JSON distinguish absent measurements from
genuine zero counts. Empty source strings can also appear blank; raw JSON preserves
the distinction where recorded. No calculated values are replaced with zero.

Identifiers, raw Decimal acquisition values, source dates, JSON, and other strings
are explicitly stored as literal text. Leading zeroes and Decimal trailing zeroes
are preserved. Strings beginning with `=`, `+`, `-`, or `@`, and strings such as
`#N/A`, remain text; the exporter creates no formulas or external links.
Integers longer than 15 digits are stored as exact text. Other counts, normalized
times, and calculated proportions are numeric. Excel's numeric precision applies to
floating-point cells; original acquisition values and metric JSON remain available.
Proportion correct uses a **0–1** numeric value and four-decimal display format,
with no percentage formatting or percent suffix. Formatting does not change the value.

To prevent silent truncation, text is split at 30,000 UTF-16 code units or 250 line
feeds per chunk. A long cell displays `[Full text: Provenance rows N-M]`. Filter
Provenance to `kind=overflow` and the original `sheet` and `cell`, order by `part`,
then concatenate `text` **without separators** to reconstruct the exact value.
For the manifest, concatenate `kind=manifest` chunks in `part` order. Sheet/cell
coordinates refer to the workbook as exported; Excel sorting or edits do not update
these references. Keep an unedited export for reproducibility.

JSON strings are split as text, not parsed into partial JSON documents. Parse them
only after concatenation. Text that cannot be represented in XML is rejected with
its sheet/cell location; no characters are silently removed. Worksheet row/column
limits are checked, including Provenance chunks. If exceeded, use CSV export.
Very large workbooks require memory for both the tables and workbook cells.

Metadata columns may require horizontal scrolling or the formula bar for detailed
reading. The workbook contains source paths, identifiers, and original source text;
review it before sharing outside the laboratory.

## Overwrite and failure safeguards

As with CSV, every export reserves a fresh folder. The workbook and manifest use
exclusive creation. Existing files, directories, symlinks (including dangling links),
hard links, and known source paths cannot be replaced. Repeated exports create
separate folders. Tables and the workbook are prepared and validated before the
folder is created. Ordinary write failures remove only that attempt's folder;
earlier exports and inputs remain untouched. A cleanup failure is logged.

The manifest is written last as the bundle completion marker. Abrupt termination,
machine failure, or failed cleanup can leave incomplete output. A missing or invalid
manifest means the bundle is incomplete; this is not a crash-durable transaction.

## Verification

Synthetic tests reload the saved workbook and compare values, types, provenance,
statuses, and reasons with the imported snapshot. They cover invalid/missing/empty
choices, zero/false, saved-count conflicts, sparse/terminated arrays, failed/unimported
inputs, literal formula-like text, precision, long Unicode metadata, line feeds,
worksheet limits, invalid XML, write failure cleanup, repeated exports, and source/link
protection. Offscreen GUI checks cover folder cancellation, background work, busy
controls, review responsiveness, failure/retry, deferred close, and exporting all
successful sessions while filters hide rows. These are software checks, not scientific
validation or proof of native Microsoft Excel rendering on every operating system.

On November 4, 2026, the full suite passed **169 tests**, Ruff lint/format checks,
and dependency consistency checks. An offscreen GUI export of the four supplied
local recordings produced 4 session rows, 120 choice rows, and 28 quality rows while
the overview showed only one session. All 2,996 session/choice cells were compared
against the reviewed snapshot (floating-point comparisons used numerical tolerance),
including source text and metadata. The embedded and companion manifests matched;
source SHA-256 hashes and modification times were unchanged. The completed GUI was
visually inspected. Verification outputs remain in ignored `outputs/`; no research
recordings were added as test fixtures. Native Microsoft Excel rendering was not
tested in this environment, and partial-session scientific validation remains open.

The string handling safeguards account for the library's documented
[string length and inferred cell type behavior](https://openpyxl.readthedocs.io/en/stable/_modules/openpyxl/cell/cell.html).

Normalizer/metric definition version 2 recognizes corroborated unused zero tails.
Those slots remain in full raw session metadata (including Provenance chunks when
needed) and carry explicit excluded indices/counts. Choices contains recorded events
only; metric diagnostics distinguish raw entries and unused slots. The manifest
records the storage policy. The initial unused-slot change retained workbook layout 1/table schema 2;
phase metrics first extended them to workbook layout 2/table schema 3.
The proportion-scale change used workbook layout 3/table schema 4; current rates
use workbook layout 4/table schema 5. See [unused-slot interpretation](prl-unused-slots.md).

Phase assignments are saved for the next import, never inferred. Re-import to apply
assignment edits; export uses the phase in the reviewed snapshot. Phase probabilities
and adjusted regressive errors remain 0–1 values; proportion correct is also 0–1.
Blank values, zero numerators/denominators, and undefined flags preserve distinct
meaning. Source strings and custom phase labels are literal text. Choices gains
phase, error-classification, and criterion-completed annotations; see
[CSV schema 7](csv-export.md) and [phase definitions](medpc-behavioral-metrics-spec.md).

Saved projects restore file/phase setup and compatible analysis configuration. They
require a new import before export and retain reference hashes for detecting changed
sources. See [projects and source verification](projects.md).

Workbook layout 3 introduced schema 4 and explicit proportion-correct IDs.
Session definition version 3 and phase definition version 2 identify the changed
scale. See [accuracy scale migration](proportion-correct.md).

Workbook layout 4 / table schema 5 adds whole-session Med-PC trials per minute to
Sessions and its Quality metric rows. The value is a plain numeric choices/min
rate (not a proportion); recorded choices and duration_s provide its inputs. Missing
or invalid rate values stay blank with reasons. Layout 5 also copies it into Phase metrics, explicitly labeled as whole-session data.
See [Med-PC trials per minute](medpc-trials-per-minute.md).

In workbook layout 6/table schema 7, the numeric copy is column **AY** on **Phase
metrics**, headed `whole_session_medpc_trials_per_minute`. Its width is expanded for
the explicit label, and it remains a plain numeric choices/min value. Sessions
continues to contain `prl.medpc_trials_per_minute`; Quality records the session rate
once, not as a ninth phase metric. See [the copied field contract](csv-export.md).

Workbook layout 6 adds manual analysis metadata to Sessions, Choices, Phase metrics,
and Quality. Inclusion is a native boolean (false is Excluded) with blank for Not
reviewed and a separate readable status; session order is an integer, not an inferred
date or session ID. Text labels/reasons remain literal, and long reasons use the
existing provenance overflow mechanism. Every successful recording is retained
regardless of inclusion; no metrics are rewritten or suppressed by the manual flag.
See [manual metadata](analysis-metadata.md).
