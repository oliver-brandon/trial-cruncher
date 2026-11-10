# Batch phase-results comparison

Choose **Phase results** in the upper batch area to compare imported behavioral
metrics across files. **Sessions** retains the original session overview. Both views
use the same imported snapshots and lifecycle state. This adds no calculation,
aggregation, phase assignment, or export schema.

## Comparison layouts

| Layout | Visible evidence |
|---|---|
| Errors and criterion | File, subject, imported phase/status, choices, proportion correct, perseverative/regressive errors, adjusted regressive proportion, its postcriterion denominator, and criterion reached |
| Win-stay | File, subject, phase/status, eligible pair count, and correct/incorrect-conditioned probabilities with separate numerators and denominators |
| Lose-shift | File, subject, phase/status, eligible pair count, and correct/incorrect-conditioned probabilities with separate numerators and denominators |
| Session rate | Whole-session choices, duration S, Med-PC trials/min, and rate status; independent of phase assignment |
| Experiment metadata | Manual condition/treatment, cohort, session order, inclusion and reason beside source identity |
| All metrics | Every metric and ratio count, plus one-based criterion choice ordinal, program, and original date text |

Ratios use 0–1 and display four decimals; sorting uses full stored precision.
Regressive errors supplies the adjusted proportion's numerator; **Postcriterion N
(denominator)** displays its stored denominator. Hover for full values, reasons,
warnings, and source provenance. The criterion ordinal is a choice position, not an
invented trial ID. Full paths distinguish duplicate filenames.

Focused layouts keep source identity beside the relevant counts and values.
**All metrics** may require horizontal scrolling. Resize columns or drag the divider
between the batch area and detailed review to show more rows. Changing phase layouts keeps filters/selection. Switching into or out of Session rate
resets the status filter because it changes from phase status to rate status. If it hides the sort column, sorting returns to File.

## Filters, sorting, and navigation

- **Search** is a case-insensitive literal substring of source path, subject, imported
  phase, program, date text, status, warnings, or reasons. Special characters are
  literal; this is not a numeric-range or regular-expression filter.
- **Phase** uses exact imported labels, including custom labels. **Unassigned phase**
  selects successful imports without a phase; failed/unimported files do not acquire
  guessed labels through this filter.
- **Status** selects availability/lifecycle states. **Needs attention** includes
  warnings, unavailable metrics, unassigned phases, withheld results, failures, stale
  sources, and unimported files. It excludes pending work.

Condition, cohort, and inclusion filters use current manual annotations and combine
with phase/status/search. They affect display only and never select analysis inclusion
or export scope. Filters combine and the visible/total count stays explicit. Reset filters clears
search, phase, and status while retaining the layout and sort. A chosen phase filter
remains selected during re-import even before its new results arrive. Filters are
independent between the upper tabs, are not saved in projects, and reset on Clear
selection or project load.

Counts, ratios, ordinals, and booleans sort by their underlying values. Missing
values stay last in either direction; zero remains numeric and false displays **No**.
Text sorts case-insensitively with full source path breaking ties. Date text is not
parsed or treated as chronological across formats/years.

Click a row or use the keyboard to review that source's phase details below. Switching
upper tabs keeps the reviewed source if it is visible in the destination. Filtering
out the selection clears review. Updates or filters in an inactive tab cannot replace
the active tab's reviewed source.

## Availability and denominators

| Status | Meaning |
|---|---|
| Available | All eight phase values available without source warnings |
| Warnings | All eight values available with retained warnings |
| Some metrics unavailable | Some ratios lack eligible observations; not necessarily a failed import |
| Unavailable metrics | No phase values available, for example an explicitly empty eligible sequence |
| Phase unassigned | Assign a phase and re-import; no phase is inferred |
| Withheld | Existing strict source-integrity policy blocks phase metrics |
| Failed | Import failed; extracted headers may still provide identity |
| Pending / Not imported / Not imported (cancelled) | Explicit lifecycle states without old calculated values |
| Re-import required | Source verification invalidated results; restore/fix and re-import |

A known zero denominator remains **0** while its undefined ratio says **Unavailable**.
A zero numerator with a positive denominator displays genuine `0.0000`. Unknown or
withheld denominators never become zero. Tooltips retain the distinction and reasons.

If criterion was never reached in a nonempty phase, regressive errors and postcriterion
choices are zero, criterion reached is **No**, and adjusted proportion is unavailable.
If criterion was reached on the last choice, the denominator is also zero but criterion
reached is **Yes**. Neither demonstrates postcriterion maintenance. See
[phase definitions](medpc-behavioral-metrics-spec.md).

Phase labels and metric values come from the **last import**, not pending phase edits.
Manual metadata edits apply immediately and remain visible even before import or
after source invalidation; they are not calculated observations. Re-import
applies edits and clears old values before work begins. Cancellation keeps only newly
completed results. Failed re-reads, project loads, and source checks clear affected
values in both views. A stale source may disappear under a phase filter when its
imported phase is invalidated; reset filters to inspect its re-import-required row.

## Full-batch scope and verification

**Filters/layouts change display only. Import and export use the full selected batch.**
CSV `phase_metrics.csv` and Excel's Phase metrics sheet include every successful
import, including hidden rows; manifests account for failed/unimported paths. Source
freshness, strict withholding, raw preservation, and overwrite protection remain in
force. The view does not average or pool results across sessions.

Synthetic model/offscreen GUI tests cover values and ratio counts, all lifecycle and
availability states, full-precision sorting with missing values last, literal filters,
column layouts, actual mouse navigation, duplicate filenames, inactive-tab isolation,
hidden selection clearing, pending phase edits, cancellation/failure, stale sources,
project load, and full-batch import/export under filters.

On November 10, 2026, a local check used the seven supplied recordings with disposable
validation-only phases, not inferred experimental assignments. All 168 checked fields
matched stored results, including 56 metric values and 56 strategy numerator/denominator
counts. The three focused layouts fit at the default window size without horizontal
scrolling and were visually inspected. Filtering to four visible rows still exported
seven phase rows in both formats. Input and summary hashes/mtimes were unchanged.
Artifacts remain under ignored `outputs/batch-phase-validation-*/`. This is
presentation/workflow verification, not new scientific validation or native-dialog testing.

Final verification: **301 tests passed**, along with Ruff lint/format, Markdown link,
and diff whitespace checks. Project loading also resets old cancellation states in
the shared batch model, so the new setup starts explicitly unimported.

## Whole-session rate comparison

**Session rate** reads the separate `prl.medpc_trials_per_minute` session result,
its validated choice count, and duration S. It uses its own rate status, so a missing
phase label does not hide an available rate. Phase and search filters still apply;
status filtering uses rate status only in this layout. Switching into/out of the
layout resets the status filter. Click-through opens Session metrics for the rate;
other layouts continue to open phase details. **All metrics** also includes the
session rate/count/duration/status columns, while its status filter remains phase-based.
The label includes Med-PC and the whole-session scope to avoid suggesting a new
phase rate or the deferred MAT definition. Exported rate values are in Sessions and are copied into Phase metrics with
explicit whole-session labels;
see [rate definition](medpc-trials-per-minute.md).

The inclusion column is visible in the focused comparison layouts. **Experiment
metadata** opens the read-only Analysis metadata detail tab on row selection.
Include/Exclude/Not reviewed is distinct from phase/rate availability, and Include
never overrides strict withholding. Reset filters and project loading also clear the
metadata view filters. See [manual metadata](analysis-metadata.md).
