# Saved projects and source verification

Trial Cruncher projects save the analysis setup so it can be restored in a later
window. Project format version **1** uses a UTF-8 JSON file ending in `.tcproj.json`.
Project files contain source paths, phase labels, settings, and hashes; keep them
private alongside the research workspace. They are ignored by Git by default.

## Workflow

1. Add files/folders, assign phases, and configure file extensions/subfolder discovery.
2. Click **Save project**. On the first save, choose a new `.tcproj.json` file.
   Later saves update that open project. **Save project as…** creates a separate
   project and refuses an existing destination.
3. Click **Open project…** to restore a saved setup. A successful open replaces the
   current file selection and phase assignments; save pending changes first if needed.
   Cancelling the picker or a validation/read failure preserves the current setup.
4. Review changed/missing source messages, then click **Import Med-PC** to calculate
   results. Every project load requires import, even when fingerprints match: project
   files do not cache raw recordings or calculated results.
5. Use **Check sources** to refresh source status without importing. Both export
   formats automatically verify imported source hashes before writing and again before
   publishing the completion manifest.

The project label shows the current file, unsaved setup changes, and source issues.
Phase edits are pending configuration for the next import. Saving a project preserves
those pending assignments, while an export still uses the reviewed import's phase.
Re-import applies edits to the analysis. The source freshness guard applies regardless
of whether a project has been saved or loaded.

Load, save, and hash checks run outside the GUI thread. File/phase/project edits,
import, and export are disabled during those operations. Closing waits for the active
operation to finish. A save failure retains the window's current setup for retry.
Discovery filters affect new additions, never which explicit project paths are restored.
View filters are cleared on load and are not stored in the project.

## Saved contract

| Field | Meaning |
|---|---|
| `format` | Exact marker `trial-cruncher-project` |
| `schema_version` | Project schema `1`, independent of export schemas |
| `application_version` | Application version that wrote the project |
| `saved_at_utc` | Save timestamp with time zone |
| `analysis_configuration` | Reader/normalizer versions, storage policy, session and phase definition sets/versions/policies, and the confirmed phase protocol profile |
| `discovery.extensions` | Normalized file extensions for future additions |
| `discovery.recursive` | Whether future folder discovery includes subfolders |
| `sources[].path` | Full absolute source path; identical filenames in different folders remain separate |
| `sources[].phase` | Explicit normalized phase label or null when unassigned |
| `sources[].sha256` | Reference content fingerprint, or null when no readable reference has been recorded |

The phase protocol profile preserves its configuration version, owner-confirmation
date, fixed-contingency/no-omission interpretation, and evidence text. These analysis
policies are fixed in the current application, not freely editable parameters.
Loading validates compatibility with the installed interpretation. An unknown project
version or different analysis configuration is rejected without applying settings;
it is never silently migrated to different scientific rules. The one explicit
exception is the known percentage-to-proportion configuration update described below.

All JSON fields and types are validated. Duplicate object keys, duplicate source paths,
relative/parent-traversal paths, invalid hashes, malformed phase labels, unknown fields,
and oversized files (over 16 MiB) are rejected. No scripts, callbacks, calculated
results, raw source text, or arbitrary configuration code are loaded from a project.
Missing source files are valid references and remain in the restored selection.

Paths are absolute on the current host. There is no automatic relocation by filename
or content search; restore the original path or explicitly rebuild the selection if
the research directory has moved. No biological session or subject IDs are invented.

## Fingerprints and re-import

An existing reference hash comes from the last imported raw snapshot or loaded project.
**Saving or checking never advances a known hash just because the source changed.**
Re-import updates it when the reader returns a new raw snapshot. A first save of a
previously untracked readable file records its current fingerprint; that does not
claim the file was parsed or analyzed. An unreadable/missing new file keeps a null
fingerprint and remains listed.

| Check result | Behavior |
|---|---|
| Same SHA-256 | Source content matches the reference; a loaded/unimported file still needs import to calculate results |
| Different SHA-256 | Clear affected review/results and mark **Re-import required**; preserve phase assignment and old reference until re-import |
| Missing source | Keep the path and phase, clear affected results, report that the file must be restored and re-imported |
| Unreadable or nonregular source, or change detected during hashing | Clear affected results and report the problem; do not claim a match |
| No reference hash | Report unverified/import required; never claim unchanged content |

Content checks do not rely on filename, size, or modification time. Same-size changes
with restored modification times are detected; a timestamp-only change with identical
content is not treated as different data. Hashing checks file identity/metadata before
and after reading to detect a source changing during the check.

If an imported source fails export verification, that attempt produces no completed
bundle. A failure at the final check cleans up that attempt's output folder. The GUI
invalidates the affected results and clears stale metrics from review. Other current
results remain available; a later partial export accounts for invalidated/unimported
paths in its manifest rather than exporting their old values. Restore/re-import those
files to include them again. Phase/source provenance is never silently relabeled.

Checks occur on project load/save, explicit source check, and export. There is no
continuous filesystem watcher; review panels show the last imported snapshot until
a check detects a change. Export checks are point-in-time checks, not a lock on the
acquisition files. A source can change after an export finishes; the exported hashes
identify the bytes whose results were verified at export time.

## Save protection and failure recovery

New saves publish a complete temporary file with exclusive creation. Updating the
open project requires the previously loaded/saved project SHA-256 and checks it
again before atomic replacement. Existing unrelated files, symlink destinations,
source paths (including deleted paths), and existing hard-link aliases of sources
are refused. External edits detected since the last load/save require reopening
or saving under a new name. Pending changes are retained in memory after failure.

A narrow sibling `.lock` file prevents cooperating project writers from replacing
one another. Temporary/lock files are removed after ordinary success or failure.
Writing/flush failures preserve the previous project. Atomic publication is not a
cross-process transaction with editors that ignore the lock, or a crash-durable backup.
After a crash, a leftover lock may prevent saving; verify no save is active before
removing that specific lock, or use Save As. The project does not contain the recordings
and is not a substitute for backing them up.

## Verification

Synthetic tests cover setup/phase/configuration/hash round trips, duplicate filenames,
missing/unreadable sources, byte changes despite equal size/mtime, unchanged content
with changed timestamps, malformed/incompatible projects, source/link protection,
external edits, concurrent saves, atomic failure cleanup, export-time changes, and
re-import recovery. Offscreen GUI tests exercise dialogs, save/load, failure/cancel,
busy controls, background execution, deferred close, invalidation, and stale review
clearing. Existing metric tests remain separate from project persistence tests.

On November 10, 2026, an offscreen GUI workflow used disposable copies of the seven
supplied recordings with explicit validation-only phase labels. Save/close/reopen
restored every path/phase, discovery settings, and analysis configuration; re-import
reproduced all 56 phase values. A deliberate edit to one copy blocked export and
cleared its old metrics. Saving kept the old baseline until re-import; after re-import
and save, both CSV and Excel exported seven phase rows and 118 choices with updated
hashes. Original recordings and their summary retained their hashes and modification
times. Artifacts remain under ignored `outputs/project-validation-*/`.

Native desktop file dialogs and Microsoft Excel rendering are not established by
offscreen tests. Project UI/source-state screenshots were inspected; this is workflow
and provenance verification, not new scientific validation of behavioral metrics.

Final checks on November 10, 2026: **282 tests passed**, along with Ruff lint/format,
dependency consistency, Markdown link, and diff whitespace checks.

## Known accuracy-scale update

Project format 1 remains supported. A project whose analysis configuration exactly
matches the previous session definition 2 / phase definition 1 setup can be opened
under session definition 3 / phase definition 2. Paths, phases, and reference hashes
are retained; the window visibly reports the proportion-scale update and marks the
configuration unsaved. Import is still required before export. Loading leaves the
original project file untouched; Save explicitly writes the updated configuration.
Any additional policy/profile/version mismatch still fails compatibility checks.
See [proportion correct](proportion-correct.md).
