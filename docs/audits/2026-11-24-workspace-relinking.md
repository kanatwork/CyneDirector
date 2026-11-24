# Safe SSD root relinking and workspace updates — verification

**Product-scope correction:** the user later clarified that phone use means Codex
for development. Phone-product requirements and the 67/100 rubric below are
historical, not the current product definition. Technical verification remains
valid. See [product discovery](../product-discovery.md) and the [active plan](../../buildplan.md).

24 November 2026, Asia/Kolkata. Local work on upstream
`efd093023c2b30410a5f11553b251e94f69e9f88`, branch
`codex/wedding-workflow-plan`. Changes remain uncommitted and unpushed. This is
the current audit; the [memory/retention report](2026-11-24-memory-retention.md)
remains historical evidence for its measured buffer/query profiles.

## Result: 67/100, unchanged

Safe source-root relinking and workspace configuration updates are implemented
and verified on disposable Mac fixtures. The actual cached-model CLI completes
after its source root is renamed and its future output destination is changed.
The native GUI previews/applies the same update in a background thread, plays the
source at its new location and preserves offline files/custom project fields on Save.

This advances W2 implementation without awarding points for code alone. The last
integrity point still needs physical SSD/full-disk/power-loss acceptance; real
wedding retrieval, phone operation and Premiere handoff have not gained evidence.
The project remains a running prototype in early beta hardening.

| Dimension | Before | Now | Evidence / remaining gate |
|---|---:|---:|---|
| Media integrity and recovery | 24/25 | 24/25 | Stable IDs/legacy keys, verified relinks, atomic configuration revisions, resumed stages and process-death recovery now pass. Physical SSD/backup/power-loss gate remains |
| Finding useful moments | 18/20 | 18/20 | Existing retrieval and real sample inference stay working; wedding-language/long-join quality and reviewed collections remain |
| Premiere workflow | 2/20 | 2/20 | Source relinking here is app storage resolution, not Premiere sequence/media interchange acceptance |
| Phone operation | 6/15 | 6/15 | Local maintenance/job JSON commands exist; actual paired-phone/disconnect/preview acceptance remains |
| Setup and compatibility | 8/10 | 8/10 | This Mac remains verified; physical external volumes, other hardware, clean install and packaging remain |
| Validation and delivery | 9/10 | 9/10 | 34 new regressions, 201 total, native GUI and real relocated-source inference pass. Real-library/release evidence remains |
| **Total** | **67/100** | **67/100** | Same wedding/Premiere/phone rubric |

The [build plan](../../buildplan.md) defines 100/100 by accepted workflow outcomes,
not a percentage of implementation. Original footage, actual user projects and
retained user generations were not opened, moved, renamed, transcoded or cleaned.

## Implemented contract

`workspace_changes.py` provides `inspect`, saved `plan`, `status` and `apply`.
Plans carry current-config/source-membership fingerprints, a proposed complete
configuration, checked root identities, known-source signatures/content hashes and
a whole-plan checksum. A stale, corrupt, cancelled or failed plan does not commit.

Workspace/root IDs and root-relative asset IDs stay stable. The configuration
gains an additive revision, historical root aliases and source bindings. Existing
metadata/vector keys, generation catalog sources, job scopes/payloads/settings,
attempts/checkpoints and `.cyne` files are not mass-rewritten. A context-bound IO
resolver and database source-key normalization bridge stored identity to physical
files. An old mount path resolves through the pinned current root even if a wrong
file later appears at the old location. Source-key caches invalidate on atomic
configuration replacement.

Same-directory relinks require the pinned volume UUID/inode (device/inode where
UUID is unavailable) and unchanged known signatures. Different-directory copies
require SHA-256 comparison of every project-known source, preserving size/mtime
too. Hash reads use 4 MiB buffers and can be cancelled. If the original is offline,
previously sealed hashes are required; unsealed or mismatched copies are rejected.
No filename-only matching or equal-sized-file shortcut was introduced. Relative
camera folders and duplicate basenames stay distinct. Conflicting existing keys
are preserved and reported rather than silently merged.

Configuration updates support future output/model destinations, reserve changes
and additional media roots. Active processing ownership excludes updates; a
configuration lock also serializes job submission. Apply checks membership and
target identity/signatures/hashes again, then uses one fsynced temporary JSON →
atomic configuration replacement, with parent-directory fsync on the tested Mac.
No cross-store migration can remain half-applied. Status recognizes a committed
update after process death, and repeated apply is idempotent.

Old output locations remain pinned in `output_history`; existing derivatives stay
in place. New writes use the new destination. Retention can inspect/quarantine/
restore across old/new roots and restore an already quarantined generation after
a destination update. Missing historical output protects its data and does not
block unrelated new output. A configuration revision invalidates an unapplied
retention plan. No physical compaction, source copy or model-cache migration occurs.

The native **Workspace & Jobs** dialog offers background preview/apply, source-root
selection and optional content-hash sealing. It retains the exact existing reserve
when relinking without a reserve edit and rejects a stale configuration editor.
Closing verification, Escape and parent-app shutdown request cancellation and
retain/join the verifier until its thread retires. A GUI-applied
change stops the old watcher until project reopen. Primary explicit jobs/playback
use the current location immediately. The tree retains offline entries, and Save
merges supported file-list changes into existing custom `.cyne` data atomically.

Read the [complete usage/recovery guide](../workspace-relinking.md), including
same-directory versus copied-drive verification, source coverage and limitations.

## Executed checks

Same M4 Pro / 48 GiB, macOS 27.2.1 arm64, Python 3.11.18, Qt 6.8.2,
torch 2.11.0, Chroma 0.4.24 and FFmpeg/FFprobe 9.1. No new dependency was added.
Host permissions were used for native/model checks because of the previously
documented sandbox CPU-feature limitation.

| Check | Result |
|---|---|
| Search / review | 33/33 and 23/23 pass |
| Reprocessing/timing / workspace/jobs | 28/28 and 39/39 pass |
| Memory/retention / worker buffer limits | 41/41 and 3/3 pass |
| New workspace changes | **34/34 pass** with real SQLite/Chroma/filesystem and selected real subprocesses |
| **Total** | **201/201 regressions pass, no skips** |
| Actual relocated-source CLI | Root renamed by the disposable fixture, then app CLI plan/apply changes location/output before pending job resumes; inventory → real MPS CLIP/BLIP/YOLO → CPU/int8 Whisper small + CLIP speech vectors completes |
| Preservation/repeats | Generated original and `.cyne` SHA-256 unchanged; custom editor field and old raw vector remain; source metadata keys and asset/job payload unchanged; repeated apply/new-path submission deduplicate; attempts stay `[1,1,1]` |
| Actual processing outputs | 6 visible visual vectors, 1 speech vector, thumbnail/proxy in the new chosen output; original source key remains the only metadata row |
| Native configuration/jobs GUI | Cocoa dialog fits; real inventory and configured queue complete; background preview/apply succeeds; original-key playback and real technical FFprobe use new source path; offline Save retains files/custom fields, reserve is preserved and stale-editor/Escape/shutdown checks pass |
| Native startup and Qt integration | Welcome/model/main windows render; no Qt exceptions; actual temporary storage/FFmpeg, operation handoff and active background shutdown pass |
| Static/environment | Compilation, shell syntax, whitespace, CLI help and `pip check` pass |

New regressions include same-directory moves, wrong-drive content with identical
size/mtime, offline sealed/unsealed copies, changed revisions, missing relative
folders, duplicate camera basenames, removed legacy aliases, within-root symlinks,
symlink escape, ambiguous metadata rows, stale config/membership/targets, exact
reserve validation, output/model/root additions, historical-output retention and
restore, processing/submission exclusion, failed atomic replacement, corrupt/
symlinked journals, cancellation, direct transcript save after relink, paused-job
resume and publication-before-ledger reconciliation without repeated inference.

Two tests kill a real child before or after the configuration replacement and
retry apply from a fresh CLI process. The old or new whole configuration remains
readable; original fixture bytes stay unchanged. These are process-crash tests,
not physical power-loss certification. The native queue test uses a small
publication adapter; the separate CLI test uses the actual cached models.

The real CLI again transcribed **“On our wedding day, I promise to stand by your
side.”** exactly. Its application counters stayed within the earlier policy
(visual batch peak 6; one speech PCM window, 104,596 bytes). This is a short
generated fixture, not real wedding throughput or long-clip quality acceptance.

The latest real pipeline observed **8,816,930,816 bytes free (about 8.2 GiB)** on
the internal filesystem. The production **20 GiB reserve** correctly blocks it.
Successful processing used a small explicit test-only reserve; production defaults
were not weakened. No real wedding SSD was available for this acceptance.

Results, log/source fingerprints and the native screenshot hash are recorded in
the [evidence JSON](2026-11-24-workspace-relinking-evidence.json). Local reports are
`.cache/durable-verification/{result,gui}.json`, `.cache/mac-verification/startup.json`
and `.cache/relink-*.log`. Fixture paths were temporary and have been removed.

## Remaining gates and next work

The app does not move the project/database, migrate existing derivative directories
to a different mount path, copy model caches, remove referenced roots or merge
conflicting existing assets. Old derivatives require their pinned original output
location online. Source-root relinking is independent of those later migrations.
Seals cover known project sources, not all unknown footage or a complete SSD backup.

Next implementation: coordinate interactive search/model ownership and owned
thumbnail/proxy FFmpeg cancellation. Durable translation/watcher routing,
independent embedding/proxy/settings versions and interrupted-run dispatch remain
W2 work. A real SSD/backup, representative wedding sample, longest-clip language/
memory/output tests and physical remount/full-disk/power-loss acceptance are still
required before an unattended 800 GB run. Actual phone review/control and Premiere
selects/audio/frame/relink acceptance remain W3–W5 gates.
