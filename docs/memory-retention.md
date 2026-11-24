# Long clips and generation retention

Implemented locally on 24 November 2026. Use with the configured
[SSD workspace and durable jobs](workspace-jobs.md). Originals stay read-only;
this feature manages new, explicitly tracked derived generations. It does not
automatically clean an existing project.

## Processing limits

`processing_memory_mib` defaults to **256**, accepts integers 64–1024, and scales
application buffer limits. It is not an OS/RSS limit: model weights, tensors,
decoders, Chroma/HNSW and native allocator caches consume additional memory.
Processing remains serial. The default policy is:

| Buffer | Limit / behavior |
|---|---|
| Resized CLIP frames | At most 32 per batch; 16 with the 64 MiB policy |
| Scene images | At most 5 retained; existing caption/temporal code only uses the first 5 scenes |
| Keyframe history | Last 5 candidates |
| Tag frame occurrences | 3 distinct indices per tag, sufficient for the existing threshold |
| Visual / transcript vector writes | At most 64 / 32 rows per batch |
| Scene / transcript records | At most 8,192 / 20,480 at default settings |
| Complete metadata | At most 8 MiB UTF-8 JSON, 204,800 value nodes, nesting depth 24 |
| Scene / transcript working records | Each has half the metadata byte allowance; each string is at most 65,536 characters |
| Summary input | First 4,096 characters; the stored transcript remains complete within its limits |
| Video decode | Known positive dimensions, at most 4,096 × 2,304 pixels; larger frames fail visual preflight |
| Speech PCM | One 180-second core window plus up to 2 seconds of context on each side, mono 16 kHz int16 |

Scene times and representative-frame metadata remain available even when an
image is not retained for captioning. No scene or transcript record is silently
dropped to meet a limit. An over-limit stage fails without publishing, preserving
the prior transcript, vectors, metadata and completion checkpoint. A smaller
scope or explicitly higher policy can then be submitted as a new analysis.
Existing oversized metadata remains readable through legacy reads; processing
refuses it before hydrating/copying it into the bounded stage.

Speech decoding writes one temporary WAV in the generation workspace, closes it
after each window, and terminates its owned FFmpeg child on cancellation. Word
midpoints select the owning core window; actual word timestamps trim crossing
segments. Times remain relative to the original clip, including leading audio
offsets. Missing/invalid crossing word times fail the stage. Context changes can
affect recognition at joins; actual wedding languages, music and overlapping
voices still require acceptance. The legacy combined worker also uses bounded
transcription, but its older Whisper **translation** path rejects sources longer
than the selected core-window duration; long translation needs a later redesign.
Thumbnail/proxy FFmpeg cancellation remains a separate gate.

Set project defaults in `_cyne_db/settings.json` using integer keys
`processing_memory_mib` and `speech_chunk_seconds` (1–300). These defaults are not
exposed as GUI controls yet. CLI overrides are frozen in each new job snapshot:

```bash
./cyne.command --project "/path/to/project" preflight \
  --file "/Volumes/Wedding/Camera A/C0001.MP4" --stage transcribe_audio \
  --memory-mib 256 --speech-chunk-seconds 180
./cyne.command --project "/path/to/project" submit \
  --file "/Volumes/Wedding/Camera A/C0001.MP4" --stage transcribe_audio \
  --memory-mib 256 --speech-chunk-seconds 180 --whisper-model small
```

Preflight JSON reports the memory policy and maximum temporary PCM allowance.
Successful metadata records `visual_processing_memory` /
`speech_processing_memory` high-water counters. These are application counters,
not a measurement of GPU/model peak memory.

## Inspect, quarantine, restore, purge

Close the project in the GUI before CLI maintenance: embedded Chroma has one
project process owner. Retention takes the same processing lock as inference and
the database read/publication lock. Composed readers may use `db.read_snapshot()`.

Only generations registered by this build are eligible. A saved dry-run plan
protects the current publication, active writers, pinned generations, any current
thumbnail/proxy reference, unfinished job results, the **two most recent previous
successful generations per source/stage**, and generations retired/created within
the last **24 hours**. At least one previous success must always be kept. Unknown
legacy vectors/generations, unregistered files, originals and `.cyne` files are
never adopted or deleted. Nothing runs automatically at startup or on a timer.

```bash
./cyne.command --project "/path/to/project" retention plan
./cyne.command --project "/path/to/project" retention status RUN_ID
# Inspect the candidate generations, counts, byte estimates and protected reasons.
./cyne.command --project "/path/to/project" retention apply RUN_ID
# Recover any quarantined generations; this does not roll back the active head.
./cyne.command --project "/path/to/project" retention restore RUN_ID
# Optional: protect a tracked generation before creating a plan.
./cyne.command --project "/path/to/project" retention pin GENERATION --reason "reviewed selects"
./cyne.command --project "/path/to/project" retention unpin GENERATION
# Separate irreversible action, after a 7-day cooling period:
./cyne.command --project "/path/to/project" retention purge RUN_ID
```

`plan` writes its inspection/journal only. `apply` rechecks the publication /
protection fingerprint and workspace identity; changed plans fail and require new
inspection. It copies vectors into a compressed, checksummed archive in
`metadata.db`, verifies row counts and the aggregate manifest, then removes live
raw rows in batches of 64. It moves only exact registered derivative files into
the same output workspace's `quarantine/RUN_ID` namespace. It never recursively
deletes directories. Provenance, symlinks, target containment and file hashes are
checked. Copy-space checks leave headroom for the archive; quarantine needs space
and does not immediately reclaim derivative bytes.

Interrupted `apply` can be rerun with the same ID if its publication/protection
snapshot still matches, or `restore` can recover the archived generation. The
journal prevents another plan owning the same partial cleanup. Restore verifies
archives and file hashes, preserves conflicting live files, restores raw vectors
and pins the recovered generation. The published head stays unchanged; restore
is recovery of a retained copy, not an editor undo command. Inspect `status` after
a partial operation. Corrupt or missing archive rows fail closed.

`purge` rechecks protections and the seven-day age, deletes only registered
quarantined files, and clears vector payloads while retaining audit IDs/digests.
It cannot restore purged data. Restored/pinned copies are protected. Logical
vector deletion and clearing SQLite payloads do **not** guarantee smaller SQLite
or HNSW files; vacuum/index rebuilding and automatic storage quotas are deferred.
Empty generation directories and untracked files remain in place.

Published vector queries cap ANN widening at 256 candidates. If hidden historical
generations crowd them out, a paged exact fallback scans 64 rows at a time and
retains only the requested top results. It supports the application's embedding
queries and source/document filters; fallback for `query_texts` is explicitly
unsupported. Result budget is 2,048 rows and fallback dimensions at most 4,096.
Diagnostics identify a scan; it can be slower on a large library. Counts are
paged too. The legacy all-results `get()` and whole-library GUI/search caches
remain materializing APIs; this is not a whole-application heap cap.

## Verification and next acceptance

Run suites in separate processes from search stubs:

```bash
source scripts/macos_env.sh
.venv/bin/python -m unittest tests.test_memory_retention -q
.venv/bin/python -m unittest tests.test_worker_memory -q
.venv/bin/python -m tests.memory_retention_benchmark
.venv/bin/python -m tests.durable_runtime_smoke
```

The [audit](audits/2026-11-24-memory-retention.md) distinguishes synthetic
long-duration buffer profiles from actual short cached-model inference. Next:
choose real storage with headroom, test the longest representative wedding clip
and actual language joins, then finish physical SSD/power-loss acceptance,
interactive model ownership, editor review and the agreed Premiere handoff. Safe source-root
relinking/configuration revisions are now implemented; see the
[relinking contract](workspace-relinking.md). A workspace revision invalidates an
unapplied retention plan; already quarantined copies use their pinned historical
output location for restore/purge.
