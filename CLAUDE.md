# CLAUDE.md - CyneDirector v2.1.0

## Current execution context — 24 November 2026

The checkout was restored from `kanatwork/CyneDirector` at upstream
`efd093023c2b30410a5f11553b251e94f69e9f88`. Use [buildplan.md](buildplan.md)
for current work and [PRD.md](PRD.md) for requirements. The original Gameplan v3
is archived; it is not the active task order.

**Product scope corrected:** target working video editors on Apple Silicon Macs
and Windows PCs; Intel Macs are excluded. Phone usage means Codex supervising
software development, not a CyneDirector mobile experience. Read
[product discovery](docs/product-discovery.md) and questionnaire answers before
selecting another feature. The active [build plan](buildplan.md) now begins with
editor discovery and a full application redesign before workflow completion,
as explicitly chosen by the user. **36/36 answers** are recorded in
[product-decisions.json](docs/product-decisions.json). Question 27B confirms a
search-first home screen with recent results.
Use inline chat only, never popup forms. Read the [product brief](docs/product-brief.md).
Fast shot/performance/dialogue retrieval and immediate source review earn daily use;
grounded story development is the larger promise. Both in-app AI and portable
context export are launch scope; optional cloud analysis is offered during project
setup. Launch speech scope is English, including Indian English accents; Hindi,
multilingual/code-switching and translation requirements are deferred. Preserve
existing multilingual data/capabilities. Premiere
markers/selects use tested file interchange; validation starts on the user’s own
available projects. Add the [GitHub release updater](docs/release-updater.md) to
packaged desktop delivery. These decisions are requirements, not completed features.
Whole-app design precedes new workflow completion; no automatic model/framework
migration or current footage upload is authorized by these questionnaire answers.

The latest [technical audit](docs/audits/2026-11-24-workspace-relinking.md) still
records valid local implementation/tests. Its 67/100 used the old phone-inclusive
rubric and is historical. Define a new product rubric after discovery; do not
inflate a score by removing phone scope. Actual editor utility and Premiere
acceptance remain unproved. See [models](docs/models.md) for actual loaders,
cached/tested weights and important context-coverage gaps. The
[dated candidate review](docs/model-evaluation-2026-11-24.md) checks newer publisher
releases without installing or choosing a winning model.

This Mac: M4 Pro / 48 GiB, macOS 27.2.1 arm64. Full Python dependencies are
installed in `.venv` (Python 3.11.18); FFmpeg/FFprobe 9.1 and CMake are available
through Homebrew. Use `./run.command` to launch, `./setup_macos.sh` to reproduce the
pinned set in `requirements-macos.lock`. An in-place setup repeat passed. Core
weights are cached: CLIP/BLIP-large/YOLOv8m use MPS; Whisper small uses CPU/int8.
The first-run registry/default still requests large-v3; skip that extra download
and choose small in project settings for the tested configuration. BLIP-2/LLM and
large-v3 weights were not tested. About 8.2 GiB remains free internally; no wedding
SSD was mounted. The default 20 GiB reserve correctly blocks this filesystem.
Choose actual storage/backup paths before wedding processing.

## What This Project Does

CyneDirector currently implements AI-assisted video indexing and semantic search.
The accepted product is a footage-search and story-development companion for solo
editors/small teams, across weddings, fiction, documentaries, commercials and social.
The complete review/story/AI/export/updater experience remains planned.

**Core capabilities:**
- Semantic visual search using CLIP embeddings
- Automatic speech transcription via Whisper
- Scene description generation via BLIP-2 / BLIP-large
- YOLOv8 object detection with bounding boxes
- Translation of transcripts (DeepL or Whisper-based)
- LLM-powered video summarization (Llama-3.2 / Phi-3 fallback)
- Face database backend (not yet a complete indexing/search/UI workflow)
- SRT subtitle export
- Background incremental indexing

## Architecture

```
main.py                  Entry point (DLL load-order fix, crash handler) -> ProjectDialog -> MainWindow
config.py                Global config, constants; re-exports COLORS/STYLESHEET from gui/theme.py; per-project settings helpers (get_setting/load_project_settings/save_settings)
run.bat                  Windows launcher — invokes venv Python directly (avoids system Python conflicts)
```

### core/ — Business Logic Layer
Business logic mixed with Qt adapters: `workflow_manager.py`, `background_indexer.py`,
and `model_manager.py` import Qt. Extract shared processing services before claiming
a headless CLI/API. Singletons and locks exist, but complete thread/model ownership
and worker shutdown are open audit items.

| Module | Purpose |
|---|---|
| `ai_models.py` | AIBackend singleton — loads/manages CLIP, BLIP-2, YOLOv8, Whisper, LLM models. Auto-detects GPU compute capability at import time. `configure_from_settings()` applies device preference. `get_whisper_params()` respects `whisper_model` setting. `load_blip()` respects `blip_variant` setting. |
| `database.py` | SQLite (metadata, WAL mode) + ChromaDB (vector embeddings). Connection-per-thread via `threading.local()` |
| `search_engine.py` | Multi-modal semantic search with query expansion, decomposition, YOLO object matching, pagination, caching |
| `tags.py` | Tag hierarchy and vocabulary for visual indexing |
| `translator.py` | Language detection and translation (DeepL / Whisper) |
| `summary_generator.py` | LLM-based video summarization with template fallback |
| `project_manager.py` | Recent projects, `.cyne` project file management |
| `workflow_manager.py` | Legacy GUI queue builder; configured visual/speech scope is submitted durably before execution |
| `workspace.py` | Pinned current/historical roots, stable-key → physical IO resolution, FFprobe inventory, capacity/reserve estimates and anchored artifact directories |
| `workspace_changes.py` | Checksummed preview/apply plans, identity/hash verification, source bindings, stable atomic revisions and old-output preservation |
| `source_state.py` | Source signatures and processing-scoped resolver context; keep IO paths separate from persistent source keys |
| `jobs.py` | Additive SQLite job/asset/item/event ledger, idempotency, controls, leases and attempts |
| `job_runner.py` | Serial orchestration, heartbeats, stage checkpoints, wait/failure/cancel/retry and crash reconciliation |
| `processing.py` | Lazy shared adapters to existing model algorithms, publication context, cached-model policy |
| `processing_lock.py` | Local processing ownership and embedded-Chroma project process lock |
| `memory_budget.py` | Explicit buffer/metadata/record policy, bounded histories, safe overflow |
| `bounded_speech.py` | Temporary PCM windows, owned decoder cancellation, word-timed source-relative joins |
| `retention.py` | Additive tracked-generation/artifact catalog, dry-run protection, verified quarantine, restore/pin and delayed purge |
| `media_engine.py` | FFprobe wrapper for video metadata extraction |
| `face_db.py` | Face recognition database — SQLite-backed (encodings, names, appearances). Auto-migrates legacy pickle/json on first run |
| `performance.py` | Dynamic batch sizing based on available RAM, memory monitoring |
| `logger.py` | Centralized logging (console + file handlers) |
| `srt_exporter.py` | SRT subtitle file export |
| `background_indexer.py` | Incremental background file indexing |
| `model_manager.py` | Model registry, HF/YOLO cache detection, `ModelDownloadWorker(QThread)` for pre-downloading AI models |
| `proxy_generator.py` | FFmpeg-based 720p proxy video generation, 320x180 thumbnail extraction, `check_ffmpeg_available()` helper |
| `settings_manager.py` | Per-project settings persistence — JSON load/save in `_cyne_db/settings.json`, defaults merging, `SettingsManager` class |

### gui/ — Presentation Layer (PyQt6)
Dark theme UI with configurable accent color (default Indigo `#6366f1`). All heavy work delegated to workers.

| Module | Purpose |
|---|---|
| `theme.py` | Centralized design system — color palette, fonts, spacing, `generate_stylesheet()`, `set_accent_color()` for runtime accent changes |
| `main_window.py` | Main application window, layout, menu, settings wiring |
| `search_tab.py` | Search interface with pagination controls |
| `media_tree.py` | Project file tree browser |
| `metadata_panel.py` | Metadata display for selected media |
| `activity_log.py` | Activity/logging UI panel |
| `player_window.py` | Standalone video player window |
| `embedded_player.py` | Embedded player widget |
| `project_dialog.py` | Project creation/open dialog |
| `query_builder_dialog.py` | Advanced search query builder |
| `tag_chip_widget.py` | Tag chip display component |
| `toast_notification.py` | Toast notification popups |
| `shortcuts_panel.py` | Keyboard shortcuts reference |
| `animations.py` | Reusable QPropertyAnimation helpers (fade, slide, pulse) with reduce-motion support |
| `model_download_dialog.py` | Pre-download dialog for AI models — shows cache status, progress bars, skip/download |
| `workspace_jobs_dialog.py` | Workspace setup, durable job submission/status and controls |
| `settings_dialog.py` | Settings panel — 750x550 modal with 5 category tabs (General, AI/Models, Indexing, Appearance, API Keys), AnimatedToggle, color picker |

#### gui/widgets/ — Reusable Components

| Module | Purpose |
|---|---|
| `animated_toggle.py` | iOS-style animated toggle switch for boolean settings |
| `search_bar.py` | Unified search bar with icon, placeholder, Ctrl+K hint, glow effect |
| `status_indicator.py` | Pulsing status dot + label for device/state info |
| `thumbnail_card.py` | Grid-view card with thumbnail, filename, status badges, hover shadow |

### workers/ — Background Processing (QThread)
Emit PyQt signals for progress/results. Cancellation flags and manager pause state
exist; reliable pause/resume/cancel and truthful per-file outcomes are open W1a work.

| Module | Purpose |
|---|---|
| `job_worker.py` | Qt adapter to shared durable JobRunner; GUI close pauses at a file/stage boundary |
| `indexer.py` | Visual indexing — extracts frames, generates CLIP embeddings/tags, runs YOLOv8 object detection, thumbnail/proxy generation |
| `transcriber.py` | Audio transcription via Whisper |
| `transcribe_translate_worker.py` | Combined transcription + translation pipeline |
| `importer.py` | Folder import scanner |
| `file_watcher.py` | Watchdog-based project directory monitor — emits `new_file_signal`/`file_modified_signal` with 2s debounce |

### Data Flow
```
Configured GUI queue / Workspace & Jobs / cyne_cli
  -> JobStore (durable scope/settings/items/events)
  -> JobRunner -> Workspace preflight -> AppProcessor -> existing model algorithms
  -> Database generation publication + atomic job checkpoint
  -> JobStore completion -> status/events / GUI
Legacy watcher/translation and SearchEngine remain separate integration surfaces.
```

### Per-Project File Structure
```
project_dir/
  project_name.cyne          # Project metadata
  *.mp4, *.mov, ...          # Video files
  _cyne_db/                  # Database folder
    metadata.db              # SQLite
    ...                      # ChromaDB files/collections live directly in _cyne_db/
    faces/                   # Face encodings + names
    indexed_files.json       # Processing tracker
    settings.json            # User settings (persisted by SettingsManager)
```

## Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `PyQt6` | >=6.6.0 | GUI framework |
| `torch` | >=2.6.0 | Deep learning (GPU via CUDA) |
| `transformers` | >=4.35.0 | CLIP, BLIP-2, LLM model loading |
| `faster-whisper` | >=1.0.0 | Speech-to-text transcription |
| `chromadb` | >=0.4.18 | Vector database for embeddings |
| `opencv-python` | >=4.8.0 | Video frame extraction |
| `face_recognition` | >=1.3.0 | Face detection/embedding |
| `ultralytics` | >=8.0.0 | YOLOv8 object detection |
| `psutil` | >=5.9.0 | RAM monitoring for dynamic batch sizing |
| `python-dotenv` | >=1.0.0 | Load `.env` file for API keys and config |
| `numpy` | <2.0.0 | Numerical operations |
| `deepl` | >=1.0.0 | Translation API (optional) |
| `watchdog` | >=3.0.0 | Filesystem monitoring for auto-detecting new/modified videos |

**External:** FFprobe / FFmpeg (for video metadata extraction, proxy generation, and thumbnails)

### Environment Variables

Configured via a `.env` file in the project root (see `.env.example`):

| Variable | Purpose |
|---|---|
| `DEEPL_API_KEY` | DeepL API key for high-quality translation (optional, falls back to Whisper) |

## AI Models Used

| Model | ID | Purpose |
|---|---|---|
| **CLIP** | `openai/clip-vit-large-patch14` | Visual embeddings (768-D) for semantic search and tag matching |
| **BLIP-large** | `Salesforce/blip-image-captioning-large` (default) | Scene captioning (444M params, ~1GB VRAM) |
| **BLIP-2** | `Salesforce/blip2-opt-2.7b` (opt-in via `blip_variant` setting) | Higher-quality captions (2.7B params, ~3GB VRAM) |
| **YOLOv8** | `yolov8m.pt` (medium) | Bounding-box object detection (80 COCO classes, 0.4 conf threshold) |
| **Whisper** | `large-v3` / `medium` (faster-whisper) | Speech transcription (accuracy vs speed mode; overridden by `whisper_model` setting) |
| **Llama-3.2** | `unsloth/Llama-3.2-3B-Instruct` (4-bit quantized) | Summary generation |
| **Phi-3** | `microsoft/Phi-3-mini-4k-instruct` | LLM fallback if Llama fails to load |

Models are lazily loaded (only when needed) and managed by the `AIBackend` singleton.

## Testing

### Smoke Tests
Run from the project root:

```
venv\Scripts\python.exe -m tests.smoke_search
```

`tests/smoke_search.py` exercises `SearchEngine` internals without GPU or real project data.
It installs lightweight import stubs for optional heavy dependencies (`torch`, `numpy`,
and selected `core.*` modules), so it can run in minimal environments.

Coverage (33 tests):
- **Query operator parsing** — AND/OR/NOT boolean operators, `score:>80` / `score:<50` ranges, `duration:30-60`, `"phrase"` extraction, `field:value` searches
- **Quoted field values** — validates `dialogue:"hello world"` and mixed operator + field queries
- **Temporal query return shape** — verifies `_search_temporal_sequence` returns a `dict` (keyed by match type), not a list
- **Temporal + search integration** — verifies temporal results integrate with `search()` paginated response shape
- **Filter application** — score range, field-specific, and phrase filters via `_apply_query_filters`
- **Paginated response shape** — `search()` returns `dict` with `results`, `total`, `page`, `total_pages`
- **Query expansion & decomposition** — `_expand_query` produces capped variations; `_decompose_query` splits on prepositions

Tests use `SearchEngine.__new__()` with fake DB/AI/FaceDB stubs to bypass `__init__` and avoid loading any models.

### Current verification (24 November 2026, local work on efd0930)

Run suites separately (search tests install global stubs); use bash for the
environment helper:

```bash
source scripts/macos_env.sh
.venv/bin/python -m tests.smoke_search
.venv/bin/python -m unittest tests.test_review_regressions -q
.venv/bin/python -m unittest tests.test_safe_reprocessing -q
.venv/bin/python -m unittest tests.test_workspace_jobs -q
.venv/bin/python -m unittest tests.test_memory_retention -q
.venv/bin/python -m unittest tests.test_worker_memory -q
.venv/bin/python -m unittest tests.test_workspace_changes -q
.venv/bin/python -m tests.memory_retention_benchmark
.venv/bin/python -m tests.runtime_smoke
.venv/bin/python -m tests.macos_startup_smoke
.venv/bin/python -m tests.durable_runtime_smoke
.venv/bin/python -m tests.workspace_gui_smoke
.venv/bin/python -m tests.macos_ai_smoke --offline
```

33 + 23 + 28 + 39 + 41 + 3 + 34 = **201** regression checks pass. The new suite uses real
SQLite/filesystem/processes and selected real Chroma publications to cover leases,
actual kill/restart, duplicate submissions, pause/cancel/retry, root disappearance,
replacement/creation races, capacity grouping, path aliases, future schema rejection
and publication-before-ledger reconciliation. No models or wedding footage in it.

`durable_runtime_smoke` runs the actual JSON CLI with real cached CLIP/BLIP/YOLO/
Whisper on generated video/speech, separate workspace derivatives and seeded legacy
data. It checks hashes, fields, old vectors, generation stamps, three successful
stages and unchanged attempts on repeat. `workspace_gui_smoke` tests native dialog
submission with real FFprobe and configured primary queue/Qt ownership; its visual/
speech publication adapter is a double. The real algorithms are tested separately
through the CLI. Previous runtime handoff/shutdown and native startup checks pass.
See the [latest evidence](docs/audits/2026-11-24-workspace-relinking.md).

### Durable jobs and storage

Use `db.publication_context(checkpoint, allowed)` around a durable model stage.
`reprocess` adds a `{stage}_job_checkpoint` with item, settings, source signature
and generation to the same metadata transaction as the publication pointer.
Reconciliation must match every field and the active generation; an old stamp on
a tombstone is not proof of completion. Never mark a job item complete just because
a worker thread ended.

`Workspace` config and `jobs.sqlite3` are additive sidecars. Canonicalize only for
containment/identity; preserve existing metadata source keys (including Mac path
aliases). `source_key` resolves aliases to the stored key; `media_path`/
`resolve_source` resolves IO through pinned current roots. Workers normalize keys
before staging; never hash a new mount path into an existing asset identity.
`workspace_changes` is the only supported configuration updater: serialize with
processing/submission, preview/verify, then replace one complete configuration.
Never mass-rewrite job payloads, vector source fields or `.cyne` files to relink.
Sources are read-only. New derivatives use pinned, generation-specific
output namespaces; only explicit verified retention may move/delete tracked old
artifacts. Managed FFmpeg destinations
must already exist and are never recursively recreated by its helpers.

`JobStore` is Qt/AI-free; `JobRunner` imports inference adapters lazily. Job
settings are frozen and API keys excluded. Pause/cancel/retry are durable requests;
completed work stays recorded. Default request hashes deduplicate repeated CLI
submissions; new request keys or GUI Force analysis request deliberate reprocessing.
Configured GUI Start workflow also records an explicit new analysis scope.
Project process locks prevent a detached Chroma writer opening a GUI-owned project.
See the [guide](docs/workspace-jobs.md) for command and lifecycle details.

### Generation publication

`core/generations.py` wraps visual/temporal/transcript collections with published
views. Use `db.reprocess(path, stage, signature, allowed=...)` for worker writes;
never bypass this with raw vector writes or delete prior generations on retry.
Stage metadata stays private until one SQLite commit selects its generation.
Existing records without a generation remain valid legacy data. Metadata uses
`visual_generation`, `transcript_generation`, `vector_publication_version: 1`.
New generations/artifacts register before writes and retire in the publication
transaction. Explicit retention protects current/recent/pinned/job-referenced data;
verified quarantine precedes deletion and supports recovery. Untracked data stays
protected. Use the [memory/retention contract](docs/memory-retention.md); never add
raw delete-on-retry or automatic purge. Reads/publication/retention use the database
RLock; composed reads use `read_snapshot()`. ANN widening caps at 256 then uses
paged exact top-k fallback when necessary. Synthetic cost/recovery checks pass;
whole-library materialization, physical compaction and real scale remain open.

`core/scene_timing.py` stores observed sampled cuts and representative frame times.
Decoder PTS is preferred; frame/fps fallback is labelled `estimated_cfr`. Do not
claim exact NLE/SMPTE/VFR timecode precision from sampled scene bounds.

## Known Issues

- Mac GUI/AI setup, native startup, actual Qt handoff/shutdown, and core inference
  samples and actual synthetic CLI model processing pass. Packaging, other hardware,
  physical SSD faults and wedding throughput/quality acceptance remain pending.
- Generation-aware reads must be used. Earlier builds cannot safely interpret
  mixed generations; restore a project backup for an older-build rollback.
- Bounded buffers/windowed speech and explicit retention pass synthetic checks;
  real long-clip model/native peaks and speech joins still need acceptance. No
  automatic compaction/quotas, independent embedding jobs/model-version freshness,
  or project/old-derivative/cache migration yet. Source-root relinking and safe
  future-destination updates pass. Jobs recover at file/stage boundaries.
- The legacy combined worker uses bounded transcription but rejects long Whisper
  translation rather than decode an entire long source. Thumbnail/proxy child
  cancellation and interactive search/model ownership remain open.
- Engine query/cache fixes exist; GUI duration/filter/sort/page semantics need work.
- **Desktop workflow gaps:** legacy translation and automatic watcher queues remain
  transient; interactive search needs shared model ownership. Prioritize these
  against the accepted editor journey. Codex phone development is separate from
  product requirements; see [scope clarification](docs/phone-control.md).
- **No Premiere selects interchange:** SRT exists; precise selects/sequence export
  and editing-proxy compatibility remain product/validation backlog. Current H.264 previews are not yet
  certified for attaching as Premiere editing proxies.

- **Limited export formats** — only SRT currently supported
- **No undo/redo** functionality in the UI
- **No timeline visualization** for search results or scenes
- **Face recognition** is available but not actively wired into the indexing workflow
- **Memory risk** with very large video libraries (mitigated by dynamic batch sizing but no streaming yet)
- **Single-user only** — no collaboration or cloud sync features
- **GPU compatibility:** MPS CLIP/BLIP-large/YOLOv8m samples pass on this M4 Pro
  with torch 2.11.0. Other GPUs and historical CUDA configurations require fresh
  validation. Current Mac speech uses CPU/int8; experimental MPS speech is not enabled.

## Windows DLL Load-Order Fix (`main.py`)

PyQt6 and torch both bundle C++ runtime DLLs (`vcruntime140.dll`, `msvcp140.dll`). If PyQt6 is imported first, its copies get locked into the process and torch's `c10.dll` fails to initialize (`WinError 1114`). Additionally, a foreign Python on the system PATH (e.g. `C:\Python314`) can inject incompatible DLLs.

`main.py` handles this at the top of the file, before any library imports:
1. Strips non-venv Python directories from `PATH`
2. Prepends `torch/lib` to `PATH`
3. Pre-imports `torch` **before** PyQt6

If torch is not installed, the pre-import is silently skipped. Use `run.bat` to launch the app — it invokes `venv\Scripts\python.exe` directly so the correct Python is always used.

## Development Conventions

### Code Organization
- Standard library imports first, then third-party, then local (`from core.xxx import ...`)
- Each module initializes its own logger: `logger = get_logger(__name__)`

### Naming
- **Classes:** PascalCase (`AIBackend`, `MainWindow`, `SearchEngine`)
- **Functions/methods:** snake_case (`get_optimal_batch_size`, `detect_language`)
- **Constants:** UPPER_SNAKE_CASE (`MAX_CHARS_PER_LINE`, `THUMBNAIL_SIZE`)
- **Private methods:** underscore prefix (`_expand_query`, `_index_single_file`)
- **PyQt signals:** descriptive with `_signal` suffix (`progress_signal`, `log_signal`, `finished_signal`)

### Patterns
- **Singleton** for expensive resources: `AIBackend`, `Database`, `ProjectManager`, `FaceDB`
- **Connection-per-thread** for SQLite — each thread gets its own connection via `threading.local()`, WAL mode + `busy_timeout=5000` for concurrent access. `_lock` wraps entire read-modify-write sequences to prevent lost updates.
- **Signal/Slot** for thread-to-UI communication (PyQt6 signals)
- **Workflow Manager** for task queuing with priority levels (high/normal/low)
- **Graceful degradation** — LLM fails -> template-based summary; model unavailable -> skip
- **Settings-driven runtime** — per-project settings from `_cyne_db/settings.json` are wired to actual runtime behavior (see Settings Wiring below)

### Settings Wiring

The settings wiring pass is implemented as follows; this table describes code
paths, not acceptance of every input or the open audit failure cases:

| Setting Key | Wired To | Notes |
|---|---|---|
| `auto_index_on_change` | `MainWindow.__init__` + `_apply_settings_changes()` | Controls file watcher start/stop |
| `generate_thumbnails` | `workers/indexer.py` Phase 6 | Gated by `get_setting()` per file |
| `generate_proxies` | `workers/indexer.py` Phase 6 + `config.GENERATE_PROXIES` flag | Gated by `get_setting()` per file |
| `batch_size` | `IndexerWorker.__init__` | `"auto"` -> `get_optimal_batch_size()`, int -> direct use; robust parsing with 1-128 clamp |
| `keyframe_interval` | `IndexerWorker.__init__` | Derives `min_interval`/`max_interval` from setting value; robust parsing with 1-10 clamp |
| `device` | `AIBackend.configure_from_settings()` | Called on project load and settings change; `"auto"` re-runs detection; switches device if no models loaded |
| `blip_variant` | `AIBackend.load_blip()` | Reads setting directly; falls back to `config.USE_BLIP2` |
| `whisper_model` | `AIBackend.get_whisper_params()` | Overrides accuracy-mode model name (default `large-v3`) |
| `sidebar_default` | `MainWindow.__init__` + `_apply_settings_changes()` | Collapses/expands sidebar to match preference |
| `accent_color` | `MainWindow.__init__` + `_apply_settings_changes()` | Calls `set_accent_color()` then regenerates stylesheet |
| `deepl_api_key` | `MainWindow.__init__` + `_apply_settings_changes()` | Sets `config.DEEPL_API_KEY` and `TRANSLATION_METHOD` |
| `language_preference` | `workers/transcriber.py` + `workers/transcribe_translate_worker.py` | Maps UI values (`auto`, `english`, `spanish`, `french`, `german`, `japanese`, `chinese`, `korean`) to Whisper language hint (`None`, `en`, `es`, `fr`, `de`, `ja`, `zh`, `ko`); `auto`/missing/invalid keeps Whisper auto-detect |
| `model_quality` | Informational | Reserved; workflow mode (speed/accuracy) set by UI radio buttons |
| `theme` | Reserved | Single dark theme currently; token ready for future use |

Global flags (`USE_BLIP2`, `GENERATE_PROXIES`, `DEEPL_API_KEY`, `TRANSLATION_METHOD`) are synced from per-project settings both at project load (`MainWindow.__init__`) and on settings dialog save (`_apply_settings_changes()`).

### Error Handling
- Try/except with `logger.error(...)` at the point of failure
- Workers emit error messages via `log_signal`
- Fallback paths when AI models fail (template summaries, skip operations)

### UI Theme
- Cinema Dark with configurable accent (default Indigo `#6366f1`), background `#0f0f0f`, surface `#1a1a1a`
- All design tokens centralized in `gui/theme.py` (`COLORS` dict, module-level constants, `generate_stylesheet()`)
- `set_accent_color(hex)` accepts only valid `#RRGGBB`, falls back to default Indigo `#6366f1` for invalid values, and updates `ACCENT`/`ACCENT_HOVER`/`GLOW` plus the `COLORS` dict in one call before `generate_stylesheet()`
- `config.py` re-exports `COLORS` and `STYLESHEET` for backward compatibility
- Font: Inter / Segoe UI, 13px base

### GPU Support
- `TORCH_CUDA_ARCH_LIST` is set dynamically at import time based on `torch.cuda.get_device_capability()`
- Supported architectures: Turing 7.5 (RTX 20), Ampere 8.0/8.6 (RTX 30), Ada 8.9 (RTX 40), Hopper/Blackwell 9.0+ (RTX 50)
- Unknown/newer GPUs fall back to the highest known arch (`9.0`)
- TF32 and `cudnn.benchmark` enabled for Ampere+ speedups

### Performance Conventions
- Dynamic batch sizing based on available RAM (`core/performance.py`)
- Search results paginated (50 per page) with 5-minute TTL cache
- Incremental indexing — only re-index files modified since `last_scanned`
- Lazy model loading — models loaded on first use, not at startup
- Float16 precision for GPU inference

### Version & Project Files
- Version tracked in `config.py` (`VERSION = "2.1.0"`)
- Project files use `.cyne` extension
- Database stored in `_cyne_db/` subdirectory within project folder
