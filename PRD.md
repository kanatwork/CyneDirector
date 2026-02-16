# PRD.md — CyneDirector Beta Product Requirements

## 1. Document Control

- **Product:** CyneDirector v2.1.0
- **Stage:** Beta execution (post-Phase 5.1 baseline)
- **Owner:** Product + Engineering
- **Last updated:** 2026-02-17
- **Architecture reference:** See `CLAUDE.md` for full technical architecture, module map, and development conventions.

## 2. Product Vision

CyneDirector is a desktop AI video intelligence tool that makes large media libraries searchable by meaning, dialogue, objects, and people — while staying usable for real editor workflows. All processing runs locally; no cloud account or upload required.

## 3. Problem Statement

Video teams lose hours manually locating moments across large libraries. Filename and folder search is insufficient for scene-level retrieval and spoken-content discovery. Existing cloud solutions require uploading sensitive footage and ongoing subscriptions. There is no local-first tool that combines visual, audio, and object-level search in a single interface.

## 4. Target Users

- **Video editors** managing large project archives (hundreds to thousands of files)
- **Content teams** reusing clips across channels and campaigns
- **Researchers and analysts** searching long-form footage for specific moments
- **Solo creators** needing quick retrieval without cloud lock-in or subscription costs

## 5. Goals

- **G1 — Reliable daily workflow:** A user can import, index, search, inspect, and export without encountering blocking bugs or data loss.
- **G2 — Settings users can trust:** Every setting in the UI controls real runtime behavior. Changing a setting and restarting the app produces the expected result without workarounds.
- **G3 — Predictable search experience:** Filters, sort, and pagination behave consistently across repeated searches. The same query returns the same results.
- **G4 — Multi-modal retrieval:** Users can find footage by visual similarity, spoken dialogue, detected objects, and temporal context — individually or combined.
- **G5 — Hardware-adaptive stability:** The app runs reliably on CUDA (Windows), MPS (macOS), and CPU-only systems, automatically selecting the best available backend.

## 6. Non-Goals (Current Beta Window)

- Multi-user collaboration or cloud sync
- Full timeline editing or NLE integration
- Advanced permissions or role-based access
- Export formats beyond SRT subtitles and transcript reports
- Linux support (untested; not blocked but not validated)

## 7. Scope

### 7.1 In Scope (Beta)

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

### 7.3 Next Scope — Not Started

- OCR / text-in-video retrieval
- Offline drive metadata and online/offline result state
- Virtual collections and production tag workflows
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
- FR-2.4: Incremental indexing skips files unchanged since `last_scanned` timestamp.
- FR-2.5: Batch size is configurable ("auto" uses RAM-based dynamic sizing via `core/performance.py`, or user-specified 1–128).
- FR-2.6: File watcher detects new or modified files and triggers re-indexing when `auto_index_on_change` is enabled.

### FR-3 Search

- FR-3.1: User can enter a natural-language query and receive ranked results with relevance scores.
- FR-3.2: Search supports boolean operators (AND, OR, NOT), quoted phrase matching, and query expansion.
- FR-3.3: Search supports field-specific filters: `visual:`, `dialogue:`, `objects:`, `cast:`.
- FR-3.4: Search supports range filters: `score:>80`, `score:<50`, `duration:30-60`.
- FR-3.5: Search supports temporal sequence queries (e.g., "A then B").
- FR-3.6: Results are paginated (50 per page) with a 5-minute TTL cache.
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

## 9. Non-Functional Requirements

### NFR-1 Stability

- Crash-free session rate target: >=99% in beta cohort.
- No unhandled exceptions in the main thread. Worker exceptions are caught and reported via signals.

### NFR-2 Performance

- UI thread remains responsive (no blocking) during all background indexing and search operations.
- Search results returned within 3 seconds on indexed projects up to 5,000 files (warm cache: <500ms).
- Indexing throughput: at least 1 file per minute on CPU-only systems with default settings.

### NFR-3 Compatibility

| Platform | GPU Backend | Status |
|---|---|---|
| Windows 10/11 | CUDA (Turing 7.5 through Ada 8.9) | Primary, tested |
| Windows 10/11 | CPU fallback | Tested |
| macOS (Apple Silicon) | MPS | Secondary, functional |
| macOS (Apple Silicon) | CPU fallback | Functional |
| Linux | Any | Untested, not officially supported |

- **Known limitation:** RTX 5070 (sm_120 / Blackwell) requires PyTorch built with CUDA 12.8+. Current torch 2.10+cu126 supports up to sm_90. GPU falls back to CPU on unsupported architectures.
- **Known mitigation:** PyQt6/torch DLL load-order conflict on Windows (`WinError 1114`) is resolved by `main.py` pre-importing torch before PyQt6 and stripping foreign Python directories from PATH.

### NFR-4 Data Safety

- Existing projects must open without destructive migrations.
- Schema and data updates must be backward-compatible or safely migrated (e.g., `face_db.py` auto-migrates legacy pickle/JSON formats).
- Settings files with unknown keys are preserved (merged with defaults, not overwritten).

### NFR-5 Storage

- Database footprint (SQLite + ChromaDB embeddings) should remain under 500MB for projects with up to 5,000 indexed files.
- Proxy videos and thumbnails are opt-in to avoid unexpected disk usage.

### NFR-6 First-Run Experience

- AI models are downloaded on first use (lazy loading), not at install time.
- Pre-download dialog shows cache status and allows users to download models proactively.
- Total model download size: approximately 5–8 GB (CLIP ~600MB, BLIP ~1GB, Whisper large-v3 ~3GB, YOLO ~50MB, LLM ~2GB). Users on slow connections should be warned.

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

## 13. Dependencies and Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Heavy model initialization and VRAM contention across workers | High | Lazy loading, VRAM release after worker completion, one model family active at a time |
| Hardware variance (CUDA versions, MPS quirks, CPU-only) | High | Auto-detection in `AIBackend`, architecture-aware `TORCH_CUDA_ARCH_LIST`, graceful CPU fallback |
| PyQt6/torch DLL load-order conflict on Windows | Medium | Resolved: `main.py` pre-imports torch, strips foreign Python from PATH |
| FFmpeg not installed | Medium | `check_ffmpeg_available()` helper; proxy/thumbnail features fail gracefully with log warning |
| Large-library memory pressure (>5,000 files) | Medium | Dynamic batch sizing via `core/performance.py`, paginated search results, incremental indexing |
| First-run model download (5–8 GB) | Medium | Pre-download dialog with cache status; lazy loading defers until needed |
| Third-party model availability (HuggingFace, Whisper, YOLO) | Low | Models are cached locally after first download; no runtime API calls except optional DeepL |
| Schema migration complexity as features grow | Low | SQLite WAL mode, backward-compatible merging in SettingsManager, FaceDB auto-migration |

## 14. Decisions (Resolved from Prior Open Questions)

| Question | Decision |
|---|---|
| Which features are beta gate vs allowed to slip? | Face recognition and LLM summarization are post-beta polish (partially built, not in critical path). OCR and virtual collections are post-beta new features. |
| Minimum supported hardware? | 8 GB RAM, any x86-64 CPU, Windows 10+ or macOS (Apple Silicon). GPU optional but recommended. |
| Search latency SLO? | 3 seconds max on cold cache for projects up to 5,000 files. <500ms on warm cache (5-minute TTL). |
