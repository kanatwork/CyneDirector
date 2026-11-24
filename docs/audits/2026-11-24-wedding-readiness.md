# CyneDirector wedding-workflow readiness audit — historical baseline

Superseded by the [efd0930 reassessment](2026-11-24-efd0930-reassessment.md): current score 48/100. Findings below describe 112388b only.

Audit date: 24 November 2026, Asia/Kolkata. Source reviewed:
`112388b25d7265ebb85d50ecf97604b920e9ca1b` from
[kanatwork/CyneDirector](https://github.com/kanatwork/CyneDirector).
App version: `2.1.0`.

## Conclusion

**38/100 for the intended wedding/Premiere/phone workflow.** This is a strong
prototype entering beta hardening, with useful visual/audio search foundations.
It is not ready for an unattended 800 GB run. The [weighted rubric and path to
100](../../buildplan.md) define this judgment; it is not a measured code-completion
percentage. No real wedding footage was available to measure retrieval quality.

GitHub's default branch was `main` and its HEAD matched the restored checkout at
the hash above. Its last change is a PRD update dated **17 February 2026,
00:29:59 IST**. Only `main` and no tags were advertised by the remote at inspection.
The previously discussed `2afb58e` is the parent of this latest commit. Restoration
does not recover any old uncommitted files or private media/project databases.

## Method and evidence limits

- Reviewed project initialization, SQLite/vector persistence, visual indexing,
  transcription, workflow scheduling, background indexing, proxy naming, search
  parsing/filter/cache/pagination, dependencies, and planning documents.
- Source compilation passed on the current Python 3.9.6 interpreter.
- `python3 -m tests.smoke_search`: **23/23 passed**. It uses import stubs and fake
  collaborators; it does not exercise real models, ChromaDB, or Qt worker lifetime.
- **Nine isolated source-level probes observed defects.** The executable
  [reproducer](reproduce_wedding_findings.py) extracts actual functions/classes
  with AST and supplies synthetic collaborators. The [recorded JSON](2026-11-24-probes.json)
  contains the results. Exit 0 means the audit script executed, not that tests of
  correct behavior passed. Re-run after fixes and convert the relevant cases to
  regression tests with corrected expectations.
- [Environment snapshot](2026-11-24-environment.json): Apple Silicon, about 15.4
  GiB free internally, no required GUI/ML modules on the checked Python, and no
  FFmpeg/FFprobe or newer Python executable on PATH. The wedding SSD was absent
  from the mounted volumes at inspection.
- No dependencies/models were installed; no app window, real inference, media
  encode, Premiere import, phone pairing, or Windows/GPU run was performed.
  The real Qt crash/lifecycle risk below needs an actual Qt integration check.
- A separate import probe with only the logger stubbed confirmed that Python 3.9
  raises `TypeError` on `float | None` in `core/proxy_generator.py:63`. Compilation
  alone does not evaluate those annotations or establish runtime compatibility.

P1 below means a blocker for relying on the unattended wedding workflow. P2
means a correctness issue that still needs closure before claiming the behavior.
All findings are open; this audit updates documentation and adds probes only.
Line references refer to the audited upstream source, which was not modified.

## Findings

### F01 — P1: camera filenames collide in generated proxies and thumbnails

Sources: `core/proxy_generator.py:52`, `:93`, `:147`; `workers/indexer.py:1012`,
`:1019`.

Both outputs use only the sanitized source filename stem in a project-wide output
directory. `/Camera_A/C0001.MP4` and `/Camera_B/C0001.MP4` both become
`C0001_proxy.mp4`; FFmpeg receives `-y`. Whichever finishes later can overwrite
the other camera's derivative, leaving both metadata entries pointing to it.
Thumbnails have the same collision. The naming probe confirms identical names;
an encoder was not invoked.

Fix: name artifacts by stable asset identity and source generation, validate them,
then atomically publish. Test duplicate basenames and sanitization collisions.
Do not rename or overwrite the originals to solve a derivative naming problem.

### F02 — P1: completion cleanup can discard the next active worker

Sources: `gui/main_window.py:2334`, `:2355`, `:2358`, `:2361`;
`core/workflow_manager.py:326`, `:342`; `gui/main_window.py:1619`, `:2540`, `:2553`.

`worker_finished()` calls `on_operation_finished()`, which synchronously dispatches
the next queued operation. That operation can install a new `self.worker` before
the original completion handler resumes. The handler then waits on that new
worker and assigns `self.worker = None`. The isolated probe starts visual then
audio processing and observes a RUNNING audio operation with no retained active
worker reference. If the old thread still reports running when dispatch occurs,
the start guard can instead refuse to launch the successor.

This breaks cancellation/ownership and creates a potential premature QThread
destruction/crash risk; the crash itself was not reproduced with actual Qt.
Fix: retain a local reference to the completed worker, clean it up on actual
termination, and only then advance scheduling. Test both lifecycle orderings.

### F03 — P1: resume stalls after an operation finishes while paused

Sources: `core/workflow_manager.py:271`, `:277`, `:326`;
`gui/main_window.py:1421`.

Pause sets a manager flag without stopping the active worker. If that worker
finishes, completion clears `current_operation` and avoids dispatch because the
workflow is paused. Resume clears the flag but never invokes `_process_next()`.
The probe observes `is_running=True`, one pending operation, and no active one.

Fix: define and expose pause semantics, coordinate active workers, and dispatch
pending work when resuming at a boundary. A phone-visible “paused” state must
reflect an acknowledged checkpoint, not just a changed button label.

### F04 — P1: one shared freshness timestamp can retain an old transcript

Sources: `core/workflow_manager.py:129`, `:140`; `workers/transcriber.py:71`,
`:179`; `workers/indexer.py:1025`.

Both visual and transcription stages overwrite `last_scanned`. After a media
file changes, visual indexing can advance it while an older transcript remains.
The workflow filter, and the transcriber itself, then see a transcript plus a
current timestamp and skip re-transcription. This also matters when both stages
were queued: the second worker repeats its own freshness check.

The probe seeds the post-visual state and confirms the old transcript is not
scheduled. Fix: independent stage fingerprints/model versions and atomic stage
completion. Existing timestamps must not certify other stages. Test visual-first,
audio-first, changed media, and upgrading speed transcripts to semantic embeddings.

### F05 — P1: failed vector writes can be forgotten while processing continues

Sources: `core/database.py:153`, `:168`, `:241`, `:254`;
`workers/indexer.py:1136`, `:1139`, `:1147`.

Vector upsert exceptions are logged and swallowed by `add_visual_embeddings()`.
Its caller then clears the pending batch. The probe raises a synthetic disk-full
error from upsert and confirms that no failure propagates and zero buffered
records remain. SQLite saves also catch write errors without returning a failure
result. Indexing can subsequently write completion metadata or log “Completed.”

Fix: propagate typed failures, preserve pending work, and commit stage completion
only after all required artifacts persist. Test both stores independently; they
do not have a shared transaction. Low current internal capacity makes this a
practical concern for the wedding run.

### F06 — P1: scene and object timestamps are fabricated from equal clip divisions

Sources: `workers/indexer.py:250`, `:343`, `:347`, `:374`, `:960`.

Detected scenes retain a representative frame but no actual scene-cut timestamp.
The save step divides the whole duration by the number of scenes. The probe
shows two scenes in a 100-second clip always receive an end boundary of 50 and
100 seconds, irrespective of where the cut occurred. Temporal embeddings and YOLO
metadata reuse these estimates. Even a true scene start need not be the time of
the representative image.

Fix: retain real source timestamps/timebase for cuts and sampled images. Keep
sampled-boundary precision explicit. Require frame-checked in/out conversion
before any Premiere selects export; these estimates are unsuitable for it.

### F07 — P1: cancelled visual indexing still publishes completion metadata

Sources: `workers/indexer.py:209`, `:326`, `:993`, `:1025`, `:1043`, `:1149`;
`core/background_indexer.py:157`.

`stop()` changes `is_running`; leaving the frame loop does not bypass subsequent
caption/metadata/finalization code for that file. An isolated cancellation during
decode still writes `last_scanned` and ends with progress 100. Depending on the
point of interruption it can publish partial tags/embeddings as current. The
background completion handler also records a file as indexed whenever the worker
emits the argument-free `finished_signal`, including the model-load failure path.

Fix: explicit per-file completed/failed/cancelled/interrupted outcomes, checks at
stage boundaries, and completion stamps only for committed successful stages.
Keep usable previous generations until replacements succeed.

### F08 — P2: syntactically valid settings JSON can crash project loading

Source: `core/settings_manager.py:87`, `:92`, `:94`.

The loader merges `stored` as a mapping but only catches JSON decoding and OS
errors. `settings.json` containing `[]` is valid JSON and raises uncaught
`TypeError: 'list' object is not a mapping`; the probe confirms it. `null` and
other non-object roots need equivalent validation.

Fix: validate the root object and setting types, recover safely, preserve a
diagnostic copy, and write via temporary file/replace. Extend invalid-settings
coverage beyond accent hex strings.

### F09 — P2: duration/filter/cache behavior can misrepresent search results

Sources: `core/search_engine.py:33`, `:555`, `:600`, `:658`;
`gui/search_tab.py:605`, `:952`, `:1007`, `:1048`.

`duration:30-60` is parsed but never applied in `_apply_query_filters()`. The GUI
records its duration selection without using it to filter either. An isolated
3600-second result survives the requested 30–60-second range. Metadata refresh
does not invalidate the result cache: the second half of the probe refreshes
an asset and still retrieves the old cached result.

Match-type/score filtering and sorting are also performed on the current page,
not on all candidates; display groups videos by number of matches, which can
override selected ordering. Exact-phrase filtering retains unfiltered results
when there are zero phrase matches. These are code-traced observations rather
than actual UI tests in this audit.

Fix: a tested query contract that filters/sorts before pagination, generation-aware
cache invalidation, stable ordering, and truthful totals/empty states. Exercise
more than one page and metadata changes during active search.

## Capabilities and remaining engineering risks

| Area | Evidence present | Remaining gap |
|---|---|---|
| Search | CLIP vectors, transcript keyword/vector paths, multimodal fusion, query parsing | Semantic quality on wedding languages/events unmeasured; F09 |
| Speech | Timestamped Whisper transcription and optional translation; language preference is wired | Semantic embeddings are accuracy-only; CLIP text embedding quality/length/language limits need evaluation |
| Visual understanding | Sampled frames, BLIP captions, YOLO objects, shot estimates | Captions/object sampling favors first scenes; real source-time fidelity needs F06 |
| Hardware | CUDA/MPS/CPU selection; lazy loading | This Mac is unvalidated; `get_whisper_params()` uses CPU for non-CUDA, so MPS visual support does not imply MPS Whisper |
| Storage | SQLite WAL, thread-local connections, batched vector writes | F01/F04/F05; pending queues are memory-only; absolute paths have no offline-drive remapping |
| Long clips | CLIP frames are resized and batched | Representative images for all detected scenes accumulate; no measured memory envelope |
| Re-indexing | Incremental mtime logic and vector upserts | Old vector IDs are not removed when replacement media changes timestamps/segments; stage generations needed |
| Background work | Separate background indexer and watcher | Independent schedulers share/unload models; shutdown handles the foreground worker but not background ownership |
| People/organization | Face database and hierarchy helpers | Faces/Tags pages are placeholders; no complete face pipeline, virtual selects collections, or OCR |
| Premiere | SRT export | No source-accurate selects/sequence interchange or verified editing-proxy contract |
| Phone | Existing ChatGPT remote connection can provide a control channel | Pairing unverified; no CyneDirector CLI/API, persistent jobs, or tested phone preview delivery |
| Delivery | Windows setup/launch scripts and one source version constant | No tested Mac setup, dependency lock, packaging/CI/updater pipeline |

Optional DeepL translation sends text to a third-party API. The product's prior
blanket “all processing local” claim requires that exception. Neither choosing
local inference nor keeping original media on the SSD implies zero network use
for model downloads, remote prompts, or explicitly enabled translation.

## Priority and next action

Follow [W0–W7 in the build plan](../../buildplan.md). Start implementation with
W1a worker lifetime, pause/resume, write-failure propagation, and cancellation
truth. Establish runtime/storage prerequisites in parallel with that code work.
Then add durable stage jobs, phone-readable control, wedding collections, and
the narrow Premiere handoff before scaling to 800 GB.

The current restoration changed no runtime application modules. The score can
improve only after implementation and real acceptance evidence. Advanced face UI,
OCR, an updater, and a new browser dashboard do not close the blockers above.
