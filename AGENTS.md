# Trial Cruncher agent instructions

Inspect existing code, tests, and relevant documentation before changing behavior.
Preserve user content and carry authorized work through proportionate verification.
Keep changes within the requested milestone; do not build speculative frameworks.

## Architecture

- Use the `src/trial_cruncher` package layout and Python 3.12+.
- Keep the core independent of PySide6; Qt belongs only in `gui/`.
- Separate detection/extraction, normalization, paradigm configuration, calculations,
  orchestration, table generation, and export as described in `docs/architecture.md`.
- Prefer small typed functions, dataclasses, and the existing Protocol contracts.
  Add registries or plugin mechanisms only when concrete implementations need them.
- Long-running work belongs outside the GUI thread. Pass results through Qt signals;
  workers must never manipulate widgets.

## Code and verification

- Use clear names, type annotations at public boundaries, and helpful error messages.
- Configure logging only in application entry points; use named loggers in the core.
- Run `pytest`, `ruff check .`, and `ruff format --check .` after relevant changes.
- Test meaningful success, missing-data, malformed-input, and failure-isolation cases.
  Keep synthetic fixtures small and label them as synthetic. Never describe synthetic
  fixtures as scientific validation. Record checks that could not run.
- Update documentation to match actual capabilities; never describe interfaces as
  working readers, metrics, or exporters.

## Scientific integrity

- Never modify original inputs, overwrite them with exports, or silently drop data.
- Preserve source paths, source identifiers, units, event meanings, and warnings.
- Missing observations remain missing, distinct from zero; report unavailable metrics.
- Separate raw variables from calculated values. Do not invent subject/session IDs,
  trial boundaries, event labels, or task parameters.
- Do not assume all tasks have trials, a fixed schedule, a fixed reversal, a fixed
  number of trials, or a particular lever/subject/group configuration.
- Before adding a metric, document its versioned definition, formula, unit, inclusion
  and exclusion rules, missing-data policy, and hand-checked examples in
  `docs/metrics.md` or a linked paradigm document.
- Before adding a parser, obtain representative de-identified files and a documented
  schema. Identify the format from content where possible, retain unmapped fields,
  check units and MATLAB indexing/time origins, and report ambiguity or truncation.
- Validate new paradigms against domain-reviewed examples; do not infer scientific
  correctness from code tests alone. Record configuration and software/definition
  versions when implementing reproducible exports.
- Keep actual research data and credentials out of Git. Use ignored `data/`,
  `outputs/`, or `local/` folders; commit only approved, de-identified fixtures.
- Do not add a license, invent author details, or publish data without authorization.
