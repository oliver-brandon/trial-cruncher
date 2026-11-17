# Manual experiment metadata and study inclusion

**Session metadata…** assigns condition/treatment, cohort, session order, and study
inclusion separately for each selected file. These are manual annotations, not
values inferred from Med-PC Group, Experiment, Subject, filenames, dates, or folders.
The original headers, source data, and metric definitions remain unchanged.

## Editing and review

Open the editor before or after import. It lists full paths so identical filenames
remain distinct, including files hidden by display filters. Each row provides:

| Field | Meaning and validation |
|---|---|
| Condition / treatment | One optional free-text label; leading-zero text is preserved |
| Cohort | An independent optional free-text label |
| Session order | Manually assigned positive integer, 1–2,147,483,647; Unassigned is missing, not order zero |
| Analysis inclusion | **Not reviewed**, **Include**, or **Exclude**; never inferred automatically |
| Reason | Required for Exclude; optional for Include/Not reviewed |

Blank text becomes unassigned; surrounding whitespace is removed. Case and internal
text are preserved. No sequential numbers, biological IDs, unique ordering constraints,
or inheritance across files from the same subject are invented. For example, two
different animals can both have session order 1. Session order does not replace the
original session ID or C-array indices and does not reorder source observations.

The bulk control applies one chosen field to **all files in the editor**, preserving
other fields. Inclusion and reason are applied together. Session order is entered
per file; no automatic numbering is performed. An invalid exclusion remains in the
editor until a reason is supplied or the edit is cancelled. Cancel preserves all
prior assignments; Save validates every row before applying anything.

Saving metadata applies it immediately to the existing reviewed records, without
re-reading sources or recalculating metrics. This differs from phase-label edits,
which still require re-import. Metadata editing is disabled during background work.
Use **Save project** to persist the current annotations; closing the editor alone
does not write a project file.

The upper **Phase results → Experiment metadata** layout shows the annotations and
supports numeric sorting of session order. Condition, cohort, and inclusion filters
can be used with every layout and with the existing phase/status/search filters.
Focused metric layouts also display inclusion beside source identity. Click a metadata
row for the read-only **Analysis metadata** detail tab, including its complete reason.
Manual metadata remains visible for unimported, failed, or stale sources; that does
not make unavailable calculated results valid. Clear selection removes assignments;
project load restores them and resets display filters.

## Inclusion is independent of calculation and display filtering

The default is **Not reviewed**, represented by `included=null`, not true or false.
Explicit Include is true; Exclude is false and requires a reason. Metadata can be
partially assigned while inclusion remains not reviewed.

These flags describe the investigator's intended analysis set. This milestone still
calculates per-file metrics for every readable supported recording so excluded data
can be inspected. Include never overrides strict withholding, source freshness, or
missing-data rules. Exclude never deletes raw data or fabricates unavailable/zero
measurements. The optional animal analysis uses Included recordings for its descriptive summaries.

**All successful recordings remain in exports, including Excluded and Not reviewed.**
Failed/unimported paths remain in the manifest with their metadata and reasons. A
display filter showing Included records changes only the view; it does not change
assignments, import scope, or export scope. Downstream analysis can explicitly select
`analysis_included=true`, while independently respecting each metric's validity.

## Project persistence and export contract

Project format **2** adds `analysis_metadata` to each source record. The object has
version `1` and exactly `condition`, `cohort`, `session_order`, `included`,
`inclusion_reason`, and `version`. It is validated on load/save, including types,
positive integer order, normalized strings, and the required exclusion reason.
Existing atomic-save, source-path/alias protection, hash checking, and compatibility
rules remain in force.

Format-1 projects can be loaded with all new fields unassigned and inclusion Not
reviewed. Paths, phases, reference hashes, and compatible analysis settings are
retained. The application reports the upgrade and marks it unsaved; loading alone
does not rewrite the original project. Save explicitly writes format 2. There is no
attempt to reconstruct past inclusion decisions or infer annotations from raw data.

Export table schema **7** and workbook layout **6** add these shared columns to
Sessions, Choices, Phase metrics, and Excel Quality:

| Column | Serialized meaning |
|---|---|
| `analysis_condition` | Manual condition/treatment label, or missing |
| `analysis_cohort` | Manual cohort label, or missing |
| `analysis_session_order` | Positive integer or missing |
| `analysis_included` | true / false / missing (Not reviewed) |
| `analysis_inclusion_status` | Included / Excluded / Not reviewed, explicitly readable |
| `analysis_inclusion_reason` | Manual reason, or missing |
| `analysis_metadata_version` | `1` |
| `analysis_metadata_source` | manual if any annotation is assigned, otherwise unassigned |
| `analysis_metadata_sha256` | SHA-256 of the canonical sorted-key JSON annotation object |

The manifest records every input's annotation object, hash, source, and inclusion
status, plus the all-records export policy. Metadata for imported sources comes from
the reviewed immutable result; editing replaces only its annotation field. Metadata
for an unimported source comes from the explicit current assignments. Export workers
snapshot these mappings, so ongoing work cannot mix annotation revisions.

CSV keeps false distinct from blank. Excel writes native booleans/integers and literal
text, preserving identifiers and formula-like labels; unsupported XML text still fails
explicitly. Existing long-text provenance chunks preserve long reasons. Duplicate
source filenames remain separated by the full path and source hash. Raw Group and
other acquisition fields remain untouched in raw metadata. Session/phase scientific
definitions stay at versions 4/2; these annotations add no new behavioral metric.

## Verification

Synthetic tests cover missing versus false inclusion, required reasons, type/order
validation, no raw-header inference, unchanged calculations, strict withholding,
literal text/booleans, all-records CSV/Excel output, failed/unimported metadata,
format-2 round trips, format-1 migration, and malformed project rejection. Offscreen
GUI tests use the editor's controls to check bulk/per-file edits, invalid Save,
Cancel, immediate updates, filters/hidden review, numeric order sorting, save/load,
worker snapshots, failed imports, stale sources, and unchanged export scope.

On November 10, 2026, an offscreen check used the seven supplied recordings with
clearly marked validation-only metadata and phase labels, not experimental assignments.
Three records were test-included, two test-excluded, and two left Not reviewed.
Editing metadata preserved the exact existing metric objects; project reload and
re-import preserved all calculated values. Filtering to the three Included rows still
exported all seven session/phase rows and 118 choice rows in both formats, with every
annotation and flag intact. Original source and summary hashes/mtimes were unchanged.
Artifacts remain under ignored `outputs/analysis-metadata-validation-*/`. This is
workflow/provenance verification, not a scientific decision to include or exclude
any real animal or recording.

Final checks: **359 tests passed**, along with Ruff lint/format, dependency,
documentation-link, and diff whitespace checks. The metadata editor and read-only
detail view were visually inspected offscreen. Native dialogs and native Microsoft
Excel rendering were not verified in this environment.

An optional [animal analysis plan](aggregation-pairing-spec.md) adds analysis-audit, individual-animal, condition-comparison, and pooled-metric tables to CSV and Excel exports. Save the plan, Included recording selections, and phase assignments together in project format 3.
