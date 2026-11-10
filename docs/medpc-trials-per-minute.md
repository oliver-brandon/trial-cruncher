# Med-PC trials per minute

Status: **Owner-approved on November 10, 2026; initial formula in session definition 4.**
Metric ID: `prl.medpc_trials_per_minute`. Display name: **Trials/min (Med-PC)**.
Unit: **choices/min**; output level: **whole session**, independent of phase assignment.

The owner selected the recorded task duration S, matching the acquisition programs'
saved A[3] formula. A trial in this label means a recorded completed choice under
the confirmed fixed-contingency/no-omission protocol. It does not invent trial
boundaries or additional opportunities.

```text
N = validated recorded choice count
duration_seconds = S
Med-PC trials per minute = 60 * N / duration_seconds
```

This uses the entire recorded task duration, including waiting and timeout time.
It does not use the header clock interval, planned time limit, last choice plus five
seconds, or MAT cues/TTL timestamps. The separately specified MAT rate remains deferred
and must use a distinct metric ID if later implemented.

## Eligibility and missing values

- Use the existing strict recorded-choice eligibility and corroborated unused-slot
  exclusion. Damaged/missing C or a saved-count conflict withholds the rate; never
  substitute A[2] for an unavailable decoded choice count.
- S must be present, finite, representable, and strictly positive. Missing, negative,
  zero, or unrepresentable duration makes **only this rate** unavailable; eligible
  counts, accuracy, and phase metrics retain their existing rules.
- If a decoded choice timestamp exceeds S, the rate is unavailable because the
  observations fall outside the proposed whole-session duration. Counts/accuracy
  retain their existing timing-warning behavior. Decreasing timestamps within S
  retain warnings but do not alter this count-over-duration calculation or reorder data.
- An explicitly empty eligible sequence with positive S has a genuine zero rate.
  Empty C and zero/missing S gives an unavailable rate, not zero or infinity.
- Nonfinite calculated output is unavailable. Do not round intermediate values.
- Preserve source warnings and explicit rate-specific unavailability reasons.
  There is no rate aggregation across sessions, animals, or phases in this milestone.

Saved A[3] remains raw provenance. It may be rounded or unfinalized after manual
stops, so it is neither the calculation input nor an eligibility/count check.
Source arrays, S, hashes, lines, and original source text remain unchanged.

## Hand-checked synthetic examples

| Eligible choices | S (seconds) | Expected choices/min |
|---:|---:|---:|
| 30 | 180 | 10 |
| 4 | 10 | 24 |
| 10 | 3600 | 1/6, using the full timeout duration |
| 2 | 120 | 1 |
| 0 | 120 | 0 |
| 0 or positive count | 0 or missing | Unavailable |

An invalid choice record or a saved-count mismatch yields unavailable rate even when
S is positive. A last choice at 12 seconds with S=10 also yields unavailable rate;
the duration is never enlarged or replaced automatically.

## Reporting and versions

The rate is a seventh session-summary metric. Session definition version 4 identifies
the addition; phase definitions remain version 2. Reader/normalizer versions, strict
withholding, proportion-correct scale, and unused-slot interpretation are unchanged.
The Sessions overview and Session metrics panel expose the rate. The batch Phase
results **Session rate** layout shows whole-session choices, duration, rate, and its
own availability status. These are session values, not an independently computed
phase rate, and remain usable when a phase label is unassigned.

CSV/Excel Sessions tables include the new metric alongside duration_s and recorded
choice count, with versioned unit/status/reasons. The rate is not added to the eight
phase metrics or duplicated as a phase-specific metric in phase_metrics.csv.
The manifest records its whole-session formula, duration source, and unit.
Table schema advances to 5 and workbook layout to 4. Existing saved projects with
the exact prior session-3/phase-2 setup (or the supported earlier percentage setup)
retain paths/phases/hashes, receive an explicit upgrade notice, and require re-import;
Save explicitly persists the updated configuration. Other configuration mismatches
remain rejected. Old computed results cannot be relabeled as current exports.

## Verification

On November 10, 2026, all seven supplied partial recordings matched independent
Decimal arithmetic from the supplied choice counts and S values. Their existing
49 saved-count checks still matched. GUI Session metrics and the Session rate batch
layout displayed the same values; both exports preserved the rates, duration, counts,
units, availability, definition versions, and raw source text/A[3]. The verification
used no phase assignments, confirming the rate is whole-session. Original input and
summary hashes/mtimes were unchanged. The prior proportion-project setup was also
loaded, explicitly re-imported, and saved under the new configuration. Artifacts
remain under ignored `outputs/medpc-rate-validation-*/`.

The final suite passed **321 tests**, including rate boundaries, strict withholding,
invalid duration isolation, numeric sorting without phase assignments, and export
precision/provenance. Ruff lint/format, dependency, documentation-link, and diff checks
passed. GUI inspection was offscreen; native Excel rendering was not tested. These
are software and local arithmetic checks, not general scientific validation.
