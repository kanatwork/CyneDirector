# PRD.md — CyneDirector Product Requirements and Backlog

**Scope corrected 24 November 2026:** CyneDirector targets video editors on
Apple Silicon Macs and Windows PCs. Intel Macs and a CyneDirector mobile UI are
outside scope. Phone use means Codex supervising development. **All 36 questions
are answered; 27B confirms search and recent results on the home screen.** Use inline chat, never popup forms.
The [product brief](docs/product-brief.md) defines accepted launch scope;
[discovery](docs/product-discovery.md) distinguishes answers from recommendations.
Next produce the full application redesign and revised success metrics. Existing
implementation details below remain a backlog inventory, not evidence of completion.

## 1. Document Control

- **Product:** CyneDirector v2.1.0
- **Stage:** Prototype; 36 product decisions confirmed, full application redesign next
- **Owner:** Product + Engineering
- **Last updated:** 2026-11-24
- **Architecture reference:** See `CLAUDE.md` for full technical architecture, module map, and development conventions.
- **Execution:** [buildplan.md](buildplan.md) supersedes the historical Gameplan v3.
- **Evidence:** [24 November workspace/relink verification](docs/audits/2026-11-24-workspace-relinking.md), local work on upstream `efd0930`; historical **67/100** under the superseded wedding/Premiere/phone rubric. Product readiness will be redefined after discovery.

Requirements and metrics below are acceptance targets, not claims that the current
implementation passes them. Compilation and 201 regressions pass, along with native
Mac startup/jobs GUI, Qt/storage/FFmpeg integration, and real cached-model CLI processing. Wedding
media, editor utility, Premiere, other hardware, and installed-package acceptance remain pending.

## 2. Product Vision

Confirmed vision from questions 1–6: CyneDirector is a desktop companion for solo
editors and small teams making story-led films. Its promise is understanding raw
footage and developing a story grounded in it. Launch support covers weddings,
fiction, documentaries, commercials and social content equally. The NLE handoff
is reliable file-based exchange with Premiere.

The user selected a **full application redesign before completing a workflow**.
The first valuable result is an evidence-linked footage brief and usable paper edit.
The complete design must accommodate all five genres, rather than use a wedding
workflow as the product's implicit default. Kanishkar's approximately 800 GB wedding
is one intended real project. Fast retrieval of a shot, performance or spoken line
is the immediate pain; source-grounded story development is the larger promise.
The agreed journey spans project/creative brief, progressive coverage, synchronized
review and corrections, both in-app AI and portable context packs, paper edit,
reviewed Premiere handoff and related film versions.

CyneDirector targets Apple Silicon Macs and Windows PCs. Codex from a phone is a
separate development workflow. Optional cloud analysis is offered during project
setup; provider, data scope and cost interactions remain to be designed. English speech,
including Indian English accents, is the launch requirement. Hindi and multilingual/
code-switching/translation requirements are deferred; preserve existing data.
Validation begins on the user’s own available projects. A GitHub release updater
is accepted delivery scope, currently unimplemented. The
[dated model review](docs/model-evaluation-2026-11-24.md) is research, not an installed
replacement stack or proof of a measured quality win.

## 3. Problem Statement

Editors spend time locating particular images, performances and spoken lines,
then reconstructing enough context to form a story. Filenames and disconnected
logs do not convey the available coverage. CyneDirector must reduce that review
effort and produce useful story evidence with inspectable source references.

## 4. Target Users

- **Primary:** Solo editors and small teams making story-led films.
- **Equal launch genres:** Weddings, fiction, documentaries, commercials and social.
- **Initial validation:** Kanishkar’s own available projects, including the wedding.
- **Editing environment:** Premiere first, portable records for Resolve next.

## 5. Goals

- **G1 — Reliable daily workflow:** A user can import, index, search, inspect, and export without encountering blocking bugs or data loss.
- **G2 — Settings users can trust:** Every setting in the UI controls real runtime behavior. Changing a setting and restarting the app produces the expected result without workarounds.
- **G3 — Predictable search experience:** Filters, sort, and pagination behave consistently across repeated searches. The same query returns the same results.
- **G4 — Multi-modal retrieval:** Users can find footage by visual similarity, spoken dialogue, detected objects, and temporal context — individually or combined.
- **G5 — Hardware-adaptive stability:** The app runs reliably on CUDA (Windows), MPS (macOS), and CPU-only systems, automatically selecting the best available backend.
- **G6 — Useful Premiere handoff:** Reviewed source ranges become a tested selects sequence with correct source frames, audio, and original-media relinking.
- **G7 — Editor confidence:** Editors can see analysis progress/coverage, inspect evidence, correct mistakes and recover safely. Exact workflow and acceptance targets follow product discovery.

## 6. Non-Goals (Current Beta Window)

- Multi-user collaboration or cloud sync
- Full timeline editing, multicam synchronization, color grading, sound mixing, and autonomous final-film delivery; these remain in Premiere
- Advanced permissions or role-based access
- Broad interchange support beyond the narrow, tested Premiere selects contract
- Intel Mac and Linux support
- A CyneDirector mobile UI, phone processing control, phone preview delivery or custom remote product API

## 7. Scope

### 7.1 Existing Implementation Surface (requires hardening/validation)

- Project creation/open, `.cyne` project files, and media import
- Background indexing pipeline (CLIP embeddings, BLIP captions, YOLO object detection, Whisper transcription)
- Semantic search with query expansion, boolean operators, field filters, and pagination
- Transcript search, object-aware retrieval, and temporal sequence queries
- Translation pipeline (DeepL API with Whisper fallback, mixed-language handling)
- SRT subtitle export
- Runtime settings wiring (device, model selection, indexing parameters, appearance, API keys)
- File watcher for automatic re-indexing on file change
- Pre-download dialog for AI model management
- Beta release hardening and packaging

### 7.2 Next Scope — Partially Built (needs UX completion)

These features have backend implementation but are not wired into the standard user workflow:

- **Face recognition:** `core/face_db.py` stores encodings and names with auto-migration from legacy formats. Not yet integrated into the indexing pipeline or search results.
- **LLM summarization:** `core/summary_generator.py` generates summaries via Llama-3.2 / Phi-3 fallback. Currently runs only during transcription in accuracy mode; no standalone trigger.

### 7.3 Editor Workflow and Safety — Mixed Implementation Status

- Implemented locally: per-file generation publication, source checks, sampled scene timing, and durable file/stage jobs with publication/ledger reconciliation
- Implemented: explicit pinned media/cache/output roots, filesystem capacity/reserve checks, offline/replaced-root waits and stable root/relative asset IDs
- Implemented: bounded clip buffers/windowed speech and explicit tracked-generation inspection, verified quarantine, restore/pinning and delayed purge; see [limits](docs/memory-retention.md)
- Implemented: verified different-path source-root relinking, stable legacy source keys/asset IDs, atomic workspace revisions, GUI/CLI preview/apply, future-output/model/reserve updates and offline/custom-field project-save preservation
- Planned: physical database compaction and explicit project/cache/old-derivative migrations; real long-media/SSD acceptance remains open
- Planned: editable virtual scenes/events/topics/takes and timestamped reviewed selects
- A narrow Premiere-compatible selects export and verified editing-proxy workflow
- Implemented local JSON job/control commands and native Workspace & Jobs GUI using shared orchestration; these serve desktop reliability, not a phone-product requirement
- Accepted, planned: source-linked context export and in-app AI with original dialogue, timed observations, coverage gaps, corrections, a creative brief and paper edits
- Accepted, planned: English speaker review (including Indian English accents) and synchronized player/filmstrip/transcript
- Accepted, planned: optional cloud setup, related film versions and safe release updates

### 7.4 Deferred Scope

- OCR / text-in-video retrieval
- Offline drive metadata and online/offline result state
- Extensive tag management beyond the wedding event/selects collections
- Light theme
- Undo/redo in UI

## 8. Functional Requirements

### FR-1 Project Management

- FR-1.1: User can create a new project or open an existing `.cyne` project file.
- FR-1.2: Project settings are persisted to `_cyne_db/settings.json` and survive app restart.
- FR-1.3: Recent projects are tracked and accessible from the project dialog.

### FR-2 Indexing

- FR-2.1: User can select video files and start a background indexing job with progress and log feedback.
- FR-2.2: Indexing extracts keyframes at a configurable interval (1–10 seconds) and generates:
  - CLIP visual embeddings (768-D vectors stored in ChromaDB)
  - BLIP scene captions (stored in SQLite metadata)
  - YOLOv8 object detections with bounding boxes (80 COCO classes, 0.4 confidence threshold)
- FR-2.3: Indexing optionally generates 720p proxy videos and 320x180 thumbnail JPEGs (controlled by settings).
- FR-2.4: Incremental processing skips a stage only when its input fingerprint and settings/model version match a committed successful result. Stage-specific source signatures now exist; durable jobs snapshot settings and support explicit new analyses; automatic freshness by model/algorithm version and independent embedding completion remain planned.
- FR-2.5: Batch size is configurable ("auto" uses RAM-based dynamic sizing via `core/performance.py`, or user-specified 1–128), clamped by the processing policy to at most 32 frames. Metadata/record limits fail without publishing partial replacements; speech uses bounded PCM windows. This is not an OS/model-memory cap.
- FR-2.6: File watcher detects new or modified files and triggers re-indexing when `auto_index_on_change` is enabled.

### FR-3 Search

- FR-3.1: User can enter a natural-language query and receive ranked results with relevance scores.
- FR-3.2: Search supports boolean operators (AND, OR, NOT), quoted phrase matching, and query expansion.
- FR-3.3: Search supports field-specific filters: `visual:`, `dialogue:`, `objects:`, `cast:`.
- FR-3.4: Search supports range filters: `score:>80`, `score:<50`, `duration:30-60`.
- FR-3.5: Search supports temporal sequence queries (e.g., "A then B").
- FR-3.6: Results are filtered and stably sorted before pagination (50 per page). A 5-minute cache is invalidated by relevant metadata/generation changes and keyed by search options.
- FR-3.7: Filter checkboxes (VISUAL, DIALOGUE, OBJECT, CAST, TEMPORAL SEQUENCE, MULTI-MODAL) control which match types appear in results.
- FR-3.8: Sort options (Relevance, Filename) produce stable, deterministic ordering.
- FR-3.9: Multi-modal results correctly reflect their constituent match types for filtering.

### FR-4 Transcription and Translation

- FR-4.1: User can transcribe audio in the original language using Whisper (configurable model: base / small / medium / large-v3).
- FR-4.2: Transcription runs with VAD (Voice Activity Detection) and produces timestamped segments with per-segment language detection.
- FR-4.3: Transcription gaps exceeding 2 seconds are detected and stored as metadata warnings.
- FR-4.4: User can optionally translate transcripts to English via DeepL API (if key configured) or Whisper built-in translation as fallback.
- FR-4.5: Mixed-language transcripts are handled intelligently — English segments are preserved, only non-English segments are translated.
- FR-4.6: Language preference setting acts as a source language hint for Whisper transcription and translation.
- FR-4.7: User can export transcripts as SRT subtitle files.

### FR-5 Settings

- FR-5.1: All active settings keys produce observable runtime behavior changes (see Settings Wiring table in `CLAUDE.md`).
- FR-5.2: Settings changes take effect immediately where possible, or on next relevant operation. No app restart required.
- FR-5.3: Invalid or corrupt settings values fall back to safe defaults without crashing.
- FR-5.4: The settings dialog validates inputs (accent color normalization, batch size parsing, keyframe interval clamping).

### FR-6 Reliability

- FR-6.1: Worker thread errors are surfaced to the user via log signals without crashing the app.
- FR-6.2: Missing optional models degrade gracefully (LLM unavailable → template summary; CLIP load fails → skip embeddings; DeepL fails → Whisper fallback).
- FR-6.3: VRAM is released after worker completion so subsequent operations can load different models.
- FR-6.4: Database uses WAL mode with `busy_timeout=5000` and connection-per-thread to handle concurrent access from workers.

### FR-7 Durable Processing and Media Safety (W1/W2)

- FR-7.1: Every asset has a stable identity independent of duplicate camera filenames and drive mount names. Source originals are never rewritten by indexing.
- FR-7.2: Each processing stage records its own input fingerprint, settings/model version, checkpoint, and explicit outcome. Another stage's timestamp cannot certify completion.
- FR-7.3: Jobs survive process restart; unavailable media enters a visible waiting/offline state. Retrying or reconnecting does not duplicate committed work.
- FR-7.4: Failed writes and cancelled work cannot publish successful completion. Previous valid results survive a failed replacement generation.
- FR-7.5: Processing uses bounded batches, capacity checks, and a single coordinated inference scheduler. Progress includes real completed counts and measured elapsed time.
- FR-7.6: Scene bounds, preview frames, transcripts, and selects retain actual source timestamps/timebase. Estimated sample precision is explicitly identified.

### FR-8 Reviewed Selects and Premiere

- FR-8.1: User can edit virtual scene/event/topic/take groups and save reviewed source in/out ranges without moving media; keyboard In/Out and transcript selection are core interactions.
- FR-8.2: Each select records asset/generation, source range, ordering, note/rationale, and review state; human review can correct suggestions.
- FR-8.3: Export provides a portable source manifest and tested Premiere-compatible markers/selects, with any selects-sequence format verified against the installed Premiere version. JSON/CSV alone is a review fallback, not claimed sequence interchange.
- FR-8.4: Source frames, timecodes, frame rates, audio layout, original-media relinking, and a short render are checked in a separate Premiere test project.
- FR-8.5: Preserve original transcripts and existing translations separately. Evaluate English speech, including Indian English accents; Hindi, code-switching and translation are deferred launch requirements. Identities/relationships require editor confirmation.

### FR-9 Desktop Progress and Recovery

- FR-9.1: Desktop GUI and local typed commands expose durable job IDs, status/events, pause/resume, cancellation and failed-item retry.
- FR-9.2: Closing a dialog or losing a launcher does not erase committed work; repeated request identities deduplicate.
- FR-9.3: Show truthful stage/source counts, failures, heartbeat, checkpoints, capacity and measured progress. ETA needs measured throughput.
- FR-9.4: Present this in the chosen editor workflow. No phone interaction or mobile UI is a product acceptance gate.

### FR-10 Footage Context Export — Accepted, Planned

- Account for source coverage and omissions rather than imply exhaustive understanding.
- Link original dialogue and visual observations to portable source/range references.
- Keep translations, observations, interpretations, unknowns and editor corrections distinguishable.
- Export readable and structured detail suitable for an external AI, with explicit privacy choices and context-size management.
- Include readable and structured records/transcripts, optional contact sheets, a creative brief and source-linked paper edits with separate narration suggestions.
- Version packs with stable references, corrections and gaps; support the project/scene-or-topic/clip/moment hierarchy.
- Validate usefulness on the user’s own available projects. Detailed schema and context-size handling remain to be designed.

### FR-11 In-App AI and Review — Accepted, Planned

- Both in-app chat and external-AI packs use shared, inspectable source evidence.
- Offer optional cloud analysis during project setup with clear input scope and cost; do not upload footage merely because cloud is available.
- Default the home screen to a prominent search box and recent results (27B).
- Synchronize player, filmstrip and transcript; clicking a quote reaches its source moment. Preserve notes, ranges and editor corrections.
- Support a primary film and related cutdowns, aspect ratios and alternate versions.

### FR-12 GitHub Release Updater — Accepted, Planned

- Discover published releases, explain changes and provide the compatible installed-app update.
- Apply at a safe restart, preserving projects, original media, jobs, settings and caches; recover from failures and incompatible schema changes.
- App updates must not silently download new models or reprocess the full library.
- Test actual installed upgrades on Apple Silicon Mac and Windows; see the [updater contract](docs/release-updater.md).

## 9. Non-Functional Requirements

### NFR-1 Stability

- Crash-free session rate target: >=99% in beta cohort.
- No unhandled exceptions in the main thread. Worker exceptions are caught and reported via signals.

### NFR-2 Performance

- UI thread remains responsive (no blocking) during all background indexing and search operations.
- Proposed search target: p95 below 3 seconds on the declared hardware and representative indexed library, measured separately for cold/warm cache. File count alone is not a sufficient benchmark.
- Measure throughput as media-minutes processed per wall-clock minute for each stage, with models/codecs/hardware recorded. Derive the full-run estimate from total footage duration and the sample; do not promise a constant files-per-minute rate.

### NFR-3 Compatibility

| Platform | GPU Backend | Status |
|---|---|---|
| Windows 10/11 | CUDA | Implementation present; fresh installed-build validation pending |
| Windows 10/11 | CPU fallback | Implementation present; fresh validation pending |
| macOS (Apple Silicon) | MPS visual processing | Native Cocoa startup; real CLIP/BLIP-large/YOLOv8m samples pass on M4 Pro, macOS 27.2.1, torch 2.11.0 |
| macOS (Apple Silicon) | CPU fallback / current Whisper path | Whisper small CPU/int8 and dlib HOG blank-image check pass; complete CPU-only visual workflow unverified |
| Linux | Any | Untested, not officially supported |

- **Validation requirement:** Record the actual GPU, driver, PyTorch build, and backend smoke result. Historical machine-specific CUDA package examples are not current compatibility guarantees.
- **Existing mitigation:** `main.py` pre-imports torch before PyQt6 on Windows and strips foreign Python directories from PATH; re-test the installed package for the original DLL load-order issue.

### NFR-4 Data Safety

- Existing projects must open without destructive migrations.
- Schema and data updates must be backward-compatible or safely migrated (e.g., `face_db.py` auto-migrates legacy pickle/JSON formats).
- Settings files with unknown keys are preserved (merged with defaults, not overwritten).

### NFR-5 Storage

- Estimate metadata/vector/proxy growth from sampled media duration and stage settings, then enforce a configured budget and free-space reserve on each destination.
- Proxies are opt-in; thumbnails default to enabled in the current implementation. Both must have explicit output locations and collision-free source identity.
- Keep source media, project metadata, model cache, temporary outputs, and editing proxies separately identifiable and recoverable. Offline media does not remove its catalog entries.

### NFR-6 First-Run Experience

- AI models are downloaded on first use (lazy loading), not at install time.
- Pre-download dialog shows cache status and allows users to download models proactively.
- Preflight reports selected models, cache hits, and estimated download/storage needs before fetching. Actual requirements must be measured; full optional-model download is not required for the first wedding sample.

## 10. System Context

```
User (GUI)
  │
  ├─ Project Dialog ─── ProjectManager ─── .cyne files
  │
  ├─ Main Window
  │    ├─ Search Tab ──── SearchEngine ──── ChromaDB (vectors) + SQLite (metadata)
  │    ├─ Media Tree ──── Database
  │    ├─ Metadata Panel
  │    ├─ Embedded Player
  │    └─ Settings Dialog ── SettingsManager ── _cyne_db/settings.json
  │
  └─ Worker Threads (QThread)
       ├─ IndexerWorker ──── AIBackend (CLIP, BLIP, YOLO) ──── Database
       ├─ TranscriberWorker ──── AIBackend (Whisper) ──── Database
       ├─ TranscribeTranslateWorker ──── AIBackend + DeepL API ──── Database
       ├─ ImporterWorker ──── filesystem scan
       └─ FileWatcher ──── watchdog filesystem monitor
```

**External dependencies:**
- FFmpeg / FFprobe (required for proxy generation, thumbnails, and video metadata extraction)
- HuggingFace Hub (model downloads, cached locally)
- DeepL API (optional, for high-quality translation)

## 11. Success Metrics

- **M1 — Stability:** Crash-free sessions >=99% across beta cohort.
- **M2 — Defect bar:** Zero open P0/P1 defects in the import → index → search → export critical path.
- **M3 — Settings trust:** Zero user-reported "setting doesn't apply" bugs in first 30 days of beta.
- **M4 — Platform coverage:** Beta checklist passes on Windows 10/11 (CUDA + CPU) and macOS Apple Silicon (MPS + CPU).
- **M5 — Search quality:** Users can locate a known clip by natural-language description within the first 5 results on 80% of attempts (measured via beta feedback).
- **M6 — Wedding evidence:** At least 30 reviewed queries, representative 10–20 GB pilot, approximately 100 GB recovery test, then a reconciled approximately 800 GB run.
- **M7 — Editor outcome (proposed):** An editor develops a useful source-cited paper edit/context brief and can review its evidence; the agreed Premiere handoff has verified original frames/audio/relink. Final task and pass threshold follow discovery.

## 12. Acceptance Criteria (Beta Exit)

- All critical flows complete end-to-end without regression:
  - Import → Index → Search → Inspect/Playback
  - Transcribe → Translate → SRT Export
  - Settings change → Restart → Verify behavior persists
- Search filters, sort, and pagination produce deterministic results across repeated queries.
- Runtime settings match expected behavior after app restart.
- No unresolved data-loss, corruption, or silent-failure defects.
- Invalid settings values (None, wrong types, corrupt JSON) recover to defaults without crash.
- Release pipeline produces installable artifacts for Windows and macOS.
- Interrupted/failed/cancelled jobs recover with truthful per-stage outcomes; no false-success records or derivative collisions remain.
- The agreed editor/Premiere workflow passes with recorded hardware/app/codec versions; phone development access is evaluated separately.

## 13. Dependencies and Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Heavy model initialization and contention across workers | High | One coordinated scheduler and worker/model ownership; processing jobs now serialize and project process ownership protects embedded Chroma; interactive search and legacy watcher/translation coordination still need work |
| Hardware variance (CUDA versions, MPS quirks, CPU-only) | High | Auto-detection in `AIBackend`, architecture-aware `TORCH_CUDA_ARCH_LIST`, graceful CPU fallback |
| PyQt6/torch DLL load-order conflict on Windows | Medium | Existing pre-import/PATH mitigation; installed-build regression validation pending |
| FFmpeg unavailable on another installation | Medium | Mac launcher supplies Homebrew PATH; FFmpeg/FFprobe 9.1 and generated derivatives verified here; check other installations explicitly |
| Long-clip and large-library memory pressure | High | Bounded scene/frame/transcript batches and measured limits; dynamic batch sizing alone is insufficient |
| First-run model/environment capacity | High on this Mac | Default 20 GiB reserve/estimates enforced per filesystem; cached-only jobs. About 8.2 GiB free internally at the latest pipeline check fails preflight; manual model downloads are a separate path |
| Third-party model availability (HuggingFace, Whisper, YOLO) | Low | Models are cached locally after first download; no runtime API calls except optional DeepL |
| Schema migration and cross-store publication | High | Versioned migrations, backups, per-stage generations, reconciliation; WAL alone does not make SQLite/Chroma writes atomic |

## 14. Decisions (Resolved from Prior Open Questions)

| Question | Decision |
|---|---|
| Which features gate the wedding workflow? | Superseded task order. Discovery will choose the first editor outcome and prioritize source review, context export, collections and Premiere handoff accordingly. |
| Minimum supported hardware? | Establish from measured pilots for selected models. No validated 8 GB universal minimum is claimed. Mac Apple Silicon and Windows CUDA/CPU remain target platforms. |
| Search latency target? | Proposed p95 <3 seconds on declared hardware/library; measure cold/warm cache separately. |
| Phone usage? | Codex for development prompts/progress; outside CyneDirector product requirements. |
| Editing integration? | Adobe Premiere; narrow, tested selects exchange. Format, scope and acceptance will follow discovery and the agreed NLE handoff in buildplan.md. |
