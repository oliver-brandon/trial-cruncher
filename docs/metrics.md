# Behavioral metric conventions

Six owner-approved PRL session-summary metrics are implemented: recorded choices,
correct/incorrect choices, rewarded/unrewarded choices, and percent correct. Their
versioned formulas, strict withholding rules, and hand-calculated acceptance cases
are specified in [PRL session-summary metrics](prl-session-metrics.md). The GUI
calculates them during import; session CSV exports retain values and diagnostics.

The [PRL normalizer](medpc.md) extracts task duration and choice outcomes and checks
their counts against saved summaries. Calculated metrics remain separate from these
source observations. Stored `A[5]` retains its `A[0] / Y` meaning and is not the new
percent-correct metric. Head entries are not recorded, so head-entry and latency
calculations remain unavailable. Owner approval and software tests do not establish
general scientific validity; actual partial-session validation remains outstanding.

Beyond the six implemented PRL definitions, the names below describe possible
future work, not universal definitions: completed trials, response/retrieval latency,
win-stay, lose-shift, perseverative/regressive errors, trials to criterion, acquisition/reversal performance,
progressive ratio breakpoint, presses/rates, and session duration.

Each metric belongs to a documented paradigm. A name alone is insufficient: for
example, the denominator of percent correct can change when omissions or aborted
trials are included. Review definitions with a domain expert before implementation.

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
