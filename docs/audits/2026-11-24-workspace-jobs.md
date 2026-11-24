# SSD workspace and durable jobs — verification

Historical milestone: the current score and remaining gates are in the
[memory/retention verification](2026-11-24-memory-retention.md).

24 November 2026, Asia/Kolkata. Local work on upstream
`efd093023c2b30410a5f11553b251e94f69e9f88`, branch
`codex/wedding-workflow-plan`. Changes are uncommitted and have not been pushed.
This supersedes the **60/100** score in the
[Mac runtime report](2026-11-24-macos-runtime.md). Earlier generation/timing and
Mac environment evidence remains applicable within its stated limits.

## Result: 65/100

Workspace/capacity checks and explicit durable inventory/visual/speech jobs are
implemented and verified on this Mac. The configured native GUI queue and local
JSON CLI share orchestration and the existing inference algorithms. The project
remains a running prototype in early beta hardening, ready for a controlled pilot
after actual storage/backup selection and capacity preflight.

| Dimension | Before | Now | Evidence / remaining gate |
|---|---:|---:|---|
| Media integrity and recovery | 20/25 | 22/25 | Pinned separated roots, capacity gates, persistent items, source/lease fencing, real process kill/restart, publication-before-ledger reconciliation and legacy path/data preservation. Bounded memory, retention and relinking remain |
| Finding useful moments | 18/20 | 18/20 | Actual model pipeline passes; wedding-language retrieval quality/latency and reviewed collections still need acceptance |
| Premiere workflow | 2/20 | 2/20 | No tested selects interchange or editing-proxy certification yet |
| Phone operation | 4/15 | 6/15 | Typed durable submit/status/events/control and detached execution work locally; actual phone pairing/disconnect/output review remains unverified |
| Setup and compatibility | 8/10 | 8/10 | Existing M4 Pro runtime remains working; physical SSD remounts, other hardware, clean install and packaging remain |
| Validation and delivery | 8/10 | 9/10 | 41 new regressions; 123 total. Actual cached-model CLI pipeline and native jobs GUI/Qt integration pass. Real-library/release gates remain |
| **Total** | **60/100** | **65/100** | Same wedding/Premiere/phone rubric; engineering judgment, not percentage of code complete |

Full credit still requires the [build-plan gates](../../buildplan.md): bounded
processing/recovery/storage on representative media, useful reviewed wedding
retrieval, tested Premiere frames/audio/relink, actual phone-originated jobs and
preview review, full-run reconciliation, and declared platform/release evidence.
This increment does not certify unattended 800 GB processing.

## Workspace and capacity contract

`core/workspace.py` adds a version-1 `_cyne_db/workspace.json` sidecar. All media
and destination directories must already exist. Media roots and write locations
are disjoint, including project/database and model-cache destinations. Canonical
paths validate containment and reject source/output symlink escapes. Directory
identity and available Mac volume UUID pin the selected locations.

New thumbnails/proxies/logs use a workspace-ID/kind/generation namespace under
the chosen output root. Existing project data and artifact pointers are not moved.
On Mac, directory creation is anchored to an opened directory descriptor and
rejects symbolic-link substitution; managed FFmpeg helpers cannot recursively
recreate a missing output path. Tests simulate a root disappearing during creation
and verify that its former path remains absent. Missing/replaced locations wait
instead of deliberately creating an internal replacement for a missing SSD.

Preflight reads FFprobe format/streams: duration, codecs, rational frame rates,
timebase, tags/timecode when present, rotation information, audio channel layouts
and related source metadata. These inventory fields do not change the sampled
scene-timing precision or certify Premiere timecode.

Budgets sum project/model/output demands by actual filesystem, add one configurable
reserve per filesystem, and include provisional new-index/speech/thumbnail/proxy
and temporary-output estimates. The default reserve is **20 GiB**. Full remaining
scope is checked before models; each file/stage gets a fresh headroom check.
Existing generations remain and already consume reported free space. Estimates
are not enforced storage quotas or a measured wedding profile; CRF proxy size and
other processes can exceed them. See [exact assumptions](../workspace-jobs.md).

The real integration preflight observed **9,262,538,752 bytes free (about 8.6 GiB)**
on the shared internal filesystem. Its default-reserve requirement was
**21,491,613,696 bytes**, and preflight correctly returned false. The successful
few-second synthetic run used a **64 MiB test-only reserve**. No production policy
was weakened and no real SSD was selected/configured for the user.

Jobs use cached models only through explicit Hugging Face/Whisper local-only
options and the chosen cache. Missing YOLO weights cannot start a job download.
Manual/first-run model downloading remains separate. Existing cache/YOLO files
are not migrated; the tested setup still uses the previously downloaded weights.

## Durable execution contract

`core/jobs.py` creates an additive version-1 `_cyne_db/jobs.sqlite3` ledger with
WAL/full synchronous commits, asset/job/item/event tables, settings snapshots,
idempotency keys, source size/mtime signatures, attempts, errors/results, elapsed
time, desired state, leases and heartbeats. Future schemas fail closed. This is
not a destructive migration of `.cyne`, settings, metadata.db or Chroma.

Asset IDs use root ID and relative path. Registration preserves existing metadata
keys (including Mac `/var` versus `/private/var` and symlink aliases), preventing a
canonicalization change from silently splitting the existing index. Repeated
identical CLI submissions return the same ID. Conflicting reuse of a request key
fails. Deliberate new request keys/GUI Force analysis create new jobs while keeping
the prior history. Configured GUI Start workflow also records a new explicit scope.

`JobRunner` executes serially through lazy `AppProcessor` adapters to the existing
visual/transcription algorithms. Its core imports need no Qt/ML; actual inference
still uses those existing Qt-dependent algorithm classes. The configured GUI
persists all visual/speech stage-specific selections before execution. The jobs
dialog submits inventory directly and shows persistent status/control. Existing
worker paths also enforce workspace/capacity checks.

Completed file/stages stay complete. A publication context adds item/settings/
signature/generation checkpoint metadata to the **same SQLite transaction as the
published generation pointer**. If the process dies after that publication but
before ledger completion, restart recognizes the exact stamp and reconciles
without repeating inference. A cleared/superseded generation invalidates it.
Source changes relative to the job snapshot prevent publication, even if they
happen before the worker takes its own input signature. Old vectors/metadata stay
valid on failure/cancellation. No SQLite/Chroma distributed transaction is claimed.

A local OS lock serializes processing owners, including across job/legacy worker
processes. A project process lock protects embedded Chroma from another process
opening a GUI-owned project. Job leases/heartbeats fence stale ledger writes;
publication checks the live lease/control/source predicate. The OS retains its
processing lock while the old process lives, even if its lease expires.

Pause finishes the current file/stage before stopping dispatch. Cancel requests
worker stop and prevents uncommitted publication. Active FFmpeg subprocess
termination is not implemented; publication remains gated after it returns.
GUI quit pauses and joins work; closing the dialog leaves it running. A detached
CLI runner survives its launcher exiting, without a chat transport supervising it.
After death, wait for the 15-second lease, then explicitly run/resume. There is no
boot/login daemon or automatic restart dispatcher.

Missing/replaced drives and low capacity leave work pending in `waiting_media`
or `waiting_capacity`; project contention uses `waiting_resource`. Mid-stage
drive loss defers the unfinished item. Corrupt inputs fail individually and other
valid files proceed. Retry only resets failed/cancelled items; source revisions
need new scope. Status has truthful stage counts, attempts/current file, heartbeat,
errors, elapsed time and monotonic events. Unique completed media seconds and
stage-media seconds are separate. ETA remains null.

## Executed checks

Same Mac as the previous report: Apple M4 Pro / 48 GiB, macOS 27.2.1 arm64,
Python 3.11.18, Qt 6.8.2, torch 2.11.0, Chroma 0.4.24, FFmpeg/FFprobe 9.1.
No new Python dependency was required; `pip check` remains clean. Host permissions
were used for native Qt/MPS checks because of the previously documented sandbox
CPU-feature limitation.

| Check | Result / limits |
|---|---|
| Search regressions | 33/33 pass; isolated stubs |
| Review regressions | 23/23 pass; injected settings/write failures |
| Safe reprocessing/timing | 28/28 pass; real persistent Chroma and generated uneven-cut decoder checks included |
| Workspace/job regressions | **39/39 pass, no skips**; real SQLite/filesystem/processes and selected real Chroma publications |
| Actual CLI model pipeline | Pass: generated clip + locally synthesized speech → inventory, real MPS CLIP/BLIP/YOLO visual indexing, CPU/int8 Whisper small, accurate transcript embeddings, workspace thumbnail/proxy |
| CLI JSON / repeats | Actual inference stdout parses as JSON; completed counts 3; six visible visual vectors, one transcript vector; attempts remain `[1,1,1]` on repeat |
| Preservation | Synthetic original and `.cyne` SHA-256 unchanged; editor note and old raw vector retained; old vector hidden from the new published view; new derivatives are in selected output |
| Native jobs GUI | Cocoa dialog fits display, real inventory submission completes and worker retires; configured primary visual/speech queue preserves distinct file scopes and completes both items with a small publication adapter double |
| Existing Qt/runtime | Real SQLite/Chroma/FFmpeg derivatives, worker handoff/background shutdown and native `main.main()` startup pass |
| Static/environment | Compilation, launch-script syntax, dependency consistency and whitespace checks pass; existing background-indexer CRLF is tolerated explicitly |

Added regressions cover same-filesystem demand summing/reserve, the 20 GiB default,
offline/replaced roots, descriptor-creation race, helper non-recreation, symlink
escape/ledger rejection, no unknown-project writes, exclusive configuration,
snapshot/dedup/conflict, concurrent submissions, live/stale leases, heartbeat,
pause/reopen/resume, cancel/retry, failed-item-only retries, source changes,
individual corrupt input handling, monotonic event cursors, cross-process locks,
actual child SIGKILL/restart, launcher-exit survival, future schema rejection,
stage-specific selection, settings-edit exclusion during active processing, rejection of generated workspace
proxies by watcher callbacks, explicit
new-analysis history and atomic-publication
reconciliation/invalidation.

The actual CLI fixture transcribed **“On our wedding day, I promise to stand by
your side.”** exactly. This is not a wedding language/overlap/music benchmark or a
throughput estimate. Optional LLM weights were absent; summary fallback stayed
local/cached-only. Face, BLIP-2, large-v3 and DeepL are outside this increment.

Local reports/logs/screenshot are under `.cache/durable-verification` and
`.cache/*current.log`; the consolidated
[evidence JSON](2026-11-24-workspace-jobs-evidence.json) records outcomes, hashes,
and source fingerprints. Generated project/media/output trees were temporary and
removed after testing; their former paths in reports are evidence, not live media.

## Preservation and next gates

No original wedding footage was read, copied, moved, renamed, overwritten or
transcoded. No existing user project was opened. `/Volumes` contained Macintosh
HD and Recovery only. All model/media tests used generated or packaged fixtures;
this Mac's real wedding SSD and backup were not available for acceptance.

Remaining W2 work:

- Explicit long-clip memory bounds and measured peak/resource costs; scene images,
  keyframe/tag/transcript structures still grow with input in existing algorithms.
- Snapshot-safe generation/artifact retention, compaction and query-cost benchmarks.
- Different-path root relinking, editable configuration/cache migration and physical
  SSD remount/full-disk/filesystem/power-loss tests. Version 1 pins its configuration.
- Independent embedding/proxy/settings/model stage versions; durable translation/
  automatic watcher routing; interactive search/model ownership coordination.
- FFmpeg child cancellation and desired-state recovery/dispatch on system restart.

Actual phone acceptance, contact sheets/preview delivery and Premiere selects/
audio/timebase/relink remain later gates. Current preview proxies are not certified
Premiere editing proxies. Read the updated [build plan](../../buildplan.md) and
[usage guide](../workspace-jobs.md) before choosing the real SSD pilot.
