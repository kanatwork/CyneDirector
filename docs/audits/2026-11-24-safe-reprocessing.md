# Safe reprocessing and sampled scene timing — verification

24 November 2026, Asia/Kolkata. Local implementation on top of `efd0930`.
This supersedes the [48/100 reassessment](2026-11-24-efd0930-reassessment.md).
Changes remain local; no release or GitHub push is implied.

Historical score snapshot. The subsequent [Mac runtime verification](2026-11-24-macos-runtime.md)
raises current readiness to **60/100** and closes the setup/startup/inference and
background-shutdown checks listed as pending below.

## Result: 55/100 (previously 48/100)

| Dimension | Before | Now | Evidence for the change |
|---|---:|---:|---|
| Media integrity and recovery | 16/25 | 19/25 | Staged generations, atomic metadata publication, failure/cancel/reopen coverage |
| Finding useful moments | 15/20 | 17/20 | Uneven sampled boundaries and caption-frame times verified, including real decoding |
| Premiere workflow | 2/20 | 2/20 | No Premiere interchange yet |
| Phone operation | 4/15 | 4/15 | No durable job commands or actual pairing verification yet |
| Setup and compatibility | 5/10 | 6/10 | Python 3.9 import fix and native Apple Silicon storage/decoder checks |
| Validation and delivery | 6/10 | 7/10 | 28 new checks; all 82 tests in the three specified suites pass |
| **Total** | **48/100** | **55/100** | Same workflow rubric; not a percentage of code complete |

## Safe reprocessing contract

`core/generations.py` introduces immutable vector generations. The standard
visual and transcription workers write through a per-file staged view:

1. Snapshot the current metadata and source size/mtime-nanosecond signature.
2. Write replacement vectors using unique generation IDs; keep metadata changes
   private to the stage. Readers continue to select the prior published generation.
3. Validate cancellation/error state, unchanged source, and no competing stage
   publication. Commit new metadata, generation pointer, and source signature in
   one SQLite transaction. Required write failures propagate.
4. Generation-aware vector readers expose only the generation selected by their
   SQLite snapshot. Candidate searches widen past hidden generations when needed.

No SQLite/Chroma distributed transaction is claimed. If a vector write or metadata
commit fails, the old pointer and old records remain usable; abandoned vectors
stay hidden. Reopening reads the persistent publication pointer. Source deletion
or replacement during processing prevents publication. Concurrent publication of
the same stage is rejected instead of silently overwriting the winner.

The source files are never modified. Existing project JSON fields and legacy
vectors without generation metadata remain readable. Successful processing adds
`visual_generation` or `transcript_generation`, the stage source signature, and
`vector_publication_version: 1`. No destructive bulk migration runs on project open.
Transcript replacement invalidates its old translation in the same publication.
Explicit vector clearing now publishes an empty-generation pointer rather than
physically deleting records before the metadata change commits.

Thumbnails/proxies use generation-specific output directories. A requested
derivative failure aborts publication. Disabled derivatives do not retain stale
source pointers. Cancelled or failed visual stages do not emit a successful-file
signal or final 100% progress. The combined transcription/translation worker's
transcription path also uses staged publication.

## Scene timing contract

The indexer no longer divides duration evenly by scene count. It records each
observed histogram-cut sample time and representative image's own time/frame.
Caption records and YOLO detections refer to that image's timestamp; temporal
vectors use the observed scene bounds.

- Prefer OpenCV decoder presentation timestamps; retain decoded frame position.
- When the decoder does not provide advancing timestamps, label a frame/fps
  fallback as `estimated_cfr`. Reject unusable/non-monotonic timing.
- Store the interval between samples and the lower/upper sample bounds around
  each observed cut. A cut at sample time 8 seconds may lie between the preceding
  sample and 8 seconds; this is explicitly **sampled precision**, not an exact
  edit decision or SMPTE source timecode.
- Store duration provenance (`frame_count/fps`). Exact VFR duration/timebase,
  camera start timecode, and Premiere frame conversion still need the dedicated
  media/export validation. Do not certify this as frame-accurate NLE interchange.
- Existing estimated scene metadata is retained until a successful reprocess;
  it cannot be corrected retrospectively without reading the media.

## Executed checks

All commands were run on this Apple Silicon Mac. Suites ran in separate processes.

```bash
python3 -m tests.smoke_search
python3 -m unittest tests.test_review_regressions -q
ANONYMIZED_TELEMETRY=False /private/tmp/cyne-safety-venv/bin/python -m unittest tests.test_safe_reprocessing -q
PYTHONPYCACHEPREFIX=/private/tmp/cyne-safety-cache python3 -m compileall -q core gui workers tests main.py config.py
```

| Check | Result |
|---|---|
| Search smoke suite | 33/33 passed |
| Existing review regressions | 21/21 passed; prior proxy-annotation import error fixed |
| New safe-reprocessing/timing suite | 28/28 passed in the isolated environment, no skips |
| Source compilation | Passed |
| Patch whitespace check | Passed |

The new suite covers SQLite commit failure, partial vector writes, temporal-write
failure, cancellation, source changes/removal, competing publishers, old reader
snapshots, unknown metadata, abandoned-generation reopening, logical clear,
transcript/translation preservation, and successful publication.

Two tests use real native libraries: persistent Chroma upsert/query/reopen and an
OpenCV-generated/decoded 10-second video with cuts at 2 and 8 seconds. Observed
scene ends are 2, 8, and 10, rather than equal thirds. Other worker tests extract
the actual processing methods and supply AI/widget doubles; they do not exercise
Qt scheduling or real inference. Those tests verify representative-frame caption
times and preservation/no-success signals on decode, cancellation, and proxy failure.

Temporary test environment: Python 3.9.6 arm64, Chroma 0.4.24, NumPy 1.26.4,
OpenCV headless 4.11.0.86 (about 392 MiB installed). To recreate it, use an isolated
venv and install `chromadb==0.4.24`, `numpy==1.26.4`, and
`opencv-python-headless==4.11.0.86`. No torch, AI weights, or wedding footage were
downloaded. Chroma's old telemetry dependency and the system SSL build emitted
nonfatal diagnostics; a full supported-runtime dependency lock is still required.

## Remaining limits and next work

- Old and abandoned generations/artifacts are deliberately retained. Snapshot-safe
  garbage collection, capacity enforcement, and large-library query cost are not
  solved. Visibility filtering can inspect many vectors/metadata rows. Benchmark
  and add retention/compaction before repeated full-library runs.
- Publication is per file/stage, not a durable job queue. Process/host power loss
  recovery of pending jobs, independent embedding stages/settings versions, and
  bounded scene-image memory remain W2 work. Reopen/abandoned-publication tests
  do not simulate filesystem/hardware failure or whole-host power loss.
- Current builds understand generation metadata; older pre-change builds do not.
  Keep a project backup before the first real reprocessing run and restore that
  backup for an older-build rollback. Retained records alone do not make old
  vector readers generation-aware.
- Background worker shutdown before shared-model unloading and full Qt lifecycle
  tests remain open. No full application launch, MPS inference, actual wedding/VFR
  media, Premiere import, phone test, or Windows execution was performed here.
- Mac compatibility has started with verified storage/decoder behavior and the
  annotation fix. Use the next W0 milestone for a reproducible supported Python
  environment, full GUI/ML dependency set, FFmpeg/FFprobe, and real sample inference.
  Packaging/notarization follows application acceptance.

F06's equal-duration fabrication is fixed for reprocessed sampled scenes; exact
source-timebase/export certification remains pending. Safe replacement in the
standard worker paths is implemented and tested. The complete wedding workflow
remains below beta acceptance until the other build-plan gates pass.
