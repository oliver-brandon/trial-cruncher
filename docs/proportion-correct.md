# Accuracy as proportion correct

On November 10, 2026, the owner requested accuracy as a proportion instead of a
percentage. This applies to both session and phase accuracy. For an eligible,
nonempty recorded sequence:

```text
proportion_correct = correct_choice_count / recorded_choice_count
```

The unit is **proportion**, with range **0–1**. For example, 2/4 = 0.5; 1/3 is
exported at full calculation precision; 0/4 = 0; 4/4 = 1. With zero recorded choices,
or with missing/invalid data under the existing eligibility rules, the value remains
unavailable. No denominator, inclusion rule, raw field, or other metric changes.
In particular, saved `A[5]` retains its target-based fraction and is not substituted.

| Scope | New metric/column | Definition set/version |
|---|---|---|
| Session | `prl.proportion_correct` | `prl-session-summary`, version 3 |
| Phase | `prl.phase.proportion_correct` | `prl-medpc-phase-behavior`, version 2 |

These replace `prl.percent_correct` and `prl.phase.percent_correct` in new outputs.
Table/bundle schema advances to 4 and Excel workbook layout to 3. Old exported files
are never rewritten; their percentage columns retain their original 0–100 meaning.
Normalizers, raw data, strict-withholding-v2, and unused-slot handling are unchanged.

The overview and metric panels label accuracy **Proportion correct** and display
four decimal places. Sorting and exports use full calculated values. Excel cells
are numeric decimals with no percentage format or percent suffix. CSV/JSON metadata
and metric units explicitly identify the 0–1 scale.

Existing project format 1 files with the exact previous configuration (session
definition 2, phase definition 1, and otherwise current settings) can be loaded.
The window flags the configuration update, preserves file paths/phases/reference
hashes, and requires re-import as with every project load. Saving explicitly writes
the new configuration; loading alone leaves the project file untouched. Other
configuration mismatches are still rejected, and old calculated snapshots are not
accepted for new exports. This is a narrow known scale update, not a general migration.

## Verification

All **295 tests** passed, including proportion endpoints/fractions, undefined and
withheld cases, GUI labels, numeric Excel formats, old-snapshot rejection, and the
explicit project-upgrade/re-import/save workflow. Ruff lint/format and Markdown
link checks passed. A local check of seven supplied recordings compared all 14
session/phase accuracy values against independent saved-counter arithmetic and
verified both exports, including reconstructed Excel provenance chunks. Original
hashes/mtimes and raw metadata were unchanged. Phase labels were disposable test
labels, not inferred experimental assignments. Artifacts remain under ignored
`outputs/proportion-validation-final-*/`; native Excel rendering was not tested.
