# Excel export

After importing, click **Export Excel…** and choose a parent folder. A new uniquely
named `trial-cruncher-export-*` folder contains `results.xlsx` and `manifest.json`.
Export runs in the background, and the saved location appears above the overview.
The workbook has four sheets, frozen headers, filters, and formatted numeric cells.

Export uses the full reviewed batch, including rows hidden by overview filters.
Successful imports with warnings or withheld metrics are included. Failed and
unimported files are accounted for. The source files are not re-read: re-import to
reflect changes made since review. Closing during export waits for completion;
errors retain imported results for retry. Cancelling the folder picker writes nothing.

## Sheets and versions

- **Sessions:** one row per successful session, with the same columns and values as
  CSV schema 2: identifiers, duration, six PRL metrics, versions, checks, warnings,
  metric statuses/reasons, diagnostics, and original source metadata/text.
- **Choices:** all normalized choice records in source/index order, including invalid
  decoded choices. Source array index, line, exact raw value, time in seconds,
  outcomes, and provenance remain available. An empty sequence produces headers only.
- **Quality:** one `input` row for every selected path, plus six `metric` rows for
  each successful session. Input rows report `exported`, `failed`, or `not_imported`,
  hash, error, and warnings. Metric rows add the existing value, unit, availability
  status, reasons, definition version, and eligibility policy. Withheld metrics retain
  their defined `unavailable` status and explicit withholding reasons. This sheet
  introduces no new metric definitions or quality calculations.
- **Provenance:** numbered text chunks containing the complete manifest and any text
  that exceeds the workbook's per-cell storage budget. It uses the columns `kind`,
  `sheet`, `cell`, `part`, `parts`, and `text`.

The workbook layout is version **1** (`workbook_schema_version`). Shared session and
choice tables remain version **2** (`schema_version`). `manifest.json` records runtime
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
times, and calculated percentages are numeric. Excel's numeric precision applies to
floating-point cells; original acquisition values and metric JSON remain available.
Percent correct retains its **0–100** value and displays a literal percent suffix,
not Excel's fraction-based percentage format. Formatting does not change the value.

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
