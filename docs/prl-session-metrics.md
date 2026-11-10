# PRL session-summary metrics — definition version 4

Status: **Approved by the project owner and implemented.**
Definition set: `prl-session-summary`, version `4`.
Eligibility policy: `strict-withholding-v2`.
Approval: October 27, 2026, for the original formulas and strict withholding;
November 4, 2026, for recognizing confirmed unused trailing slots while preserving raw data. This
approval is not a claim of independent scientific validation.

This definition set specifies seven session-level metrics for the owner-confirmed
`PRL_BO`, `PRL_OPTO`, and `PRL_OPTO_CORSTIM` interpretations documented in [medpc.md](medpc.md), using
reader version `1` and normalizer version `2`. Program names alone do not establish compatibility
with future acquisition-code revisions. The definitions below are specific to this project,
not claims of universally accepted PRL definitions or scientific validation.

## Scope and meaning

Summarize the choices recorded in one imported session. A choice is an event in the
source `C` array, not a reconstructed trial. Correctness and reward are the program's
encoded outcomes. A rewarded choice does not establish physical pellet delivery or
retrieval. Correct and rewarded are separate properties: an incorrect choice may be
rewarded and a correct choice may be unrewarded.

The metrics describe the recorded session, including an early-stopped session with
an intact choice record. They do not establish that the intended protocol finished,
that all behavior was captured, or why the session ended. No minimum choice count,
fixed trial target, reversal location, or schedule is assumed.

Task duration remains the existing extracted `duration_s` from `S`, in seconds from
task start. It is not a new calculation in this milestone. Header elapsed time is
not substituted. Head entries, latencies, omissions, aborted-trial counts, choice
MAT-derived rates, win-stay/lose-shift, reversal metrics, and subject/group aggregates are outside
this definition set.

## Metric definitions

For an eligible session, let `n1`, `n2`, `n6`, and `n7` be the numbers of decoded
choice events with outcome codes 1, 2, 6, and 7. These codes respectively mean
correct/rewarded, correct/unrewarded, incorrect/rewarded, and incorrect/unrewarded.
Let `N = n1 + n2 + n6 + n7`.

All seven definitions use definition version `4`. The first six use the common
choice-record eligibility below; the Med-PC rate additionally requires valid duration
and time bounds, as specified in [Med-PC trials per minute](medpc-trials-per-minute.md). Each output has row level **session**. Counts are nonnegative integers with unit
`count`; proportion has unit `proportion` and range 0–1 inclusive.

| Stable identifier | Display name | Formula | Interpretation |
|---|---|---|---|
| `prl.choice_count` | Recorded choices | `N` | Choices represented by the eligible recorded sequence |
| `prl.correct_choice_count` | Correct choices | `n1 + n2` | Choices encoded as correct |
| `prl.incorrect_choice_count` | Incorrect choices | `n6 + n7` | Choices encoded as incorrect |
| `prl.rewarded_choice_count` | Rewarded choices | `n1 + n6` | Choices encoded with a reward outcome |
| `prl.unrewarded_choice_count` | Unrewarded choices | `n2 + n7` | Choices encoded without a reward outcome |
| `prl.proportion_correct` | Proportion correct | `(n1 + n2) / N`, for `N > 0` | Correct choices as a proportion of recorded choices |
| `prl.medpc_trials_per_minute` | Trials/min (Med-PC) | `60 * N / S`, for finite positive S | Whole-session completed-choice rate, including waiting/timeouts; unit choices/min |

The proportion-correct denominator is **recorded choices**, not the configured maximum
`Y`, elapsed time, rewards, or a guessed number of trials. Saved `A[5]` remains a raw
source value with its documented `A[0] / Y` meaning. It is neither substituted for
nor renamed as `prl.proportion_correct`. No intermediate rounding is allowed; display
rounding must not change exported calculation precision.

## Eligibility and missing-data rules

Approved policy: **do not silently calculate standard session metrics from a
valid subset of a damaged or conflicting choice record.** All five counts and the
proportion share the same choice-record eligibility rule. Diagnostic counts remain
available separately where they can be observed reliably.

Version 2 first identifies unused trailing slots under the fully corroborated
[storage rule](prl-unused-slots.md). Those slots remain raw but are not choices.
A sequence is eligible when `C` is explicitly present, its printed indices are
contiguous from zero, every non-padding entry before the first exact `-987.987` terminator is
decoded by the confirmed normalizer, no values follow that terminator, and no
available saved-count comparison reports a mismatch. A terminator is optional.
An explicitly empty `C` satisfies the structural rule. The term "eligible" does
not assert that an acquisition export captured all behavior.

| Condition | Result |
|---|---|
| Valid nonempty `C`; available saved counts match | First six metrics available; rate additionally requires valid S and time bounds |
| Valid prefix with fully corroborated unused zero tail | Exclude only confirmed storage slots, retain all raw values and exclusion metadata, calculate from the recorded prefix |
| `C` absent | All seven unavailable; absence is not an observed zero |
| Explicitly empty `C`, or only a terminator at index zero; no saved-count mismatch | Five counts are zero; proportion correct unavailable because `N = 0` |
| Missing C indices, including a first index other than zero | All seven unavailable; do not fill gaps or infer omitted choices |
| Any invalid/unknown encoded choice before the terminator | All seven unavailable; do not drop that record or shrink the proportion denominator |
| Values after the terminator, including another terminator | All seven unavailable; retain every raw value and warning |
| Any valid saved `A[0]`, `A[1]`, `A[2]`, or `B[0:4]` comparison is false | All seven unavailable pending review; neither source wins automatically |
| Saved summary counts absent, negative, fractional, or otherwise not comparable, while `C` itself is eligible | Calculate from `C` with warnings; unavailable cross-checks alone do not invalidate the observed sequence |
| Missing, invalid, or negative `S` | Duration unavailable; eligible choice counts and proportion remain available with warnings |
| Decodable timestamps decrease or exceed valid `S` | Retain eligible counts/proportion with warnings: these metrics count encoded outcomes and do not use timing or reorder events |
| Identical timestamps or identical encoded values at different valid indices | Count each indexed event; do not deduplicate or invent a duplicate-event interpretation |
| Printed array rows out of index order, but indices complete and unique | Use source-index order, retain the warning; eligible metrics remain available |
| Missing subject/session identifier | Do not invent an ID; eligible metrics remain available with source path/hash provenance |
| Unsupported program or a reader failure, such as duplicate indices or malformed numeric text | No successful metric result; preserve the per-file import failure |

The saved-count mismatch rule takes precedence over the empty-sequence zero rule.
For example, an empty `C` with saved `A[2] = 10` produces unavailable session metrics,
not ten inferred choices or five zero counts. If `C` is invalid, a comparison value
of `null` must not be treated as evidence of agreement.

Eligibility must use structured source/normalization facts, not parse warning text.
Warnings about unrelated raw-only fields do not by themselves make choice metrics
unavailable. All original warnings still accompany results.

## Partial sessions, ordering, and exclusions

An early stop or timeout is not automatically a reason to exclude a session. If its
recorded `C` meets the eligibility rule, calculate over those recorded choices. A
short sequence is not evidence of missing data by itself. Conversely, a contiguous
sequence cannot prove that no trailing records were lost: retain acquisition/end
status as unknown unless documented evidence establishes it.

Do not infer omissions or aborted trials from inter-choice intervals, a short session,
missing indices, or the difference from a presumed target. They are not separately
observed in these inputs and have no denominator contribution in this definition.
No silent exclusion of individual invalid choices is permitted. Confirmed storage slots
are explicitly excluded with recorded indices/counts under [the versioned rule](prl-unused-slots.md).

The exact terminator is excluded as a non-choice control marker. Post-terminator
values are retained raw and block the session metrics. Source C-array index defines
event order; no transitions are calculated, and no events are joined across sessions.
No timing cutoff, warm-up exclusion, minimum sample size, or user-configurable
eligibility override is implemented in version 2.

## Diagnostics and result reporting

Keep quality diagnostics separate from the behavioral summaries:

- Whether `C` is present and whether a terminator was observed.
- Raw C entry count and recognized unused slot count, separately.
- Number of observed pre-terminator choice records after storage exclusions, including invalid records.
- Number of valid decoded pre-terminator choices and number of invalid records.
- Number of raw entries after the terminator and whether C indices have gaps.
- Each existing saved-count comparison: match, mismatch, or unavailable.

Diagnostic counts describe only observed records. They are missing when `C` is
absent; explicit empty `C` has zero observed records. They are never substituted
for unavailable session metrics. In particular, a known count of valid decoded
records from a damaged sequence must not be presented as the session's total.

Each metric carries its stable identifier, definition version, value/unit,
availability status, all applicable unavailability reasons, and warnings. The
statuses are `available`, `available_with_warnings`, and `unavailable`. A result with
any retained session warning is not labeled warning-free. An unavailable value stays
`None` internally, blank in CSV, and visibly "Unavailable" in the GUI; its reasons
must remain attached in exports. A legitimate zero stays numeric zero.

Retain source path/hash, source identifiers, original C indices/values, original
saved counters, software/reader/normalizer versions, definition-set version, and the
fixed eligibility policy. Calculated columns must be distinct from raw fields.
Existing session/choice exports and manifests must preserve these additions without
overwriting saved data. No aggregation or weighting across sessions/subjects/groups
is defined here; in particular, no automatic average or pooled proportion is implied.

## Hand-calculated examples and acceptance cases

These are synthetic illustrations of the approved rules, not scientific validation.
Unless otherwise stated, `C` indices start at zero, every value is valid, and any
saved summary counts agree. Counts below are ordered as
`(choices, correct, incorrect, rewarded, unrewarded)`.

| Input | Expected counts | Expected proportion correct |
|---|---|---|
| `C = [0.01, 1.22, 2.36, 4.57]` | `(4, 2, 2, 2, 2)` | `0.5` |
| `C = [0.01, 1.22, 2.31]` | `(3, 3, 0, 2, 1)` | `1` |
| `C = [0.06, 1.27]` | `(2, 0, 2, 1, 1)` | `0`, a real proportion rather than missing |
| `C = [0.01, 1.26, 2.37]` | `(3, 1, 2, 2, 1)` | `1 / 3`, with no intermediate rounding |
| Explicit `C = []` | `(0, 0, 0, 0, 0)` | Unavailable: zero denominator |
| No `C` variable | All unavailable | Unavailable: missing choice array |
| `C = [0.01, 1.23, 2.36, 4.57]` | All unavailable; diagnostics: 4 records, 3 decoded, 1 invalid | Unavailable; do not report `1 / 3` from the valid subset |
| Valid choices only at indices 0 and 2 | All unavailable; diagnostics: 2 observed records and an index gap | Unavailable |
| `C = [0.01, 1.22, -987.987]` | `(2, 2, 0, 1, 1)` | `1`; terminator excluded |
| `C = [0.01, -987.987, 2.36]` | All unavailable; diagnostics: 1 decoded record, 1 post-terminator entry | Unavailable |
| Four-choice first example, but saved `A[2] = 5` | All unavailable; keep the disagreement visible | Unavailable |
| Four-choice first example, but A and B absent | `(4, 2, 2, 2, 2)`, with unavailable-cross-check warnings | `0.5`, with warnings |
| Three-choice second example, documented early stop with intact record | `(3, 3, 0, 2, 1)` | `1`; no assumed target denominator |

Additional automated acceptance cases cover missing/zero/invalid `S`,
time reversals and out-of-duration timestamps, repeated timestamps at distinct indices,
out-of-order rows, unrelated warnings, missing IDs, malformed imports, simultaneous
unavailability reasons, and export round trips of missing versus zero values.

The synthetic tests assert the hand-calculated results above and exercise GUI display,
CSV values/status/reasons/diagnostics, rounding boundaries, and failure isolation.
Five actual timeout recordings and two manual stops now pass local consistency checks.
The manual-stop unused slots are retained raw with explicit exclusion metadata. See
[partial-session validation](partial-session-validation.md) for evidence and limits.
Reader/export verification and synthetic tests do not establish general scientific
validity of these metrics.

## Implementation and reproducibility

`prl_metrics.calculate_prl_summary(session)` returns seven `MetricResult` values and
separate `PRLDiagnostics`. It uses the version 2 normalizer's decoded events, raw C
structure, and structured saved-count checks; it does not parse warning messages or
silently accept unsupported reader/normalizer versions. The approved fixed policy
has no user overrides. Normalized records that do not correspond to the source C
sequence after verified storage exclusions raise an error rather than yield a potentially
incomplete summary. Inconsistent storage metadata also raises an error; version 1
snapshots must be re-imported.

`processing.import_medpc_file()` calculates once after normalization, in the existing
background import worker when called through the GUI. `ImportResult.summary` holds
the result separately from the raw `Session`. The Session metrics tab and CSV export
consume that same snapshot. The GUI displays proportion values to four decimal places;
exports retain the full calculated Python float. Counts are integers. Percentages
are calculated as `correct / total`, with no intermediate rounding.

CSV schema 2 adds six columns named by stable metric ID to `sessions.csv` and stores
per-metric status, reasons, warnings, units, and versions in `metric_results_json`.
Diagnostics are in `metric_diagnostics_json`; definition set/version and eligibility
policy have their own columns and are recorded in the manifest. The choices table
retains all observations even when session metrics are withheld. See
[csv-export.md](csv-export.md) for the complete output contract.

Version history: version 1 is the initial owner-approved definition set, with strict
withholding for invalid/incomplete choice records and saved-count disagreements.
Version 2 adds the owner-confirmed, corroborated unused-tail exclusion, leaving the
six formulas unchanged. See [version 2 examples and guards](prl-unused-slots.md).
Version 3 implements the owner-requested change from percentage to proportion
correct on November 10, 2026, with a new metric ID and 0–1 scale. See
[accuracy scale migration](proportion-correct.md). Counts and eligibility are unchanged.
Version 4 adds whole-session Med-PC trials per minute from validated choices and S.
The first six formulas and phase definitions are unchanged; invalid duration affects
only the new rate. See [rate eligibility and examples](medpc-trials-per-minute.md).
Future semantic changes require a new definition version.

## Local verification record

On October 27, 2026, an offscreen GUI import/export check of the four supplied local
recordings compared all 24 calculated metric values against independent arithmetic
from saved A/B counters. All matched; the export contained four session rows and
120 choice rows with matching values, definitions, policy, and source provenance.
Original hashes and modification times were unchanged. Screens for available metrics
and a synthetic case with multiple withholding reasons were visually inspected.
Artifacts remain under ignored `outputs/`. This is a local consistency check, not
independent scientific validation or evidence for an actual early-stopped session.

In the initial November 4, 2026 check, after the owner confirmed PRL_OPTO's shared MPC interpretation,
five note-confirmed timeouts passed 35 saved-count checks and independent arithmetic
comparisons for all 30 metric values. Both CSV and Excel exports preserved all seven
supplied sessions and 292 C records: 92 valid timeout choices plus 200 manual-stop
records, including 174 invalid zero entries. The two manual-stop summaries remained
withheld with reasons. See [partial-session validation](partial-session-validation.md).
Adding a confirmed program name does not change metric formulas or the strict policy;
reader, normalizer, and metric definition versions remained 1 at that stage.

After confirmation of unused trailing slots, normalizer/definition version 2 imports
all seven recordings with 118 recorded choices and all 49 saved-count checks matching.
The 174 unused slots remain in raw arrays/source text and are recorded as exclusions.
All 42 metric values and both export formats were rechecked; see
[partial-session validation](partial-session-validation.md).
