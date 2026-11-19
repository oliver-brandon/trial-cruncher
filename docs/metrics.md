# Behavioral metric conventions

Seven owner-approved PRL session-summary metrics are implemented: recorded choices,
correct/incorrect choices, rewarded/unrewarded choices, proportion correct, and whole-session Med-PC trials per minute. Their
versioned formulas, strict withholding rules, and hand-calculated acceptance cases
are specified in [PRL session-summary metrics](prl-session-metrics.md). The GUI
calculates them during import; session CSV exports retain values and diagnostics.

The [PRL normalizer](medpc.md) extracts task duration and choice outcomes and checks
their counts against saved summaries. Calculated metrics remain separate from these
source observations. Stored `A[5]` retains its `A[0] / Y` meaning and is not the new
proportion-correct metric. Head entries are not recorded, so head-entry and latency
calculations remain unavailable. Owner approval and software tests do not establish
general scientific validity. Five supported timeout recordings now pass local
consistency checks. `PRL_OPTO` uses the owner-confirmed shared interpretation;
confirmed manual-stop zero tails are excluded as unused storage under
[definition version 2](prl-unused-slots.md), preserving raw arrays and exclusions. See
[partial-session validation](partial-session-validation.md).

Eight additional phase metrics are implemented under `prl-medpc-phase-behavior`
version 2: phase proportion correct, perseverative/regressive errors, adjusted regressive
error proportion, and four correct/incorrect-conditioned win-stay/lose-shift
probabilities. Their [implementation specification](medpc-behavioral-metrics-spec.md)
records the owner-confirmed fixed-contingency/no-omission profile, manual phase
assignment, strict withholding, formulas, denominators, and acceptance evidence.
Missing phase labels leave these results unavailable without suppressing the
existing session summaries. [Med-PC trials per minute](medpc-trials-per-minute.md)
is now a separate, explicitly approved whole-session metric: 60 times validated
recorded choices divided by S. The independently defined MAT rate remains deferred;
the Med-PC rate is not a silent fallback for it.

Other future metric families include response/retrieval latencies, trials to criterion,
and progressive-ratio breakpoint. Each needs its own
paradigm-specific definition and reviewed source observations before implementation.

[Animal aggregation and pairing](aggregation-pairing-spec.md) implements the confirmed
single-recording selection and pooling rules. It uses globally unique Subject IDs,
one project per analysis, metric-specific valid animal counts, and the individual
values for condition and phase comparisons.

## Required metric specification template

Copy this template into a paradigm document and link it here when implementing one.

```text
Name / stable identifier:
Definition version and change history:
Paradigm and applicable protocol versions:
Scientific meaning and source/reference:
Output row level (trial, session, subject, group):
Unit and expected range:
Required raw variables, event codes, units, and time origin:
Configuration parameters, allowed values, and justified defaults:
Formal definition/formula (define every symbol and denominator):
Observation ordering, boundaries, and transition rules:
Inclusion criteria:
Exclusion criteria and reported exclusion counts:
Omissions, aborted trials, partial sessions, and censored observations:
Missing, malformed, duplicate, or out-of-order observation policy:
Zero-denominator / no-eligible-observations behavior:
Aggregation and weighting across sessions/subjects/groups:
Warnings and conditions that make the result unavailable:
Source provenance and reproducibility requirements:
Small hand-calculated examples and expected results:
Edge cases and independent tests:
Domain reviewer and validation evidence (only when actually available):
```

## Rules

- Preserve missing values as missing. A real zero is a valid measured/calculated
  result, not a substitute for missing inputs. Undefined probabilities or ratios
  must remain missing with an explanation.
- Define eligible observations and denominator explicitly, including any conditioning
  on prior events, session/task boundaries, and incomplete transitions.
- Document latency start/end events and treatment of absent retrieval or response.
- Define reversal/criterion/breakpoint rules from protocol configuration. Never hardcode
  a reversal index, reinforcement schedule, trial count, or lever assignment.
- Keep raw observations and calculated values separate; never rename a source field
  as a metric without documenting the transformation.
- Record semantic definition changes and preserve enough configuration/provenance to
  reproduce earlier results. Do not silently reinterpret existing metric names.
- Test hand-calculated synthetic examples and separately compare real, approved
  reference cases. Distinguish software verification from scientific validation.
