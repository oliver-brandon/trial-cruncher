# Animal summaries and condition pairing

**Confirmed specification, revision 3 · November 17, 2026.** One treatment per recording. The investigator selects at most one Included recording per global Subject × condition × phase in a single cohort. Pool eligible evidence across animals within each condition and phase. Use individual values for comparisons.

## Analysis scope

One analysis covers one experiment/cohort, an explicit set of treatment conditions, and acquisition, reversal, or both phases. Its design is explicitly between-subjects or within-subjects. Every result, sample count, pair, and source audit belongs to that analysis. Display filters have no role in membership.

The inputs are the reviewed [session metrics](prl-session-metrics.md), [phase metrics](medpc-behavioral-metrics-spec.md), and [manual annotations](analysis-metadata.md). Source freshness, current metric definitions and strict source-integrity checks apply. Both existing full-batch exports and the analysis audit retain Excluded and Not reviewed files with their dispositions.

## Owner decisions

| Decision | Rule |
|---|---|
| ID1 · Identity | Use the globally unique raw Subject ID as text. Preserve leading zeros and case. Count each identified biological animal once within the analysis. |
| ID2 · Cohort | An animal belongs to one cohort/experiment. Analyze one such scope at a time. Flag contradictory cohort assignments for review. Several condition or phase observations for the same ID within that cohort are legitimate. |
| S1 · Repeated observations | Keep an animal's acquisition and reversal observations linked. Different IDs can belong to different treatment groups, or one ID can contribute to several treatment conditions. The investigator selects which recording(s) from complication-driven retests belong in each analysis. |
| S2 · Phase order | Acquisition precedes reversal. Support either phase alone. Session order provides chronology where assigned. Phase and treatment labels come from explicit assignments. An acquisition recording is optional for a reversal-only analysis. |
| S3 · Weighting | When pooling is requested, label the result as pooled and sum eligible numerators and denominators. Show both sums, their units and all contributors. The pooling population must be explicit. |
| M1 · Missing outcomes | Leave each undefined or unavailable metric cell blank, retain its reason, and allow other metrics and observations to contribute. Report the valid sample size for each metric. |
| P1 · Condition order | Condition order has display significance only. Show observed values by condition. Omit calculated differences, directional contrasts and percent changes. |
| P2 · Pairing | Within an animal, identify each observation by its condition and phase. Match acquisition and reversal within condition, or match conditions within the selected phase, according to the requested comparison. |

## Selecting recordings

1. Snapshot the analysis scope, design, selected conditions and phases, imported results, and current annotations. Only explicitly Included recordings enter the candidate set. Keep each exclusion reason and distinguish Not reviewed from Excluded.
2. Resolve the global Subject, condition, phase, and experiment/cohort membership for each candidate. Flag unresolved keys and duplicate-content candidates with source paths and hashes. Preserve the original strings and recording-level session IDs where available.
3. **Confirmed retest rule.** Allow one selected recording per animal × condition × phase in an analysis. When two Included recordings occupy that cell, show both and ask the investigator to select the intended recording for this analysis. Until resolved, flag that cell as ambiguous. Session order, date, import order, and metric validity must never silently choose a winner.
4. Apply the existing per-metric validity rules to the selected recording. Preserve available-with-warning values with their warnings. Track failed, stale, unimported, missing-key, and ambiguous records in the audit. A valid partial session is eligible under the same rules as any other selected session.

The scope and selected sources must be reproducible per analysis. A recording can participate in a different analysis under a separately saved selection. Choices, three-correct streaks, and strategy transitions stay within their original recording.

## Comparison tables

| Design and phase scope | Rows and columns |
|---|---|
| Between-subjects, both phases | One row per animal, labeled with its treatment group. Show that animal's acquisition and reversal values side by side. Summarize the distinct animals within each group. |
| Between-subjects, one phase | One row per animal in its assigned group for the requested phase. Compare groups descriptively without matching one animal to another. Flag an ID appearing in multiple selected treatment groups for design review. |
| Within-subjects, one phase | One row per global animal ID. Show its observed values for each selected condition in that phase. |
| Within-subjects, both phases | One row per animal per metric, with separately labeled condition × phase cells. The within-condition acquisition/reversal view and the within-phase condition view reference the same cells. |

Build the roster from the union of candidate IDs in the analysis scope. For a missing partner, retain the observed cell and leave the partner blank with a reason. If both sources exist but one strategy is undefined, preserve both sources, show the available value, and mark only that metric's pair incomplete. Keep per-condition valid animal counts and complete-pair counts distinct. For more than two conditions, state which columns must be present in the reported complete set. Reordering conditions may reorder columns only.

## Pooling and sample sizes

Only pool compatible observations inside the approved scope, population, condition, phase, and metric definition. Keep the individual animal observations available alongside each labeled pool.

| Pooled quantity | Eligible numerator | Eligible denominator | Unit |
|---|---|---|---|
| Proportion correct | Sum of correct choices | Sum of recorded choices | proportion, 0–1 |
| Each win-stay or lose-shift probability | Sum of that strategy's successes | Sum of that same strategy's eligible conditioning pairs | probability, 0–1 |
| Adjusted regressive-error proportion | Sum of regressive errors for eligible postcriterion observations | Sum of valid postcriterion choices | proportion, 0–1 |
| Whole-session Med-PC trials per minute | 60 × sum of validated recorded choices from rate-eligible sessions | Sum of their positive S durations in seconds | choices/min |

Use the same contributors for both sums. Known zero successes with a positive denominator give a genuine zero and contribute to valid animal N. A known 0/0 observation stays blank with a zero-opportunity reason. Its zero counts add no weight and the animal does not contribute a defined value to that metric's N. Unknown or withheld inputs contribute neither term. A zero pooled denominator gives a blank pooled value and a reason. A zero-choice session with valid positive S has a defined zero rate and contributes its duration under an approved rate pool. Count the Med-PC rate only once across its Sessions and Phase metrics representations.

Keep raw error counts and criterion diagnostics at their recorded animal/session level. Any additional across-animal count statistic needs its own explicit label and definition. Report candidate and selected session counts, distinct candidate animals, valid contributing animals per metric and condition, zero-opportunity/unavailable counts, and complete within-animal pairs per metric. Record the underlying choice counts, strategy opportunities, or duration separately from biological sample size.

## Outputs and provenance

- **Analysis audit** covers every selected source with path/hash, raw Subject, cohort, condition, phase, session order, inclusion/reason, selection disposition, and per-metric status/reasons.
- **Animal metrics** has one observation per resolved animal × condition × phase × metric for this analysis. Include units, source lineage, criterion/ratio evidence, and availability.
- **Condition comparison** presents the relevant between- or within-subject layout above. Include side-specific source references, reasons for blank cells, and pair completeness where applicable.
- **Pooled metrics** records the explicitly selected pooling scope, metric ID/version, both sums, resulting value/unit, metric-specific N, zero-opportunity counts, and contributing and omitted sources.

Save the analysis design, scope, selection and duplicate resolutions, pooling rule, and configuration hash. Trace every derived row to source, metadata, phase, and metric-definition versions. Rebuild affected results after changes to source validity, assignments, inclusion or analysis selection. Existing export protections apply. Derived tables use analysis schema version 1. Inferential tests are outside this milestone.

## Synthetic acceptance examples

1. Two **different animals** in the same treatment and reversal phase have 1/2 and 9/10 correct. Show individual values 0.5 and 0.9, pooled proportion 10/12 ≈ 0.8333, two contributing animals, and 12 choices.
2. In that same scope, one animal's strategy is 0/0 and the other's is 2/4. Show blank with reason and 0.5 respectively. The pool is 2/4, valid animal N is 1, and the zero-opportunity count is 1. If the first observation were 0/2 instead, both animals would contribute and the pool would be 2/6.
3. Two eligible sessions from different animals contribute 2 choices/60 s and 18 choices/180 s. The condition-level rate pool reports 20 choices, 240 s, and 5 choices/min.
4. For reversal under two within-subject conditions, animal 007 has A=0.4 and B=0.7. Animal 008 has A=0.8 and missing B. Keep both rows. A has two valid animals, B has one, and one animal has a complete pair. Reversing the columns preserves these results.
5. Animal 007 has one acquisition file and two reversal files under A after a technical complication. Under the confirmed single-recording rule, explicitly select one reversal. Two Included reversal candidates leave that cell ambiguous. A reversal-only analysis can proceed once the intended reversal is identified, regardless of acquisition availability.
6. A source with the same global Subject but a conflicting cohort assignment needs review. Repeated condition/phase cells in the same cohort do not create additional animals. Subject strings `007` and `7` retain distinct identities.

## Analysis configuration and output versions

Animal summaries, pooling and pairing use definition version 1. One saved project holds one optional analysis plan. Save As preserves a separate selection for another analysis. Select a cohort, design, exact treatment labels and phase labels in acquisition-to-reversal order. The Included source flags select recordings. Resolve a retest by retaining Include on the intended file and marking the other file Exclude with a reason. Analysis tables use version 1 as an optional extension to the full-batch export contract. Preview and export build fresh from the reviewed import and current metadata.

## Using the analysis

The cohort dropdown uses the **Cohort** field in **Session metadata…**. Older projects
can have phase assignments and blank cohort fields. If the list is empty, choose
**Open session metadata…**, enter a cohort per file, or select **Cohort** and
**Apply field to all files** for a single-cohort batch. Save the assignments and
use **Save project** to keep them. After reopening a project, use **Import Med-PC**
to rebuild its phase results before previewing an analysis.

1. Import files with their phase assignments. Use **Session metadata…** to set cohort, treatment, and Include for the intended recording in each animal × condition × phase cell. Use Exclude and its reason to resolve a retest. Use **Save project as…** when another analysis needs a different recording selection.
2. Open **Animal analysis…**. Choose one cohort and the design, then check the exact condition and phase labels. **Apply and preview** calculates from the full reviewed batch in a background worker. The standard acquisition and reversal labels appear in that order. Custom labels retain their exact text.
3. Inspect **Pooled metrics** for the ratio of sums, **Condition comparison** for individual observations, **Animal metrics** for source values and evidence, and **Analysis audit** for the disposition of every file. Resolve ambiguous cells through metadata and reopen the analysis to refresh the preview.
4. Close the preview, then choose the detailed export option and use **Export CSV…** or **Export Excel…**. Detailed exports rebuild the four tables from the current reviewed snapshot and verify source freshness. **Disable analysis** removes the analysis plan from future exports. **Save project** persists the current plan and per-file selection.

The preview reports how many recordings were selected from the batch. In **Condition
comparison**, **Assigned conditions** lists the treatments represented by source
recordings for that animal in the selected scope. Each condition × phase has its own
value column. A missing partner or blocked comparison shows its recorded reason.
Expand cells with source evidence to see the recording paths.

In **Analysis audit**, **Recording proportion correct** comes from the reviewed session.
It remains visible for a repeat that cannot contribute to the animal comparison.
If two recordings are Included for the same animal, condition and phase, use Session
metadata to keep the intended recording Included and mark the other Excluded with a
reason. Reopen **Animal analysis** and apply the plan again.

The optional analysis tables use schema 1 alongside the existing full-batch tables. The manifest's aggregation entry records the scope, design, identity and pooling policies, definition version and plan hash. Join source references in derived rows to the audit and manifest for recording hashes, annotation hashes and phase configurations. Projects saved with an analysis plan use project format 3. Projects without a plan use the existing format 2. Opening a saved project requires re-import to rebuild the observations.

Individual results use long format with one row per selected animal cell and existing metric ID. The seven pooled rows per condition and phase cover accuracy, adjusted regressive proportion, four strategy probabilities, and the Med-PC session rate. Rate evidence columns give choices and seconds with scale 60. Raw count metrics and criterion positions are available on individual rows. A pool with no positive denominator has a blank value and an explanatory reason. Known zero-opportunity evidence retains zero sums. An entirely unobserved pool has blank sums.

Comparison columns use JSON arrays of the condition and phase labels, preserving exact strings even when they contain punctuation. Cell evidence includes source paths, reasons and valid animal N. Complete animal N refers to all required cells for that row and metric. Pair coverage additionally gives complete animal N for acquisition/reversal within each condition and, for within-subjects designs, across selected conditions within each phase. Missing or excluded partners remain auditable. A conflict blocks the affected animal cell or design stratum while other animals remain eligible.

## Verification

Synthetic tests cover denominator weighting, zero-opportunity and unavailable metrics, missing counterparts, acquisition/reversal and condition pairing, cohort conflicts, duplicate recordings and retests, stale sources, both export formats, plan persistence, and the offscreen GUI selection/preview/export workflow. Seven supplied recordings were also imported with disposable cohort, condition, phase and inclusion labels for software verification. Independent arithmetic on their saved counters and timers agreed with the pooled accuracy and rate in both CSV and Excel. The preview included seven audit rows, 105 individual metric rows and 14 pooled rows for the two test conditions. Original source and summary hashes and modification times were preserved. Experimental pairing still needs a representative dataset with investigator-reviewed condition and phase assignments.
