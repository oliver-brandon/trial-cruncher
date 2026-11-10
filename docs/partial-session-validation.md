# Partial-session validation scope

On November 4, 2026, seven supplied recordings and their summary were checked locally.
The owner confirmed that five timeout labels came from notes and that the two other
recordings were manual stops. The initial audit treated the four `PRL_OPTO` files as
unsupported. The owner subsequently confirmed that PRL_OPTO uses the exact same MPC
setup as CORSTIM and PRL_BO. It is now supported under that shared interpretation.

## Current result after unused-slot confirmation

The owner then confirmed that the manual-stop trailing zeros are unused array slots
and authorized excluding them while retaining all raw data. Normalizer and metric
definition version 2 implement the [corroborated storage rule](prl-unused-slots.md).
All seven sessions now have available metrics: **118 recorded choices**, **49 matching
saved-count checks**, and **42 metric values** matching independent arithmetic from
the saved A/B counters. The two manual stops each contribute 13 choices; their 87
unused slots each remain in the original raw arrays, text, and line provenance.

The GUI displays the raw entry and unused slot counts separately from recorded
choices. All CLI inspections exit successfully, with versioned storage metadata.
CSV and Excel contain seven session rows and 118 choice rows, retain all 174 unused
slots in raw session metadata, and record the excluded indices/counts and policy.
All 3,035 session/choice cells in each format were compared against the reviewed
snapshot, including exact raw source text and the complete arrays. Excel's embedded
manifest matches the companion manifest. Original input/summary hashes and mtimes
remain unchanged. Validation artifacts remain under ignored
`outputs/unused-slots-validation-*/`.

Reader version 1, table schema 2, and workbook layout version 1 are unchanged.
Normalizer/metric definition versions are now 2; old interpretation snapshots are
rejected for export with a request to re-import. The suite includes success,
zero-denominator, conflicting/missing counters, invalid/internal-zero prefixes,
nonzero tails, gaps, terminators, stale metadata, and stale-export-version cases.
The full suite passed **214 tests**, Ruff lint/format checks, and diff whitespace
checks. The GUI suite passed again after correcting the definition label to version 2;
the manual-stop metrics and unused-slot diagnostics were visually inspected.

## Intermediate result after program compatibility confirmation

At this stage all seven recordings imported under their original program names. Five timeout
sessions provide 92 choices, match all 35 saved-count checks, and have 30 available
metric values matching independent counter arithmetic. The two manual-stop sessions
each retain 100 C records: 13 decoded choices and 87 zero entries with unavailable
decoded fields. All six session metrics in each manual stop remained withheld under
the unchanged strict policy; the 13 decoded records are diagnostic counts.

CSV and Excel export all seven sessions and 292 C records, including all 174 zero
entries and their unavailable fields. The manifests list seven successful imports;
metric reasons/diagnostics and Excel Quality distinguish the withheld summaries.
Filtering the GUI to one session does not restrict export. Full saved-cell comparisons
and source hash/mtime checks were repeated after adding support. Local artifacts are
under ignored `outputs/opto-support-validation-*/`.

Reader, normalizer, and metric definition versions remained 1: this added a confirmed
program name without changing existing decoding, metric definitions, or eligibility.
The suite passed **187 tests**, including PRL_OPTO decoding, hand-calculated
metrics, short/timeout-length CSV/Excel exports, and zero-tail withholding.

## Initial audit before compatibility confirmation

- All seven files matched the SHA-256 hashes in the supplied summary. Subject,
  date, experiment, program, saved choice count, task timer, configured time limit,
  and header elapsed time agreed with the corresponding summary fields.
- Three note-confirmed timeouts used supported `PRL_OPTO_CORSTIM`. They imported
  without warnings, produced 43 choices, and matched all 21 A/B count checks. All
  18 calculated metric values matched separate arithmetic from the saved counters.
  Direct lexical checks of the original C arrays independently matched indices,
  source lines, raw values, timestamps, and outcome codes.
- Task duration used `S`, not the longer header elapsed time. The timeout records
  had a saved 60-minute limit and `S=3600.1` seconds. These values are consistent
  with the owner's timeout notes; the application does not infer an end reason.
- Four `PRL_OPTO` recordings remained explicit unsupported-program failures, with
  complete raw extraction available for review. Two were note-confirmed timeouts;
  the two manual stops had nonzero C prefixes followed by zero-valued tails.
  Numeric suffix tallies over the summary-count prefixes agreed with all 28 saved
  A/B comparisons for these files. This is numeric consistency evidence, not an
  approved interpretation of that program or authority to discard the tails.
- GUI mixed-batch review kept all seven paths visible. CSV and Excel exports
  included the three supported sessions and all 43 choices, and both manifests
  accounted for the four unsupported files with errors and hashes. With only one
  supported session visible through the overview filter, both formats still exported
  the complete successful batch. Each format's 1,119 session/choice cells matched
  the reviewed tables, including complete raw metadata and source text. Excel's
  embedded manifest matched the companion manifest, and Quality retained all input
  outcomes and supported metric statuses.
- Hashes and modification times of all seven inputs and the supplied summary were
  unchanged. Research recordings, per-recording results, verification scripts, exports,
  and screenshots remain under ignored `data/` and `outputs/` paths.

The existing supplied `PRL_OPTO_CORSTIM` acquisition source has a timer threshold
and a normal stop/save path. Its name does not prove byte-identical acquisition code
was used for these historical recordings. No exact historical revision, physical
reward delivery, unrecorded behavior, or completeness beyond the saved observations
is established by these checks. Notes supply the termination labels; they are not
new fields automatically added to application imports or exports.

## Interpretation limits

Actual timeout and manual-stop consistency are now checked for the supplied records.
This does not establish universal validity across historical program revisions or
other acquisition layouts. The versioned rule requires agreement from all counters
and the entire array structure; it never accepts all nonzero entries or blindly
trims at `A[2]`.

Zeros outside a fully corroborated unused tail remain invalid choice records and
cause withholding. A GUI quality label of **Available** means metric availability; it does
not mean the intended experimental protocol completed.

Synthetic regression checks in `tests/test_partial_sessions.py` cover short and
timeout-length durations with observed-choice denominators in CSV/Excel, unknown
program raw preservation, recognized unused-slot exclusions, and withholding when
the full array/counter guards fail. They use small invented data, not copied research
fixtures. See [metric definitions](prl-session-metrics.md), [Med-PC support](medpc.md),
and [Excel serialization](excel-export.md) for the unchanged contracts.

Before the compatibility confirmation, all **175 tests** passed, along with
`ruff check .`, `ruff format --check .`, and `git diff --check`. Application behavior
and scientific definition versions were not changed by that initial validation work.
