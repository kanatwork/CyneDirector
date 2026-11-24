# Bounded clip memory and safe generation retention — verification

Historical milestone: current source-root/configuration behavior and the current
score are in the [workspace/relinking verification](2026-11-24-workspace-relinking.md).

24 November 2026, Asia/Kolkata. Local work on upstream
`efd093023c2b30410a5f11553b251e94f69e9f88`, branch
`codex/wedding-workflow-plan`. Changes remain uncommitted and unpushed. This
supersedes the **65/100** score in the [workspace/jobs report](2026-11-24-workspace-jobs.md).

## Result: 67/100

Long clips now use bounded application buffers and windowed speech decoding.
Exceeding a record/metadata limit fails the replacement without publishing partial
data. New tracked generations support dry-run inspection, verified quarantine,
interrupted-operation recovery, restore/pinning and a separate delayed purge.
Existing untracked project data remains protected.

The app remains a running prototype in early beta hardening. This closes the
implementation and synthetic verification portion of these W2 gates; it does
not certify the actual 800 GB library or arbitrary long-clip recognition quality.

| Dimension | Before | Now | Evidence / remaining gate |
|---|---:|---:|---|
| Media integrity and recovery | 22/25 | 24/25 | Bounded processing, no partial overflow publication, snapshot-safe tracked retention, archive/file verification and real kill/resume/restore. Different-path relink and physical SSD/power-loss acceptance remain |
| Finding useful moments | 18/20 | 18/20 | Active-generation retrieval survives hidden-vector crowding and retains source times. Real wedding-language join quality, reviewed selects and full-library latency remain |
| Premiere workflow | 2/20 | 2/20 | Selects interchange, exact source frames/audio layout and editing proxies still need acceptance |
| Phone operation | 6/15 | 6/15 | Existing durable commands remain working; actual paired-phone/disconnect/preview acceptance is pending |
| Setup and compatibility | 8/10 | 8/10 | Native Mac startup/GUI/real inference still pass; other hardware/clean install/packaging remain |
| Validation and delivery | 9/10 | 9/10 | 44 added regressions, 167 total; measured synthetic memory/query costs and real short inference. Representative wedding/full-run/release evidence still missing |
| **Total** | **65/100** | **67/100** | Same wedding/Premiere/phone rubric; engineering judgment, not percentage of code complete |

100/100 still requires all [build-plan](../../buildplan.md) acceptance gates:
safe real-storage recovery, useful reviewed wedding retrieval, verified Premiere
selects/relink/audio, phone-originated control and review, reconciled full run and
declared platform/release evidence. More backend code alone cannot earn those points.

## Implemented contract

- `MemoryPolicy` scales application buffers, with validated settings frozen in
  durable jobs and reported by preflight. Defaults: 256 MiB policy, 32 CLIP frames,
  5 scene images, 5 keyframe candidates, 3 occurrence indices/tag, visual writes
  ≤64 and speech vectors ≤32. Original frame dimensions above 9,437,184 pixels fail
  visual preflight; speech can still use a higher-resolution container.
- Complete metadata has byte/node/depth bounds. Default scene/transcript caps are
  8,192/20,480 records and metadata 8 MiB UTF-8. Half that byte budget is available
  to each scene/transcript working collection. Limits fail without silently dropping
  records. Existing oversized rows remain readable and are refused for processing
  before application hydration/copying. Summary input alone is capped at 4,096 chars.
- Speech uses one 180-second core PCM window plus up to two seconds of context
  on either side. Word timestamps and midpoint ownership trim overlapping windows;
  offsets stay source-relative. Temporary WAVs are registered before writing and
  removed per window. Closing/cancelling terminates the owned decoder child.
- An additive versioned catalog records new generation lifecycles and exact
  derivative paths before writes. Publication/retirement occurs in the metadata
  pointer transaction. Staged vector writers cannot mutate a published generation.
- Saved dry-run retention plans protect current, active-writer, pinned, referenced
  artifact and unfinished-job generations, two prior successes/source/stage and a
  24-hour grace period. Keep-history cannot fall below one. Legacy/untracked data
  is never automatically adopted. No startup cleanup or automatic purge was added.
- Apply validates the snapshot/workspace, archives/checksums all candidate vectors
  before deletion, deletes in pages of 64 and moves only exact registered derived
  files to quarantine. Journal ownership prevents competing partial cleanup.
  Restore verifies/recreates raw copies and pins them without moving the active
  head. Purge is a separate action with a seven-day cooling period and fresh checks.
- Retention, publication and published reads share the database RLock; maintenance
  also takes processing ownership. Composed reads can hold `read_snapshot()`.
  Published counts are paged. ANN widening caps at 256 then uses paged exact top-k
  fallback when historical rows crowd active results or Chroma cannot widen.

See [usage, limits and recovery commands](../memory-retention.md). No retention
plan was applied to an actual user project.

## Measurements

Same M4 Pro / 48 GiB, macOS 27.2.1 arm64, Python 3.11.18, torch 2.11.0,
Chroma 0.4.24, Qt 6.8.2 and FFmpeg/FFprobe 9.1. No new dependency was added.
Native tests ran with host permissions because the sandbox blocks the previously
documented CPU-feature/native-runtime checks.

The long-duration profile executes the actual visual worker loop with simulated
decode/model operations and allocated resized RGB byte buffers. It is a buffer
growth test, not hours of actual GPU inference or a real codec throughput estimate.

| Profile, 64 MiB policy | Python allocation peak | Process peak RSS | Outcome |
|---|---:|---:|---|
| 5,000 samples, 0.69 simulated hours | 6,138,515 bytes (5.85 MiB) | 44,122,112 bytes (42.1 MiB) | Published; 17 live resized images, batch ≤16 |
| 50,000 samples, 6.94 simulated hours | 6,138,515 bytes (5.85 MiB) | 53,116,928 bytes (50.7 MiB) | Published; same buffer peak and image/batch bounds |
| Dense cuts, 50,000 requested samples | 9,683,239 bytes (9.23 MiB) | 63,569,920 bytes (60.6 MiB) | Stopped at 2,048-scene cap; prior metadata unchanged, no publication |

These numbers exclude real model weights/native inference allocations. Whole-app
RSS is not capped by `processing_memory_mib`. Legacy all-results `get()` and global
GUI/search caches remain materializing APIs.

Actual FFmpeg tests preserve 1.5 seconds of leading audio offset and decode the
correct later window, with unchanged source hash. Actual cached Whisper small
CPU/int8 with a deliberately short two-second core produces two timed segments
and exactly **“On our wedding day, I promise to stand by your side.”** Max PCM was
104,596 bytes. This checks window ownership/source timing on a controlled sentence;
music, overlap, language switching and arbitrary real joins are unverified.

A real Chroma fixture with four 300-vector generations measured 12 queries before
and after quarantine. Raw rows fell **1,200 → 600**, visible active rows stayed
**300**, and restore recovered **1,200** raw rows. Paged exact scan median was
**21.27 → 14.86 ms**, observed sample p95 **36.50 → 15.64 ms**, scanning
**1,200 → 600** rows in pages of 64. These small synthetic measurements are not a
library latency SLA. Quarantine does not reclaim file bytes; SQLite/HNSW physical
shrinking is not implemented or promised.

## Executed verification

| Check | Result |
|---|---|
| Search / review regressions | 33/33 and 23/23 pass |
| Reprocessing/timing / workspace/jobs | 28/28 and 39/39 pass |
| Memory/retention / worker buffer regressions | 41/41 and 3/3 pass |
| **Total** | **167/167 pass, no skips** |
| Actual cached-model CLI | Inventory → MPS CLIP/BLIP/YOLO visuals → CPU/int8 Whisper small + CLIP speech vectors; 3 completed stages, 6 visual and 1 speech vector, attempts `[1,1,1]` after repeat |
| Real processing counters | Visual peak batch 6, one retained scene image; speech one window/104,596 PCM bytes. Temporary fixture only |
| Preservation | Generated original and `.cyne` SHA-256 unchanged; custom editor note and old raw vector preserved; current generation view correct |
| Native startup and jobs GUI | Cocoa welcome/model/main windows render, jobs dialog fits, real inventory and configured two-stage queue complete, no Qt exceptions |
| Qt/storage/FFmpeg integration | Actual temporary storage/derivatives, worker handoff and active background shutdown pass |
| Environment/static | `pip check`, compilation, script syntax and whitespace checks pass |

New regressions cover configuration/dimension/record/byte/node bounds, fixed
histories, complete batched speech, safe dense overflow, PCM cancellation/cleanup,
word joins, legacy data, grace/history/pins/job/artifact protection, stale plans,
snapshot-reader exclusion, archive copy/move/delete failures, actual process death
mid-delete with fresh-process apply/restore, symlink containment, corrupt/missing
archive rows, missing collections, writer immutability, future schemas, paged query
recall/filter/distance and counts. The native jobs GUI uses a small publication
adapter for visual/speech stages; the separate CLI test uses the real models.

The actual pipeline observed **8,969,023,488 bytes free (about 8.4 GiB)** internally.
The default **20 GiB reserve** correctly blocks production processing. Successful
temporary fixtures explicitly use 64 MiB reserve; no production policy was weakened.

Consolidated results, log hashes and source fingerprints are in the
[evidence JSON](2026-11-24-memory-retention-evidence.json). Local generated reports
are `.cache/memory-retention-verification/benchmark.json`,
`.cache/durable-verification/result.json` and `.cache/memory-*.log`. Fixture project
paths in reports were temporary and have been removed.

## Remaining work

Original wedding footage and existing user projects were not opened, moved,
renamed, transcoded or cleaned. No real wedding SSD was mounted for acceptance.
Next W2 implementation is explicit root relinking and safe configuration updates
with stable identities and preserved legacy paths. Interactive search/model
ownership, durable translation/watcher routing, independent stage versions and
thumbnail/proxy FFmpeg child cancellation remain open.

Select actual storage/backup paths with headroom, then test the longest
representative wedding clip, real languages/joins, codecs/timebases and output
costs. Long legacy Whisper translation currently fails explicitly rather than
decode an entire source. Physical SSD remount/full-disk/power-loss and full-library
storage/query behavior remain acceptance gates. Actual phone review/control and
Premiere selects/audio/relink remain W3–W5 work.
