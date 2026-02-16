# CLAUDE.md - CyneDirector v2.1.0

## What This Project Does

CyneDirector is an AI-powered video management and semantic search desktop application. It indexes video content using vision, audio, and language AI models, then enables natural-language search across the indexed library (e.g., "person running in park"). Target users are video editors, content creators, researchers, and archivists.

**Core capabilities:**
- Semantic visual search using CLIP embeddings
- Automatic speech transcription via Whisper
- Scene description generation via BLIP-2 / BLIP-large
- YOLOv8 object detection with bounding boxes
- Translation of transcripts (DeepL or Whisper-based)
- LLM-powered video summarization (Llama-3.2 / Phi-3 fallback)
- Face recognition across videos
- SRT subtitle export
- Background incremental indexing

## Architecture

```
main.py                  Entry point (DLL load-order fix, crash handler) -> ProjectDialog -> MainWindow
config.py                Global config, constants; re-exports COLORS/STYLESHEET from gui/theme.py; per-project settings helpers (get_setting/load_project_settings/save_settings)
run.bat                  Windows launcher — invokes venv Python directly (avoids system Python conflicts)
```

### core/ — Business Logic Layer
No GUI dependencies. Uses singletons for expensive resources. Thread-safe with locks.

| Module | Purpose |
|---|---|
| `ai_models.py` | AIBackend singleton — loads/manages CLIP, BLIP-2, YOLOv8, Whisper, LLM models. Auto-detects GPU compute capability at import time. `configure_from_settings()` applies device preference. `get_whisper_params()` respects `whisper_model` setting. `load_blip()` respects `blip_variant` setting. |
| `database.py` | SQLite (metadata, WAL mode) + ChromaDB (vector embeddings). Connection-per-thread via `threading.local()` |
| `search_engine.py` | Multi-modal semantic search with query expansion, decomposition, YOLO object matching, pagination, caching |
| `tags.py` | Tag hierarchy and vocabulary for visual indexing |
| `translator.py` | Language detection and translation (DeepL / Whisper) |
| `summary_generator.py` | LLM-based video summarization with template fallback |
| `project_manager.py` | Recent projects, `.cyne` project file management |
| `workflow_manager.py` | Task queue with priority scheduling, pause/resume |
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
| `settings_dialog.py` | Settings panel — 750x550 modal with 5 category tabs (General, AI/Models, Indexing, Appearance, API Keys), AnimatedToggle, color picker |

#### gui/widgets/ — Reusable Components

| Module | Purpose |
|---|---|
| `animated_toggle.py` | iOS-style animated toggle switch for boolean settings |
| `search_bar.py` | Unified search bar with icon, placeholder, Ctrl+K hint, glow effect |
| `status_indicator.py` | Pulsing status dot + label for device/state info |
| `thumbnail_card.py` | Grid-view card with thumbnail, filename, status badges, hover shadow |

### workers/ — Background Processing (QThread)
Emit PyQt signals for progress/results. Support pause/resume/cancel.

| Module | Purpose |
|---|---|
| `indexer.py` | Visual indexing — extracts frames, generates CLIP embeddings/tags, runs YOLOv8 object detection, thumbnail/proxy generation |
| `transcriber.py` | Audio transcription via Whisper |
| `transcribe_translate_worker.py` | Combined transcription + translation pipeline |
| `importer.py` | Folder import scanner |
| `file_watcher.py` | Watchdog-based project directory monitor — emits `new_file_signal`/`file_modified_signal` with 2s debounce |

### Data Flow
```
User Input (GUI) -> WorkflowManager (queue) -> Worker Threads
  -> AIBackend (model inference) -> Database (SQLite + ChromaDB)
  -> SearchEngine -> GUI Display
```

### Per-Project File Structure
```
project_dir/
  project_name.cyne          # Project metadata
  *.mp4, *.mov, ...          # Video files
  _cyne_db/                  # Database folder
    metadata.db              # SQLite
    chroma_data/             # ChromaDB vector store
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

Coverage (23 tests):
- **Query operator parsing** — AND/OR/NOT boolean operators, `score:>80` / `score:<50` ranges, `duration:30-60`, `"phrase"` extraction, `field:value` searches
- **Quoted field values** — validates `dialogue:"hello world"` and mixed operator + field queries
- **Temporal query return shape** — verifies `_search_temporal_sequence` returns a `dict` (keyed by match type), not a list
- **Temporal + search integration** — verifies temporal results integrate with `search()` paginated response shape
- **Filter application** — score range, field-specific, and phrase filters via `_apply_query_filters`
- **Paginated response shape** — `search()` returns `dict` with `results`, `total`, `page`, `total_pages`
- **Query expansion & decomposition** — `_expand_query` produces capped variations; `_decompose_query` splits on prepositions

Tests use `SearchEngine.__new__()` with fake DB/AI/FaceDB stubs to bypass `__init__` and avoid loading any models.

## Known Issues

- **Limited export formats** — only SRT currently supported
- **No undo/redo** functionality in the UI
- **No timeline visualization** for search results or scenes
- **Face recognition** is available but not actively wired into the indexing workflow
- **`language_preference`** — persisted in settings but not yet consumed by translator/transcriber workers
- **Memory risk** with very large video libraries (mitigated by dynamic batch sizing but no streaming yet)
- **Single-user only** — no collaboration or cloud sync features
- **RTX 5070 (sm_120)** — torch 2.10+cu126 only supports up to sm_90; needs PyTorch built with CUDA 12.8+ for full GPU support

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

Every active setting key in `core/settings_manager.py` is wired to runtime behavior:

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
| `language_preference` | Persisted only | Not yet consumed by translator/transcriber; ready for future wiring |
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
- `set_accent_color(hex)` updates module-level `ACCENT`, `ACCENT_HOVER`, `GLOW` globals and the `COLORS` dict in one call; must be called before `generate_stylesheet()`
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
