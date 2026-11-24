# Archived engineering plan before product discovery

Superseded on 24 November 2026 after the product scope was clarified. Phone
operation of CyneDirector and its old score are historical requirements, withdrawn
from the product scope. Relative links were adjusted for this archive location.

# CyneDirector build plan — wedding footage and Premiere

Updated: 24 November 2026 (Asia/Kolkata). Product owner: Kanishkar.

This is the current execution plan. [PRD.md](../../PRD.md) defines product scope;
[CLAUDE.md](../../CLAUDE.md) describes the implementation. The February gameplan is
preserved in [docs/archive/gameplan-v3-2026-02-08.md](../../docs/archive/gameplan-v3-2026-02-08.md).

## Outcome

Make approximately 800 GB of wedding footage on an SSD searchable, turn reviewed
moments into a Premiere selects sequence, and let Kanishkar start and supervise
processing from a phone while the Mac does the work. Premiere remains the place
for multicam synchronization, creative cutting, sound, color, and final delivery.

Confirmed: Premiere is the editing app. Still to establish: phone OS, footage
mount path, total hours, camera codecs/frame rates, audio channel layouts, spoken
languages, desired film length, and backup/cache locations. These do not block
the correctness work. Do not infer languages or relationships from names.

## Baseline and current status

| Item | Evidence/status |
|---|---|
| Authoritative repository | `https://github.com/kanatwork/CyneDirector.git` |
| Restored path | `/Users/kanishkar/Desktop/The Tools/CyneDirector` |
| Audited upstream commit | `efd093023c2b30410a5f11553b251e94f69e9f88`, latest `main` observed on 24 November |
| Last upstream change | 24 November 2026, 03:39:24 IST; runtime fixes and regression tests |
| App version | `2.1.0` in `config.py`; no new version assigned by this audit |
| Previous development milestone | Phase 5.1 implemented; Phase 5.2 was next in the old plan |
| Fresh checks | 201 regressions, prior memory/retention benchmarks, native startup/jobs/configuration GUI, Qt/storage/FFmpeg integration and real cached-model processing after simulated SSD relinking pass |
| Fresh findings | Stable source resolution, saved/verified root relink and destination-update plans, atomic configuration commit and offline project preservation implemented; [latest verification](../../docs/audits/2026-11-24-workspace-relinking.md) |
| This Mac | M4 Pro / 48 GiB, macOS 27.2.1 arm64; isolated Python 3.11.18, full GUI/ML dependencies, FFmpeg/FFprobe 9.1 installed |
| Capacity | About 8.2 GiB free internally at the latest real pipeline check; default 20 GiB processing reserve correctly blocks this filesystem; wedding SSD was not mounted |
| Runtime validation | Actual CLI inventory → MPS visuals → CPU/int8 speech with workspace derivatives passes; native GUI job submission/status/queue lifecycle passes. Real SSD remount, wedding/Premiere/phone/Windows pending |

Source restoration and the native Mac environment are complete for controlled sample
testing. `setup_macos.sh`, `run.command`, and `requirements-macos.lock` record the
working setup; an in-place setup repeat passed. Optional BLIP-2/LLM and large-v3
weights were not downloaded. Full wedding acceptance and packaged delivery remain
separate gates. See [README.md](../../README.md) for launch/cache/model instructions.

## Readiness score: 67/100 (previously 38, 48, 55, 60, then 65)

This is an engineering judgment about the intended wedding/Premiere/phone
workflow, not a measured percentage of code complete or a prediction of editing
quality. Existing source receives partial credit; unverified behavior does not
receive full credit.

| Dimension | Current | Full credit requires |
|---|---:|---|
| Media integrity and recovery | 24/25 | Bounded processing, reversible retention and safe root relinking pass synthetic faults; physical SSD/full-disk/power-loss acceptance remains |
| Finding useful moments | 18/20 | Timestamped retrieval and reviewed collections meet the sample quality and latency gates |
| Premiere workflow | 2/20 | Accurate selects import, original-media relinking, audio layout, and tested export contract |
| Phone operation | 6/15 | Paired phone can submit, inspect, pause, resume, and retry a durable job; transport loss does not lose it |
| Setup and hardware compatibility | 8/10 | Reproducible setup and a documented validation matrix on supported Mac/Windows backends |
| Validation and release readiness | 9/10 | Real-media/integration tests, measured 800 GB run, diagnostics, and repeatable install artifacts |
| **Total** | **67/100** | All gates below have evidence |

100/100 means the defined workflow passes on its declared hardware, formats, and
app versions. It does not mean perfect semantic understanding or the absence of
future bugs. OCR, a new web app, automatic face naming, and autonomous final-film
editing are not requirements for that score. Re-score using the same rubric as
evidence arrives; do not award points simply for adding more code.

The relinking increment retains **67/100**: implementation and synthetic recovery
gates advanced, but the remaining integrity point still needs physical-storage
acceptance. Wedding retrieval, phone and Premiere outcomes have not yet changed.

## W0 — Recover the workspace and establish the sample

Status: source restoration/runtime, workspace configuration and capacity policy
verified on synthetic fixtures. Actual SSD/project/cache/output selections, backup
and representative wedding sample are still pending; W0 is not fully closed.

- Keep the upstream commit identifiable and work on `codex/wedding-workflow-plan`.
- Done: Python 3.11.18 arm64 `.venv`, full `requirements.txt` dependency set
  including GUI/vision/speech/face libraries, exact Mac lock, and repeatable scripts.
  Native Cocoa startup and cached inference pass on this M4 Pro.
- Done: FFmpeg/FFprobe 9.1, real generated thumbnails/proxies, Qt/storage worker
  handoff and active background-thread shutdown. Optional dependency separation
  and a clean second-machine install remain delivery hardening work.
- Use tested Whisper `small` in project settings. The first-run registry/default
  still requests large-v3; skip that extra download unless deliberately selected.
  BLIP-2, LLM summaries, and DeepL calls are outside this verification.
- Implemented: explicit pinned media/project/model/output directories, grouped
  filesystem capacity, default configurable 20 GiB reserve plus provisional output
  estimates, and per-file/stage rechecks. Jobs use cached models only; manual model
  downloads are a separate path. See [workspace guide](../../docs/workspace-jobs.md).
- Still required: select actual storage and measure wedding output costs. The
  current internal volume fails the default reserve; tests used a bounded 64 MiB
  reserve only for disposable few-second clips.
- Mount the SSD, inventory media without altering it, and verify an independent
  backup before the full run. Read originals; write derivatives to the workspace.
- Select 10–20 GB spanning the longest clip, short clips, low light, speeches,
  music, multiple cameras, duplicate basenames, different frame rates, and each
  spoken language. Sample size alone is not evidence of representative coverage.
- Record duration, codecs, frame/timebase, source timecode, orientation, audio
  streams, size, and source location. Reject unsupported formats explicitly.

Exit: reproducible launch on this Mac, identified storage destinations with
headroom, and a sample manifest. Do not start all 800 GB to discover setup errors.

## W1 — Close correctness defects before unattended processing

Status: upstream fixes plus local generation-publication and sampled-timing work.
F01/F02/F03/F04/F08 have code fixes. F06 now records observed sampled boundaries;
exact source timebase/VFR/Premiere certification remains pending. Staged visual and
transcript replacement retain the last-good generation on failure/cancellation,
with real storage and decoder tests on this Mac. Background-worker shutdown before
model unloading and Qt operation handoff now pass integration checks. Explicit
visual/speech jobs now recover at file/stage boundaries. F09 GUI semantics, fully
independent embedding/settings versions and interactive-search/model coordination
remain open. Read the [job verification](../../docs/audits/2026-11-24-workspace-jobs.md)
and [generation/timing report](../../docs/audits/2026-11-24-safe-reprocessing.md) for limits.

### W1a — Worker ownership and truthful outcomes (partially verified)

- Fix F02: capture the completed worker, retire it before advancing the queue,
  and retain ownership of every running worker until its actual termination.
- Fix F03: define pause boundaries and dispatch pending work when resumed after
  an operation finishes. Current workers do not implement actual mid-stage pause.
- Fix F05: propagate SQLite/vector-store failures; retain uncommitted batches.
- Fix F07: cancellation, unreadable media, model failure, and partial results must
  not advance completion stamps or produce unconditional success notifications.
- Share explicit per-file outcomes between manual and background processing.
  Prevent concurrent jobs from unloading the same shared models; stop and join
  background workers during shutdown as well as the foreground worker.

Exit: regression tests for two-operation handoff, pause at a boundary, disk-full
and vector-write failure, cancellation during decode/inference, and background
failure/shutdown. Confirm actual Qt lifecycle behavior in addition to isolated
tests. Completed, failed, cancelled, skipped, and interrupted counts must agree.

### W1b — Source identity and time (sampled timing/publication implemented)

Local implementation: immutable vector generations with one SQLite publication
pointer, generation-specific derivative directories, source-change checks, and
sampled cut/representative-frame timestamps. Legacy project fields/records remain
readable. Managed new generations now have explicit conservative retention with
verified quarantine/restore; untracked old data stays protected. Physical database
compaction and exact camera timebase/export acceptance are still required.

- F01: generate derivatives from unique source identity; two `C0001.MP4` files
  must never share an output. Write temporary outputs and atomically publish only
  after validation. Keep original names and camera folder structure intact.
- F04: replace shared freshness decisions with independent visual, transcript,
  transcript-embedding, translation, and proxy stage versions/fingerprints.
  Migrate old projects conservatively; an old timestamp is not proof of every
  stage's completion. Speed transcription must be eligible for later embeddings.
- F06: store actual sampled frame times, detected cut boundaries, and source
  timebase. Associate captions and objects with the sampled frame, not an evenly
  divided estimate of clip duration. Distinguish sampled precision from exact cuts.

Exit: same-basename cameras stay distinct; changed media invalidates all affected
stages; uneven synthetic cuts and real clips seek to the correct source frames.

### W1c — Settings and search truth (depends on W1b)

- F08: handle non-object JSON settings and invalid types; persist settings safely.
- F09: implement duration and match-type filtering and stable sorting over the
  full candidate set before pagination. A zero-match phrase filter returns zero.
- Invalidate result caches when metadata/generations change; include search
  options in cache identity. Keep sorted order consistent across page changes and
  grouping. Test queries with no results and no selected match types explicitly.

Exit: unfiltered counts, filtered counts, ordering, and page totals agree on a
dataset larger than one page, including while new files finish processing.

## W2 — Durable jobs, media locations, and bounded processing

Status: workspace/capacity checks, explicit durable inventory/visual/speech jobs,
bounded clip buffers/windowed speech, recoverable tracked-generation retention and
safe root/configuration updates are implemented and verified. W2 remains open for translation/watch
queues, physical compaction and broader fault/hardware/real-media acceptance. Read
the [job guide](../../docs/workspace-jobs.md), [memory/retention contract](../../docs/memory-retention.md)
and [relink/update guide](../../docs/workspace-relinking.md).

| Entity | Implemented / remaining |
|---|---|
| Media root | Stable IDs, pinned current directory plus historical aliases; same-directory relink or SHA-256 verification of all known sources for a different directory; offline inspection and sealed-copy support |
| Asset | Stable root/relative ID and preserved original metadata path; input signature is stored per job item |
| Job | Additive version-1 SQLite ledger, settings/scope snapshot, idempotency key, durable state/control, lease/heartbeat |
| Job item/stage | Attempts, input signature, state, elapsed/error/result; file/stage publication checkpoint in existing metadata transaction |
| Artifact | New exact derivative files registered before writing; additive generation/pin/quarantine catalog, verified archive/file checksums, restore and explicit delayed purge. Legacy/untracked data protected |
| Event | Persistent monotonic cursor, timestamp, job/item, kind/detail; status counts and current file/stage |

Done in this increment:

- Qt/AI-free workspace/ledger/orchestration imports, shared `AppProcessor`, lazy
  adapters to the existing inference algorithms, and GUI/CLI entry points. Moving
  all algorithms out of QThread classes remains a later refactor.
- Persist the full configured GUI visual/speech scope before execution, including
  stage-specific selections. Duplicate CLI submissions deduplicate; explicit new
  request keys/GUI force analysis retain the prior job history.
- Kernel processing ownership, a project process lock for embedded Chroma, live
  leases, stale-owner fencing, actual kill/restart and heartbeat tests. A detached
  runner survives launcher exit; there is no boot/login service yet.
- Keep the last published generation on failed/cancelled replacement. A metadata
  checkpoint commits with its generation pointer; a publication-before-ledger
  crash reconciles without repeating inference. Clearing/superseding invalidates
  that checkpoint. No cross-store distributed transaction is claimed.
- Missing/replaced source/output roots wait without recreating mounts; low space
  waits before models; cancellation prevents uncommitted publication; failed items
  retry without repeating completed work. Source changes require a new revision.
- Inventory with FFprobe precedes expensive stages when selected. Actual CLI
  cached inference plus workspace thumbnails/proxies passes on this Mac. Current
  stages bundle visual models/proxies and bundle speech/accuracy embeddings.
- Durable progress reports real attempts, elapsed/media seconds, heartbeat,
  events and capacity evidence. ETA stays null until calibrated throughput exists.
- Explicit frame/scene-image/keyframe/tag/vector/metadata bounds; overflow fails
  without publishing or losing prior data. Default 256 MiB policy scales buffers,
  not model/native RSS. Flat 5,000/50,000-frame profiles measured the same 5.9 MiB
  Python buffer peak; dense cuts stop safely at the configured record cap.
- Windowed speech uses one 180-second PCM core plus small overlap. Actual word
  timing owns joins; generated offset audio and cached Whisper checks pass. Native
  model quality at real long wedding-language joins remains an acceptance gate.
- Saved dry-run retention plans, active/recent/pinned/job/artifact protection,
  verified vector quarantine before deletion, exact-file moves, interrupted apply
  recovery, restore/pin and separate seven-day purge. No actual user cleanup run.
- Paged counts and capped ANN widening with bounded exact fallback preserve active
  retrieval amid hidden generations. Synthetic 1,200 → 600 raw rows kept 300 visible
  rows and reduced scan cost; restore recovered all 1,200. No physical shrink claim.
- Saved configuration plans/revalidation, revision and source-membership fencing,
  single atomic JSON commit, process-death-before/after recovery, and configuration
  locking shared with submission. No job/vector/metadata path rewrite is needed.
- Stable legacy source keys resolve at IO boundaries across FFprobe, visual/speech,
  derivatives and GUI playback/technical metadata. Resubmission at the new path
  deduplicates; paused stages and publication reconciliation survive a relink.
- GUI background preview/apply and local `workspace inspect/plan/status/apply`;
  reserve/model/output updates and CLI root additions. New outputs use new locations;
  pinned old outputs stay eligible for verified retention/restore when online.
- Offline media remains in the tree and explicit project saves retain custom `.cyne`
  fields. Original footage, existing metadata/vectors and user files are not moved.

Remaining before W2 exit:

- Validate actual long-clip model/native peak memory, speech join quality and full
  library query/storage costs. Current 6.9-hour profiles simulate decode/models;
  real inference checks use short generated media. Oversized metadata fails safely.
- Measure quarantine space at wedding scale; design any physical SQLite/HNSW
  compaction separately. Retention is explicit CLI maintenance, not an automatic quota.
- Physically accept SSD/exFAT/APFS remount and verified backup-copy workflows.
  Source relinking is implemented; project/database relocation, existing derivative
  directory relocation and cache copying are separate unimplemented migrations.
- Coordinate interactive search with model ownership; route transient watcher and
  translation paths through durable services; separate embedding/proxy stage versions.
- Add cancellation ownership for thumbnail/proxy FFmpeg children (speech decoder
  ownership now passes), physical SSD remount/full-disk/power-loss acceptance, and
  automatic interrupted-run dispatch if needed.

Exit still requires these remaining gates plus a representative real-media pilot;
passing synthetic restart tests does not certify unattended 800 GB processing.

## W3 — Phone prompts and observable local jobs

Status: local JSON job/control foundation implemented; actual phone pairing,
transport-loss acceptance, contact sheets and preview delivery remain unverified.

Architecture:

```text
Phone / ChatGPT
    -> existing authenticated connection to this Mac
    -> Codex invokes typed local commands
    -> shared processing service + persistent job database
    -> SSD originals (read) / chosen workspace (write)
    -> structured status, events, contact sheets, and export files
```

Implemented through `cyne.command` / `python -m cyne_cli`: configure, preflight,
submit, start, run, list, status, events, pause, resume, cancel and retry-failed.
Inventory is a submitted stage. These are local commands, not proof of phone
acceptance. Search, collections, contact sheets and export are still proposed CLI
surfaces. See [exact usage](../../docs/workspace-jobs.md), including GUI/CLI ownership.

Progress must include stage, current source, done/total counts, media seconds,
failures, heartbeat, checkpoint, elapsed time, destination capacity, and output
paths. Show ETA only when sufficient measured throughput exists. Repeated phone
prompts must not create duplicate jobs. A worker process must outlive a phone/chat
disconnect; do not make the conversation transport its process supervisor.

Use the [phone setup guide](../../docs/phone-control.md). Start with chat-visible status
and saved low-resolution contact sheets. Continuous phone video review is a later
feature requiring its own tested preview delivery. No custom internet-facing API
or mobile-app rewrite is required for this milestone.

Exit: from the actual paired phone, submit a sample job, close/reopen the mobile
app, recover status by job ID, pause/resume, and retry one deliberate failure.
Record the tested phone OS/app version. The footage remains available to the Mac;
model downloads and any explicitly chosen cloud translation are separate traffic.

## W4 — Wedding discovery and reviewed collections

Status: not started; depends on W1/W2; CLI surfaces use W3.

- Timestamped speech transcription with preserved original text and language.
  Test the real languages, overlapping voices, vows, music, and long silences.
  Translation is optional and kept separately; do not substitute it for the source.
- Give multilingual dialogue retrieval a measured embedding strategy. Current
  dialogue vectors use CLIP text encoding, are accuracy-mode only, and lack a
  proven wedding-language quality baseline. Do not assume semantic parity across
  languages from the existence of a transcript.
- Provide editable event labels and virtual collections for the actual wedding
  schedule: preparations, ceremony/rituals, speeches, portraits, reception, etc.
- Persist selects with asset ID, source generation, in/out, rationale, review
  status, user note, and ordering. Every suggestion must link back to source media.
- Start with manual person labels and reviewed candidate matches. Automatic face
  clustering can follow if person search proves valuable; no automatic identity
  claims. OCR remains deferred unless signage/text becomes an actual need.
- Compare at least 30 human-authored queries with manually identified moments.
  Proposed quality gate: useful reviewed result in the first five on at least 80%
  of queries; include missed moments and false positives in the report.

Exit: Kanishkar can find, preview, correct, and save moments for at least one
wedding event; search latency is measured against the actual sample/library.

## W5 — Premiere selects and proxy handoff

Status: not started; depends on accurate source identity/time and W4 selects.

- Start with a documented selects manifest (JSON/CSV) and reviewable contact
  sheet. These are audit/fallback outputs, not promises that Premiere imports CSV.
- Implement a narrow, tested Premiere-compatible sequence export. Legacy Final
  Cut Pro XML (`xmeml`) is the first candidate to validate against the installed
  Premiere version. Modern Final Cut Pro `.fcpxml` is not directly importable into
  Premiere; do not label it an equivalent format. [Adobe import guidance](https://helpx.adobe.com/premiere/desktop/organize-media/import-files/migrate-from-final-cut-pro-x.html)
- Keep the initial exchange to straight cuts, explicit sequence settings, source
  in/out ranges, ordered clips, and required audio tracks. Retain a portable source
  map, frame/timebase information, and separate source versus sequence timecodes.
- Test 23.976/24/25/29.97/50/59.94/60 fps where present, drop-frame conventions,
  rotated clips, duplicate names, multi-channel audio, and clips crossing minutes.
  Handle variable-frame-rate media explicitly rather than silently rounding it.
- For the first edit, prefer Premiere-created editing proxies. CyneDirector's
  current 720p H.264 files are analysis/preview derivatives until attachability,
  channel mapping, duration, and source linkage are verified. Keep analysis and
  editing proxy profiles distinct. [Adobe proxy attachment](https://helpx.adobe.com/premiere/desktop/organize-media/ingest-proxy-workflow/attach-proxies-to-full-resolution-media.html)
- Validate imported starts/ends against original frames and audio; save and reopen
  the Premiere project, relink originals after a drive remount, and render a short
  test from originals. Do not modify the main wedding project for this test.

Exit: a reviewed collection opens as a useful selects sequence in Premiere with
correct source frames, audio, offline/relink behavior, and an exchange report.

## W6 — Scale the same workflow to the wedding library

Status: not started; depends on W0–W5.

| Step | Required evidence before advancing |
|---|---|
| Representative 10–20 GB | End-to-end index/search/select/Premiere import; actual model/codec behavior |
| Approximately 100 GB | Measured throughput, bounded memory, storage growth, restart/retry and SSD reconnect |
| Approximately 800 GB | All sources accounted for; complete/failed/skipped ledger reconciles; selective retries work |

Estimate processing time from total media hours and observed stage throughput,
not GB alone. Estimate derivative size from sample output bytes per media hour,
with an explicit reserve. Schedule stages to preserve capacity and begin reviewing
finished events while later events are processing.

Exit: no unexplained missing sources, false-success records, cross-camera proxy
links, or timecode drift. All unresolved failures are visible. A phone-originated
request produces a reviewed Premiere selects sequence from this real library.

## W7 — Reproducible delivery and the remaining points

Status: dependency lock/setup scripts and core Mac integration evidence complete;
packaging, other hardware, and release acceptance pending. Personal editing can
begin after W5/sample acceptance; broad beta distribution waits for the platform/release evidence below.

- Record a known-good dependency set and startup diagnostics; package a usable
  Mac artifact and verify the declared Windows CUDA/CPU path on real hardware.
  Document unsupported formats/backends instead of implying blanket support.
- Convert isolated findings into regression tests of corrected behavior. Add real
  SQLite/vector integration, actual Qt worker lifecycle, media fixtures, export
  validation, and a small representative hardware/codec matrix.
- Publish measured query latency (proposed p95 <3 seconds on the declared test
  library), retrieval quality, memory/storage budgets, and full-run reconciliation.
- Provide recoverable project backup/restore, a diagnostics bundle, and repeatable
  install/release artifacts. Re-validate the core path on the installed build.
- The old auto-updater, OCR, extensive face UI, and theme polish remain backlog.
  Add the updater after the release/rollback process is reliable; it does not
  outrank completion of this wedding workflow.

100-point acceptance: every rubric row has direct evidence, all P1 findings are
closed, every claimed command works from the paired phone, and Premiere imports
and relinks the real selected footage. Automated rough-cut suggestions can follow
as editable proposals. Creative approval stays with the editor.

## Next implementation prompt

```text
Read PRD.md, buildplan.md, docs/workspace-relinking.md, docs/memory-retention.md
and the latest relinking audit. Preserve project formats, active/legacy data,
stable source keys and root IDs, bounded processing, verified configuration/retention
plans and the 201 passing regressions. Use the installed .venv and cached core models.
Next coordinate interactive search with inference/model ownership and cancellation
of thumbnail/proxy FFmpeg children. Prevent active searches and background/manual
workers from unloading each other's models; keep durable stage completion truthful.
Test search during processing, ownership loss, cancellation and shutdown with real
Qt/subprocess checks. Durable translation/watcher routing and independent stage
versions remain W2 gates. Do not physically compact databases or move project/cache/
derivative directories without a separately reviewed recovery contract.
Keep original media read-only. Do not run 800 GB, automatically apply retention,
move source files, or weaken capacity checks to make a sample run. Select actual
SSD/workspace/cache paths and backup; inventory a representative wedding pilot
only after preflight. Verify real languages/codecs/timebases before Premiere work.
Keep the actual CLI model pipeline, native jobs GUI, Qt lifecycle and regressions
passing. Phone pairing/preview and Premiere selects remain separate acceptance.
```
