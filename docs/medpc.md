# Med-PC reader and PRL normalization

## Supported scope

`MedPCReader` reads one UTF-8/ASCII Med-PC text session per file, including a UTF-8
BOM and Windows CRLF line endings. Detection looks for nonempty `File:` and `MSN:`
headers, not a filename extension. `can_read()` examines the first 64 KiB as a format
probe; `read()` performs structural validation. Program source `.MPC` files and macOS
AppleDouble `._*` sidecars are not session exports.

`PRLNormalizer` interprets only the exact `MSN` names `PRL_BO` and
`PRL_OPTO_CORSTIM`. Their supplied program versions and the rules below were confirmed
by the project owner. Program names do not identify future code revisions reliably:
changes to acquisition code require renewed schema review and a normalizer version
change when interpretation changes. Other programs can be extracted as raw data, but
are rejected by this normalizer rather than assigned PRL semantics.

Reader and normalizer contract versions currently both equal `"1"`.

## Use

With the development environment activated:

```sh
trial-cruncher --inspect-medpc "data/your-session.txt"
```

This prints a JSON inspection containing source path/hash, program, identifiers,
task duration, decoded choices, summary checks, and warnings. Warnings/errors are
also structured logs on standard error. Exit codes are **0** for a warning-free
inspection, **1** for read/normalization failure, and **2** for a completed inspection
with warnings (argument usage errors also follow argparse's exit code 2). This is
an inspection command, not a CSV/Excel export pipeline.

For GUI review, launch `trial-cruncher --gui`, add files or a folder, and click
**Import Med-PC**. Click a file to browse Session details, Decoded choices, Warnings
and checks, and Source text. The Session metrics tab shows the six owner-approved
PRL summaries, with strict withholding and diagnostic counts; see
[their definitions](prl-session-metrics.md). The same reader and normalizer drive both interfaces.
The choice table displays unavailable fields explicitly and preserves source array
indices/order. Failed files have no decoded choices; if extraction succeeded before
normalization failed, their original headers and source remain available.

Imports run in the background with per-file progress. Cancel stops before the next
file, retaining completed results. Re-importing replaces prior results, including
when a file has changed or become unreadable. Source review is read-only.
**Export CSV…** saves the reviewed sessions and choices to a fresh folder, preserving
raw metadata, warnings, and missing values; see [CSV export](csv-export.md).
Closing waits for the active file and cancels remaining imports; during export it
waits for the export to finish.

Programmatic use keeps raw extraction independent of PRL interpretation:

```python
from pathlib import Path

from trial_cruncher.medpc import MedPCReader
from trial_cruncher.prl import PRLNormalizer

path = Path("data/your-session.txt")
raw = MedPCReader().read(path)
(session,) = PRLNormalizer().normalize(raw, path)

print(raw["headers"])
print(raw["arrays"]["C"])  # Original zero-based index -> Decimal value
print(session.duration_s)
for choice in session.events:
    print(choice.raw_values["index"], choice.timestamp_s, choice.attributes)
print(session.metadata["summary_checks"])
print(session.warnings)
```

## Raw extraction and provenance

The reader returns a typed mapping containing:

- Original header strings, including identifiers with leading zeroes, the original
  Windows `File` value, and unknown headers.
- Scalars and arrays as `Decimal` values. Array dictionaries preserve each explicitly
  printed index; no values are filled in for missing indices. Empty arrays differ
  from absent variables. Unknown variables and negative numeric values remain raw.
- The decoded source text with original newline characters (initial UTF-8 BOM removed),
  SHA-256 of the original bytes, resolved local source path, reader version, and source
  line numbers for headers, variables, and array elements.
- Warnings for sparse or out-of-order array indices.

The source text retains lexical details beyond parsed values. Duplicate headers,
variables, overlapping array indices, malformed numeric tokens, orphan array rows,
unrecognized lines, and concatenated sessions raise `MedPCReadError` with file/line
context instead of silently overwriting or dropping content. Numbers may use decimal
or scientific notation; nonnumeric and nonfinite tokens are rejected. Unsupported
text encodings fail explicitly. The reader never writes to inputs.

## Confirmed interpretation

`S` is task duration in seconds, measured from task start to finish. Header times
include the period when the program was loaded before the animal began the task;
their difference is **not** task duration. Missing, negative, or unrepresentable `S`
produces an unavailable duration and warning, with no header-time fallback.

`D` is the session's configured correct lever (`0` left, `1` right), chosen opposite
to the animal's preferred training lever. It is preserved unchanged in the raw scalar
map; training preference is not analyzed or inferred.

`C` encodes each choice as the task timer, which advances in 0.1-second increments,
plus an outcome code:

| Added value | Correct | Rewarded |
|---|---|---|
| `0.01` | yes | yes |
| `0.02` | yes | no |
| `0.06` | no | yes |
| `0.07` | no | no |

Decode the hundredths-place digit using decimal arithmetic and subtract its value
from the raw number. For example, synthetic `12.91` means a correct/rewarded choice
at **12.9 seconds**, not 12.91 seconds. "Rewarded" describes the program's pellet
outcome; it does not establish physical delivery or retrieval.

Each `Session.events` entry is a `choice` with task-relative `timestamp_s` and
`attributes` containing `outcome_code`, `correct`, and `rewarded`. Original value,
array name/index, and source line remain separate in `raw_values`. Events are ordered
by source array index, never sorted by timestamp. Unknown codes, negatives, excessive
fractional precision, or unrepresentable values remain choice records with unavailable
decoded fields and a warning. Decreasing timestamps and choices beyond `S` are flagged.

The exact `-987.987` terminator written by the supplied programs is retained raw but
is not a choice. Any values after it remain raw and generate warnings rather than
being interpreted. No rounded marker variants or zero-padding conventions are assumed;
unrecognized negative values or zero-valued `C` entries are flagged. Actual sample
exports omit the terminator.

There is no hardcoded trial count, session maximum, reversal point, subject count,
or group assignment. A choice event is not a reconstructed trial interval. The reader
does not invent trial start times, trial identifiers, or a session identifier; absent
session IDs remain `None`. `source_file` and original array indices provide provenance.

## Head entries and stored summaries

Head entries are no longer recorded in this protocol. `A[4]`, `F`, and `J` are
preserved raw but excluded from interpretation. The session explicitly records
`head_entries_recorded=False` and `latency_available=False`. A saved zero head-entry
counter is not treated as a measured zero. No response/retrieval latencies are computed,
and differences in `F` encoding between the two programs are irrelevant to this normalizer.

Counts decoded from `C` are checked against `A[0]` (correct), `A[1]` (incorrect),
`A[2]` (total), and `B[0:4]` (the four outcomes in the table above). Each check is
`True` for a match, `False` for a mismatch, or `None` when a comparison is unavailable.
Saved values are never corrected. Missing/fractional/negative summary counts produce
warnings. Missing/sparse/invalid `C` or data after a terminator makes all comparisons
unavailable; an explicitly empty `C` can be compared against genuine saved zero counts.

`A[3]`, `A[5]`, and the optogenetic program's `A[6]` remain saved source values, not
newly calculated metrics. In the supplied code, `A[5]` is **a fraction** computed as
`A[0] / Y`, despite its "Percent Correct" comment. `Y` is the configured maximum
number of choices and is not exported in these samples. The normalizer does not
recompute this fraction, substitute observed choice count for `Y`, or infer whether
a session ended by reaching its limit or by timeout. See [metrics.md](metrics.md)
before adding any behavioral calculations.

## Verification and limits

On October 23, 2026, local verification of the four supplied de-identified recordings
decoded 120 choice records and matched all 28 saved count comparisons, with no warnings.
Both the programmatic reader and CLI were checked; hashes and modification times
remained unchanged. These recordings and their `.MPC` files stay under ignored `data/`
and are not bundled with tests or published.

On October 27, 2026, an offscreen GUI integration check imported the same four files,
displayed all 120 choices and 28 matching checks, and verified unchanged input hashes
and modification times. Session-detail and choice-table screenshots were inspected.
This does not establish native desktop/dialog behavior on every supported OS.

Automated tests use independently constructed synthetic exports, including known
timestamps/outcomes, missing data, sparse arrays, malformed input, summary mismatches,
unsupported programs, and CLI error behavior. This is software verification and local
consistency checking, not general scientific validation of Med-PC or PRL analysis.
An actual early-stopped/timed-out recording is still useful additional evidence.

Six PRL session-summary metrics are implemented separately from extraction and
normalization. Additional metric families, configurable batch analysis, Excel export,
general Med-PC dialect support, and a MATLAB reader remain future work.
Session CSV schema 2 includes the six calculated values with versioned definitions,
strict withholding reasons, and diagnostics; raw observations remain unchanged.
