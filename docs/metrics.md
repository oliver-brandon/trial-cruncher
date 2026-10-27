# Behavioral metric conventions

No behavioral metrics are implemented or scientifically validated in this release.
The [PRL normalizer](medpc.md) extracts task duration and choice outcomes and checks
their counts against saved summaries. These are extraction/consistency checks, not
a new metric suite. Stored `A[5]` is preserved as the source's `A[0] / Y` fraction;
it must not be relabeled as an independently calculated percent correct. Head entries
are not recorded, so head-entry and retrieval/response latency calculations are
unavailable for the current protocol.

The names below describe potential work, not universal definitions: percent correct,
completed trials, rewards, response/retrieval latency, win-stay, lose-shift,
perseverative/regressive errors, trials to criterion, acquisition/reversal performance,
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
