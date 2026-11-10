# Med-PC PRL behavioral metrics — implementation specification

Status: **Owner-confirmed rules; implemented.**
Specification revision: 3 · November 10, 2026.
Definition set: `prl-medpc-phase-behavior`, definition version 2.

This milestone supports the confirmed PRL_BO, PRL_OPTO, and PRL_OPTO_CORSTIM
interpretations. On November 10, 2026 the owner confirmed one fixed contingency per
file, no omissions because levers stay extended until a choice, manual phase
assignment during import, and authorization to implement. Strict withholding remains
in force; trials per minute stays deferred.

## Basis and scope

Source: owner-supplied **PRL behavioral metric definitions**, version 1.2,
September 22, 2026, filename `PRL_BEHAVIORAL_METRIC_DEFINITIONS.md`.
Source SHA-256: `a07717554220746588fe0da0f112de1147145558dbdc2785807740583554bec2`.
Sections 1, 2, 4–7 supply the behavioral definitions and worked example. Section 8
records a separate MAT-based experiment; its TTL fields, reward matching, session
selection, sample sizes, and verification claims are not Med-PC defaults or evidence
that these new calculations have been validated in Trial Cruncher.

The owner requested accuracy on a 0–1 proportion scale on November 10, 2026. This
supersedes the supplied reference's percentage reporting without changing the
denominator or eligibility. See [scale migration](proportion-correct.md).

This milestone covers phase proportion correct; perseverative and regressive error
counts; adjusted regressive-error proportion; and correct/incorrect-conditioned
win-stay and lose-shift probabilities. It includes criterion and denominator evidence,
GUI review, and CSV/Excel export. Results describe observed choices, not reconstructed
trial opportunities, physical reward retrieval, or modeled behavior.

**Deferred:** trials/choices per minute, MAT parsing or linkage, cue/lever TTL matching,
latencies, inferred omissions, trials to criterion as a separate metric, subject/group
aggregation, statistical tests, cross-session learning criteria, and intrasession
reversal processing. Do not calculate a fallback rate from `S`, header elapsed time,
saved `A[3]`, or last C time plus five seconds. `S` remains recorded task duration.

Existing session summaries remain `prl-session-summary` version 3 with
`strict-withholding-v2`. Phase results are separate and never silently replace
`prl.proportion_correct` or reinterpret saved `A[5]`.

## Confirmed phase and omission rules

| Decision | Owner-confirmed rule | Implementation consequence |
|---|---|---|
| P1 | Each file has one fixed contingency. | One phase per imported file; never combine files or infer an intrasession reversal. |
| P2 | The user assigns phase during import. | A per-file phase editor with optional bulk assignment, no automatic default. Preserve custom labels such as Reversal 2. An unassigned phase leaves new metrics unavailable while session summaries remain usable. |
| O1 | There are no omissions; levers remain out until a choice is made. | Adjacent C choices are the adjacent completed-choice sequence. Waiting time does not create an omission. |
| O2 | Not applicable to this confirmed no-omission protocol. | Do not invent a streak reset/continuation policy for other tasks. Corrupt or missing choice records still trigger strict withholding. |

These facts are recorded as protocol profile `fixed-contingency-no-omissions-v1`,
with owner-confirmation date and evidence in configuration. `omission_count=0` is a
protocol assertion, not a count measured from cue TTLs. This profile is limited to
the three confirmed program interpretations, not all future Med-PC tasks. Known
contradictory protocol evidence requires renewed review rather than silently applying
this profile. Phase labels are user input, not evidence inferred from filenames.

## Input and provenance contract

Use the current content-validated reader version 1 and normalizer version 2 output.
Calculators consume canonical records and structured diagnostics; they never re-read,
rewrite, repair, or reorder the source file.

| Required fact | Med-PC source / interpretation |
|---|---|
| Source session | One imported file; retain full path, SHA-256, original File header and program name |
| Animal | Original Subject header, unchanged; missing stays missing |
| Biological session ID | Original ID if explicitly available; current imports may have none |
| Choice order and provenance | Original zero-based C index and source line; never timestamp-sort or renumber the raw index |
| Correct / rewarded | Confirmed C suffixes: `.01` = correct/rewarded, `.02` = correct/unrewarded, `.06` = incorrect/rewarded, `.07` = incorrect/unrewarded |
| Time | Existing normalized task-relative seconds; retained for provenance, not used for the deferred rate |
| Saved count checks | Session-level A[0..2] and B[0..3] comparisons |
| Unused slots | Existing `validated-zero-tail-v1` recognition and explicit exclusion metadata |
| Phase and fixed contingency | Explicit confirmed configuration from P1/P2; not inferred from elapsed time, choice count, or correctness changes |
| Omission evidence | Explicit confirmed protocol assertion or documented observations with positions; otherwise unknown |

Within a fixed two-lever contingency, equal correctness classifications mean the
same lever and unequal classifications mean the other lever. Do not use that
equivalence across a reversal. Reward means **Med-PC program-encoded reward outcome**.
Do not introduce MAT `Pe1_` matching or treat a missing outcome as nonreward.

Keep missing Subject/session identifiers visible with warnings and source provenance.
A technical source-record key may identify the file in tables, but must be labeled
as such, never populated into a fabricated biological session ID. No cross-file
grouping or joining is permitted in this milestone. Do not assume exactly 30 choices,
one daily session, or a fixed number of subjects.

## Eligibility and strict withholding

Apply the existing session integrity check **before** phase processing. Session A/B
counters validate the complete recorded session, not an arbitrarily selected subset.
The initial single-phase-per-file scope avoids dividing those counters by phase.

| Condition | Required behavior |
|---|---|
| Reader failure, unsupported program/version, or stale canonical records | Preserve per-file failure; no new metric values |
| Missing C | All new values unavailable; never substitute saved counters |
| C index gaps, invalid choice/outcome, post-terminator values, or any comparable saved-count mismatch | Withhold all new behavioral values for the source; do not salvage valid runs/pairs or unaffected-looking windows |
| Fully corroborated unused trailing slots | Exclude storage slots exactly as already approved; preserve raw arrays and excluded indices/counts |
| Unrecognized zeros or contradictory/missing evidence needed to recognize padding | Existing strict rules apply; do not discard zeros |
| Saved cross-check absent/noncomparable but otherwise intact unpadded C | Existing warning-only policy applies; unavailable checks are not matches |
| Unknown phase | All new phase results unavailable; the confirmed fixed-contingency profile is recorded separately |
| Task outside the confirmed no-omission profile | Unsupported; requires a separately reviewed protocol rather than a guessed omission rule |
| Short, manually stopped, or timed-out session with intact eligible record | Calculate over the recorded choices; no minimum count or assumed completion |
| Missing/invalid S or timing warnings with complete ordered C indices | Retain warnings; these choice-order metrics do not require duration or re-sort by time |

Partial sessions do not imply missing trailing choices. Conversely, intact arrays
do not prove the experiment completed. Use source-index order, retain duplicate
timestamps at distinct indices, and keep legitimate zero probabilities/counts distinct
from unavailable values. Known missing records never become zero omissions.

No incomplete valid subset is promoted to a full metric. Diagnostics can describe
observed records in a withheld source, but eligible-pair totals, criterion state,
and metric numerators/denominators are null when their prerequisites are unresolved.
The current whole-session summaries retain their own eligibility semantics.

## Metric definitions

Output unit of analysis: animal × source session × confirmed contingency phase.
For an eligible phase with N recorded choices, let `c[t]` and `r[t]` be its boolean
correctness and reward flags. Positions t are **one-based choice ordinals**, not
invented trial numbers. Raw C indices remain separately available and zero-based.
All metric identifiers below belong to definition version 2 of the new set.

Let K be the first ordinal completing three consecutive correct choices in that
phase. Each incorrect choice resets the current streak to zero; a correct choice
increments it. Once K is reached, do not reset K or restart perseverative counting.
Reward does not affect this criterion. Omissions do not occur in the confirmed protocol.

| Stable identifier | Formula / rule | Unit |
|---|---|---|
| `prl.phase.proportion_correct` | `sum(c[t]) / N` for N > 0 | proportion, 0–1 |
| `prl.phase.perseverative_errors` | Count incorrect choices at t < K; if no K, all incorrect choices | count |
| `prl.phase.regressive_errors` | Count incorrect choices at t > K; zero if no K in a nonempty eligible phase | count |
| `prl.phase.adjusted_regressive_error_proportion` | Regressive errors / number of choices after K | proportion, 0–1 |
| `prl.phase.win_stay_correct` | Correct/rewarded conditioning choices followed by a stay / all eligible correct/rewarded conditioning choices | probability, 0–1 |
| `prl.phase.win_stay_incorrect` | Incorrect/rewarded conditioning choices followed by a stay / all eligible incorrect/rewarded conditioning choices | probability, 0–1 |
| `prl.phase.lose_shift_correct` | Correct/unrewarded conditioning choices followed by a shift / all eligible correct/unrewarded conditioning choices | probability, 0–1 |
| `prl.phase.lose_shift_incorrect` | Incorrect/unrewarded conditioning choices followed by a shift / all eligible incorrect/unrewarded conditioning choices | probability, 0–1 |

All counts are nonnegative integers. Compute ratios once without intermediate rounding.
Export full calculated values and integer numerators/denominators; rounding is display-only.
Before reversal, the perseverative label describes errors on the currently incorrect
lever; it does not establish persistence on a formerly correct contingency.

For each eligible within-phase adjacent pair (t, t+1), stay means
`c[t+1] == c[t]`; shift means `c[t+1] != c[t]`. Only t supplies the conditioning
class and reward. Altering a valid reward flag on t+1 must not change this pair's
eligibility or outcome (it can change the subsequent pair). An actually missing
outcome anywhere still invokes the source integrity gate; never infer its value.
The phase's last choice contributes to accuracy/errors but cannot condition a pair.

### Empty observations and zero denominators

- N = 0 with an explicitly observed empty eligible sequence: accuracy, both error
  metrics, adjusted error proportion, and all strategy probabilities are unavailable.
  Observed choice counts and eligible pair count are genuinely zero. Criterion state
  and K/postcriterion count are null because there are no behavioral observations.
  Strategy numerators and denominators can be recorded as observed zero with
  `undefined_probability=true`; the probability itself stays null.
- N > 0, no K: `criterion_reached=false`, K null, postcriterion count 0;
  perseverative errors equal incorrect count, regressive errors 0, adjusted proportion null.
- K = N: `criterion_reached=true`, postcriterion count 0, regressive errors 0,
  adjusted proportion null. The zero is not evidence of maintained performance.
- A strategy denominator of zero gives null probability plus an undefined flag;
  its observed numerator is zero. Withheld/unobserved denominators stay null, not zero.
  The undefined flag is null when denominator eligibility could not be established.
- A genuine zero numerator with a positive denominator gives numeric zero.
  No "reported zero" substitution for undefined probabilities is authorized.

## Results, review, and export contract

Retain a separate phase result alongside the current session summary. `phase_metrics.csv` and an Excel **Phase metrics** sheet contain one row per source
session/phase, including unavailable results with explicit reasons. Sessions, Choices,
Quality, Provenance, and manifests remain available. Unknown phase must be null in
an unavailable result row, not a made-up phase. Failed imports remain in the manifest.
No aggregate animal/group rows, pooled ratios, or inferred sample sizes are produced.

Required supporting fields:

| Field group | Required content |
|---|---|
| Identity | Composite technical source key `(source_file, source_sha256)`, original subject and nullable session IDs, original program and user-assigned phase label (custom labels may distinguish reversal number) |
| Configuration evidence | P1/P2/O1/O2 confirmations or unresolved states, their source/scope, configuration version/hash; no inference of global approval from one session |
| Versioning | Application, reader, normalizer, storage policy, existing session policy, new definition-set and metric versions, export schema versions |
| Counts | Phase recorded/correct/incorrect choices, whole-session recorded choices, raw C count and unused-slot indices/count, invalid-record diagnostics |
| Missing observations | Nullable recorded omission count, omission observability/evidence, known index gaps separately; never conflate slots, omissions, or missing records |
| Criterion | Nullable `criterion_reached`, one-based `criterion_choice_ordinal`, zero-based `criterion_source_index`, postcriterion choice count |
| Errors | Raw perseverative/regressive counts, adjusted numerator/denominator and proportion in separate columns |
| Strategies | Four independent numerator/denominator/probability/undefined-flag groups; eligible pair count when known |
| Result status | Per-metric value, unit, status, reasons, warnings and versions; phase-analysis status must not conceal existing available session summaries |

Stable reason codes are `phase_unassigned`, `source_integrity`, `no_choices`,
`no_postcriterion_choices`, and `zero_strategy_denominator`. They distinguish phase
assignment, integrity withholding, empty observations, and zero strategy
denominator, with readable explanations. Reuse the existing available,
available-with-warnings, and unavailable result semantics. Source integrity failures
remain visibly withheld; undefined ratios are visibly unavailable for their own reason.

Choice rows retain original indices; add documented phase assignment and criterion/error
annotations only where their prerequisites are met. Unavailable classifications stay
missing, never "correct" or "no error". Excluded storage remains fully preserved in
raw metadata. No input mutation, overwrite, formula interpretation, long-text loss,
or export filtering is allowed. Both export formats use the same reviewed snapshot.

Export table/bundle schema is version 4; Excel workbook layout is version 3, adding
Phase metrics and phase/error annotations on Choices. Do not stamp new manifest
definitions onto old computed results. Definition IDs and any
configuration affecting semantics must be recorded so results can be reproduced.

## Acceptance examples and checks

These are synthetic examples. The ten-choice example is reproduced from the supplied
reference for agreement testing, not as a research dataset. All examples below assume
P1/P2/O1 are confirmed and there are no omissions or integrity failures.

| Choice ordinal | Class | Reward | Error class |
|---:|:---:|---:|---|
| 1 | I | 0 | Perseverative |
| 2 | I | 1 | Perseverative |
| 3 | C | 1 | Correct |
| 4 | I | 0 | Perseverative |
| 5 | C | 1 | Correct |
| 6 | C | 0 | Correct |
| 7 | C | 1 | Correct; K = 7 |
| 8 | I | 0 | Regressive |
| 9 | C | 1 | Correct |
| 10 | I | 0 | Regressive; no next choice |

Expected: N=10; correct=5; accuracy=0.5; perseverative=3; regressive=2;
postcriterion=3; adjusted=2/3. Win-stay correct=1/4, win-stay incorrect=0/1,
lose-shift correct=0/1, lose-shift incorrect=2/3. The four denominators sum to 9.

Additional hand-checked cases (C/I strings describe choices, not raw C-array tokens):

| Case | Expected |
|---|---|
| One incorrect choice | N=1, accuracy=0, perseverative=1, regressive=0, criterion false, postcriterion=0, adjusted unavailable; all four strategy denominators zero |
| `CCC`, all rewarded | K=3, both errors zero, postcriterion=0, adjusted unavailable; win-stay correct=2/2, other strategy denominators zero |
| `CCCIICCC` | K=3 remains fixed; perseverative=0, regressive=2, postcriterion=5, adjusted=2/5, accuracy=0.75 |
| Eligible empty C or recognized all-unused storage | N=0, behavioral metrics unavailable, no fabricated criterion success or error-free performance |
| Any invalid choice, index gap, or saved-count conflict | All new behavioral metrics withheld; do not join the surrounding valid choices |
| Intact sequence but unknown phase | New phase metrics unavailable; current session summaries retain their independent availability |
| Unassigned phase | All eight new metric values are unavailable; existing session summaries still calculate |
| Two distinct sessions ending/starting `CC` and `C` | Never form a three-correct run or transition across the file boundary |
| Recognized trailing slots appended to an eligible nonempty sequence | Metrics and pairs unchanged; raw/excluded counts increase transparently |

Implementation tests must additionally check all four transition categories, next-choice
reward independence, no reset after K, incorrect-choice reset before K, criterion on
the final choice, distinct missing/zero/false states, stale configurations, unknown
programs, failure isolation, and equal/decreasing timestamps without sequence reordering.
Internal omissions are outside the confirmed protocol; do not add a test that
silently blesses a reset or continuation rule for another protocol.

For eligible nonempty omission-free phases:

- Correct + incorrect = N.
- Perseverative + regressive = incorrect.
- Postcriterion count = N - K when K exists, otherwise 0.
- Each strategy numerator lies in [0, denominator]; defined probabilities lie in [0,1].
- Total eligible pairs = N - 1; the four strategy denominators partition those pairs.

## Implemented workflow and components

1. Add files/folders, then choose **Assign phases…** before importing. The dialog shows
   full source paths, supports Acquisition/Reversal or a custom text label, and can
   apply a label to all files. There is no inferred/default phase. Cancel preserves
   assignments. Save records pending assignments for the next import.
2. Click **Import Med-PC** to snapshot the full path-to-phase mapping and process all
   selected files in the background, including hidden rows. Assignments are disabled
   while busy. Editing them later does not relabel existing results: re-import to apply.
3. Select a source and open **Phase metrics** for eight values, numerator/denominator
   evidence, criterion diagnostics, statuses, and reasons. Existing Session metrics
   remains separate. Clearing selection clears assignments and both result views.
4. Export the reviewed snapshot to CSV or Excel. A changed pending assignment does
   not change exported phases. Re-import failure/cancellation never leaves stale phase
   results. Failed files remain accounted for independently of successful files.

`phase_metrics.py` holds immutable configuration/results and the Qt-independent
calculator. It validates the existing full-session integrity rule before examining
choice order. `processing.py` attaches `phase_summary` to each successful import.
`gui/phases.py` edits per-file assignments; the import worker copies the mapping.
`tables.py` builds phase rows and choice annotations. Exporters reject missing/stale
phase definitions, policies, configurations, or source provenance and preserve
literal text, missing/zero/false values, long metadata, and no-overwrite behavior.
Assignments can now be saved in `.tcproj.json` projects together with analysis
configuration and source hashes. Loading restores setup and requires re-import;
source changes also block stale exports. See [projects](projects.md). Cross-file/group
analysis remains future work.

Python API example (explicit user assignment):

```python
from pathlib import Path
from trial_cruncher.processing import import_medpc_file

result = import_medpc_file(Path("data/session.txt").resolve(), phase="Reversal 2")
if result.phase_summary is not None:
    print(result.phase_summary.metrics)
    print(result.phase_summary.diagnostics)
```

Omitting phase imports and preserves the existing session summaries but produces
unavailable phase metrics with reasons. The CLI inspection command retains its
existing read-only raw/choice scope; phase calculations are exposed through GUI/API.

## Verification and limits

The owner confirmed the scientific rules and authorized implementation on November 10,
2026. The ten-choice example matches the supplied reference. Synthetic tests also
compare all 341 four-outcome sequences of length zero through four against an
independent criterion-window/transition reference, plus longer criterion-maintenance
cases and next-choice reward invariance. These checks are software verification.

Offscreen GUI tests cover actual phase-dialog controls, cancel/save, duplicate
filenames with full-path identity, bulk/custom labels, import snapshots, background
execution, cancelled and failed re-imports, clearing assignments, unassigned phases,
and full-batch export with filters active. Export checks retain ratios, flags,
criterion indices, configuration hashes, source provenance, literal formula-like
labels, and stale-version rejection. Native Microsoft Excel rendering and native
OS dialogs are not established by these checks.

Local verification of all seven supplied incomplete recordings used an explicitly
labeled disposable **validation-only** phase, not an inferred acquisition/reversal
assignment. Direct source-text extraction and independent NumPy calculations matched
all 56 phase metric values (including undefined values), all 28 strategy
numerator/denominator pairs, and criterion/postcriterion evidence. CSV and Excel each
contained seven phase rows and 118 choice rows, with all 3,788 session/choice/phase
cells compared to the reviewed snapshot. All 174 unused slots remain preserved raw.
Source and summary hashes/mtimes were unchanged. Artifacts remain under ignored
`outputs/phase-metrics-validation-*/`. Actual experimental phase assignments must
still be entered by the user; this verification does not supply them.

No real recordings were copied into committed fixtures. These comparisons establish
local arithmetic/provenance consistency, not general scientific validation or a
statistical analysis of treatment effects. Trials per minute remains deferred.

Final verification on November 10, 2026: **247 tests passed**, including the
341-sequence independent comparison inside the suite. Ruff lint and format checks,
dependency consistency, Markdown links, and diff whitespace checks passed. The phase
assignment editor and eight-row review screen were visually inspected offscreen.

## Batch comparison

The upper **Phase results** tab now provides a read-only batch comparison of these
same imported metrics and denominators, with focused error/win-stay/lose-shift layouts
and independent phase/status filters. It introduces no new scientific definition or
export version. See [batch phase results](batch-phase-results.md).
