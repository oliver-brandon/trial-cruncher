# PRL unused trailing slots — interpretation version 2

On November 4, 2026, the owner confirmed that the trailing zeros in the supplied
manual-stop recordings are unused array slots and authorized handling them while
preserving raw data. The owner also confirmed that PRL_OPTO has the same MPC setup
as PRL_BO and PRL_OPTO_CORSTIM. This rule applies only to those confirmed programs.

The reader remains version 1. Normalizer version 2 and PRL metric definition set
version 2 use storage policy `validated-zero-tail-v1` and eligibility policy
`strict-withholding-v2`. Metric formulas and units are unchanged; the changed inclusion
rule requires new interpretation/definition versions. Old snapshots must be re-imported.

## Recognition and inclusion rule

Let `L` be the number of printed C entries and `N` the saved `A[2]` count. Recognize
exactly indices `N` through `L-1` as unused slots only when **all** conditions hold:

1. C is present and all its indices are contiguous from zero.
2. `A[2]` is a nonnegative integer with `0 <= N < L`.
3. Every C entry in `0..N-1` decodes as a valid choice under the confirmed encoding.
4. Every entry in `N..L-1` is exactly numeric zero. No nonzero value, terminator,
   or other negative marker may be discarded.
5. All seven counters `A[0]`, `A[1]`, `A[2]`, and `B[0..3]` are present, nonnegative
   integers, and agree exactly with the decoded prefix counts.

There is no fixed array size, trial target, duration cutoff, or inferred stop reason.
The rule recognizes unused storage, not manual termination itself. An internal zero,
index gap, invalid prefix, missing/conflicting counter, or nonzero tail prevents this
recognition entirely. Those inputs follow the existing strict rules, preserving invalid
choice entries and withholding metrics rather than salvaging a valid subset. Values
after an explicit terminator remain raw and block metrics as before, including zeros.

The recognized slots are not choices and contribute to none of the six metric
numerators or denominators. For an eligible prefix, the five counts and percent
correct use only its N recorded choices. If N is zero and all counters are zero,
five counts are zero and percent correct is unavailable (zero denominator). An absent
C remains missing, and cannot be turned into zero choices by saved counters.

## Provenance and reporting

Original source bytes, source text/hash, complete raw C values and indices, source
line numbers, and saved counters are unchanged. Normalized choice events and choice
tables contain the recorded prefix only. Session `choice_storage` metadata records
the policy, raw C entry count, unused slot count, and original excluded indices.
Missing C has missing counts; a present array without recognized padding has zero
excluded slots. Accepted exclusions are informational diagnostics, not invalid-choice
warnings. Other warnings are retained.

Metric diagnostics report raw C entries, recognized unused slots, observed choice
records, and valid/invalid choice counts separately. The calculator re-evaluates the
storage rule from raw data and rejects inconsistent exclusion metadata or event
sequences. CSV and Excel session metadata and diagnostics preserve these facts,
including the original unused values; manifests record the storage and metric policies.
The CLI and GUI expose the exclusion information. Neither reports the session as
experimentally completed merely because the metrics are available.

## Hand-checked synthetic acceptance examples

The examples are invented software cases, not research recordings. Each A list below
contains A[0..2], and each B list contains B[0..3]. Counts are ordered as choices,
correct, incorrect, rewarded, unrewarded.

| C | A | B | Expected |
|---|---|---|---|
| `[0.01, 1.22, 2.36, 4.57, 0, 0]` | `[2, 2, 4]` | `[1, 1, 1, 1]` | Exclude indices 4,5; counts `(4,2,2,2,2)` and 50%; retain all six raw entries |
| `[0.06, 1.27, 0]` | `[0, 2, 2]` | `[0, 0, 1, 1]` | Exclude index 2; counts `(2,0,2,1,1)` and genuine 0% |
| `[0, 0]` | `[0, 0, 0]` | `[0, 0, 0, 0]` | Exclude both slots; five zero counts, percentage unavailable |
| `[0.01, 0, 2.36, 0]` | `[1, 2, 3]` | `[1, 0, 1, 1]` | No exclusion; invalid prefix, all metrics withheld |
| `[0.01, 0, 2.36]` | `[1, 0, 1]` | `[1, 0, 0, 0]` | No exclusion; nonzero value after proposed boundary, all metrics withheld |
| `[0.01, 0, 0]` | `[1, 0, 1]` | missing | No exclusion; insufficient corroboration, all metrics withheld |
| `[0.01, -987.987, 0]` | `[1, 0, 1]` | `[1, 0, 0, 0]` | No exclusion; post-terminator data still withholds metrics |

Changing these recognition conditions or exclusions requires a new versioned rule.
