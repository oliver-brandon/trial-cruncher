# Batch session overview

The batch overview is the file selector above the existing detailed review. It shows
one row per discovered file, including failed and unimported files. It uses the same
imported session and metric snapshot as the detail tabs and CSV export. It does not
calculate new metrics, average sessions, infer identifiers, or change source files.

## Review and navigation

Add files or a folder, then click **Import Med-PC**. The overview updates as each file
finishes. Click a row, or move between rows with the keyboard, to review its source,
metrics, decoded choices, warnings, and checks below. Drag the divider to give the
overview or review more space. Columns can be resized; scroll horizontally to see all
metrics and the warning count on smaller windows.

Rows show filename, quality status, subject, program, recorded Start Date, duration
from `S`, the six approved PRL metrics, and warning count. Hover over a filename to
see its full source path. Hover over quality or metric cells for warnings,
unavailability/withholding reasons, and import errors. Missing raw fields display
**Unavailable**. Subject identifiers keep their original text, including leading zeroes.
Raw headers remain visible for an unsupported program if extraction succeeded.

Selection follows the full resolved source path, not the current row number or
filename. Sorting cannot switch the reviewed source, and identically named files
from different folders remain separate. If a filter hides the selected row, the
detailed review clears; it does not continue showing hidden results. Select another
visible row to resume review. An empty filtered view says **No files match the filters**
and still reports the full batch size.

## Sorting and filtering

Click a column heading to sort; click again to reverse direction. Duration, metric
values, and warning counts sort numerically. Proportion display rounds to four decimal
places, but sorting uses the full calculated value. Unavailable, withheld, and
unimported values sort after known values in either direction; genuine zero remains
a numeric value. Equal sort values use source path as a deterministic tie-breaker.

Filenames, subjects, programs, quality, and dates sort as case-insensitive text.
**Date (source text)** is the original `Start Date` header, not a parsed calendar
date. Text sorting must not be interpreted as chronological ordering across years or
mixed date formats. No date format or session identifier is inferred.

Three filters can be combined; a row must satisfy all of them:

- **Search:** a case-insensitive literal substring of source path, subject, program,
  recorded date, quality, errors, warnings, or withholding reasons. Special characters
  such as brackets are literal, not regular expressions. This is not a numeric range filter.
- **Program:** choose an observed program, including unsupported programs retained in
  raw headers. **Unavailable program** selects rows without a known program.
- **Quality:** choose a status or **Needs attention**. The latter includes warnings,
  withheld/unavailable metrics, failures, and unimported files. Pending files are
  excluded while their import is underway.

**Reset filters** clears all three filters without changing the chosen sort order.
The count beside the filters reports visible rows and total files. A selected program
filter stays selected during re-import even if no current result yet matches it.
These controls affect this window only; no persistent filter configuration is saved.

## Quality and missing values

| Quality | Meaning and cell display |
|---|---|
| Available | All six metrics available and no session warnings; numeric zero remains zero |
| Warnings | All six metrics available, with retained session warnings; for example missing duration or unavailable saved-count cross-checks |
| Withheld | The approved strict rule blocks metrics because of C-index gaps, invalid choices, values after a terminator, or saved-count mismatch; metric cells say **Withheld** |
| Unavailable metrics | At least one metric is unavailable without a structural/count-conflict withholding condition; for example missing C, or an empty eligible sequence with undefined proportion correct |
| Failed | Import did not produce a supported session; metrics say **Unavailable**, and the error remains visible in review and tooltips |
| Not imported | File has not been read; metric/duration/warning-count cells say **Not imported** |
| Pending | File awaits completion in the active import; previous results have been cleared and metric cells say **Pending** |
| Not imported (cancelled) | Import was cancelled before this file; no old values are retained, and metric cells say **Not imported** |

Withholding takes priority over warning status. Unavailable metrics also take priority
over warning status, but all warnings remain visible in tooltips and detailed review.
An empty eligible C has five real zero counts and an **Unavailable** proportion; it
must not look like six missing measurements. Missing C has unavailable values for all
six metrics. The detailed Session metrics tab retains the versioned metric status and
specific reasons; the overview's **Withheld** label is a presentation of the existing
strict policy, not a different calculation or export value. See
[PRL metric definitions](prl-session-metrics.md).

## Import, export, and lifecycle

**Filters change the view only. Import and export use the full batch.** This scope is
stated beside the filters and in button tooltips. Import re-reads all listed files,
including hidden rows. CSV and Excel exports include every successful imported session, with
failed and unimported paths recorded in the manifest. The CSV schema, row order,
missing-value rules, and overwrite protection remain unchanged; displayed **Withheld**
values are still missing numeric values plus attached reasons in CSV schema 4.
See [CSV export](csv-export.md) and [Excel export](excel-export.md).

Sorting, filtering, and detailed review remain available during background work.
Re-import immediately clears old results from every row. Cancellation retains newly
completed results and marks the remaining files unimported. A failed re-read cannot
leave old metrics in the overview or detailed review. **Clear selection** removes the
whole batch, results, and filters. Closing during work uses the existing deferred-close
behavior.

## Verification

Synthetic tests cover quality states, missing versus withheld versus zero, literal
search, combined program/status filters, numeric sorting in both directions with
missing values last, full-precision proportion ordering, duplicate filenames,
click-through to the correct source, clearing hidden/stale review, live filtering and
cancellation, malformed re-reads, and full-batch import/export under an active filter.
The existing offscreen GUI and core suites continue to run. These are software/UI
checks, not scientific validation or native-dialog verification on every OS.

On October 27, 2026, an offscreen GUI check of the four supplied local recordings
verified all four overview rows and 24 metric cells, proportion sorting, source-path
selection, and click-through source review. Filtering to one visible row still
exported all four sessions, including original source text in CSV metadata. Input
hashes and modification times remained unchanged. The overview was visually inspected;
local verification artifacts remain under ignored `outputs/`.

## Source freshness

Project load/save, **Check sources**, and export can invalidate changed, missing,
or unreadable inputs. Those rows remain visible as **Re-import required**, with
reasons in tooltips and cleared stale review/metric values. **Needs attention**
includes them. A fresh import replaces this state with the actual import result.
Source checks do not infer phase labels or silently remove selected paths; see
[projects](projects.md).
