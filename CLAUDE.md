# CLAUDE.md - CyneDirector v2.1.0

## What This Project Does

CyneDirector is an AI-powered video management and semantic search desktop application. It indexes video content using vision, audio, and language AI models, then enables natural-language search across the indexed library (e.g., "person running in park"). Target users are video editors, content creators, researchers, and archivists.

**Core capabilities:**
- Semantic visual search using CLIP embeddings
- Automatic speech transcription via Whisper
- Scene description generation via BLIP-2
- Translation of transcripts (DeepL or Whisper-based)
- LLM-powered video summarization (Llama-3.2 / Phi-3 fallback)
- Face recognition across videos
- SRT subtitle export
- Background incremental indexing

## Architecture

```
main.py                  Entry point → ProjectDialog → MainWindow
config.py                Global config, constants; re-exports COLORS/STYLESHEET from gui/theme.py
```

### core/ — Business Logic Layer
No GUI dependencies. Uses singletons for expensive resources. Thread-safe with locks.

| Module | Purpose |
|---|---|
| `ai_models.py` | AIBackend singleton — loads/manages CLIP, BLIP-2, Whisper, LLM models. Auto-detects GPU compute capability at import time |
| `database.py` | SQLite (metadata, WAL mode) + ChromaDB (vector embeddings). Connection-per-thread via `threading.local()` |
| `search_engine.py` | Multi-modal semantic search with query expansion, decomposition, pagination, caching |
| `tags.py` | Tag hierarchy and vocabulary for visual indexing |
| `translator.py` | Language detection and translation (DeepL / Whisper) |
| `summary_generator.py` | LLM-based video summarization with template fallback |
| `project_manager.py` | Recent projects, `.cyne` project file management |
| `workflow_manager.py` | Task queue with priority scheduling, pause/resume |
| `media_engine.py` | FFprobe wrapper for video metadata extraction |
| `face_db.py` | Face recognition database (encodings + names) |
| `performance.py` | Dynamic batch sizing based on available RAM, memory monitoring |
| `logger.py` | Centralized logging (console + file handlers) |
| `srt_exporter.py` | SRT subtitle file export |
| `background_indexer.py` | Incremental background file indexing |

### gui/ — Presentation Layer (PyQt6)
Dark theme UI with Indigo accent (`#6366f1`). All heavy work delegated to workers.

| Module | Purpose |
|---|---|
| `theme.py` | Centralized design system — color palette, fonts, spacing, `generate_stylesheet()` |
| `main_window.py` | Main application window, layout, menu |
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

### workers/ — Background Processing (QThread)
Emit PyQt signals for progress/results. Support pause/resume/cancel.

| Module | Purpose |
|---|---|
| `indexer.py` | Visual indexing — extracts frames, generates CLIP embeddings and tags |
| `transcriber.py` | Audio transcription via Whisper |
| `transcribe_translate_worker.py` | Combined transcription + translation pipeline |
| `importer.py` | Folder import scanner |

### Data Flow
```
User Input (GUI) → WorkflowManager (queue) → Worker Threads
  → AIBackend (model inference) → Database (SQLite + ChromaDB)
  → SearchEngine → GUI Display
```

### Per-Project File Structure
```
project_dir/
├── project_name.cyne          # Project metadata
├── *.mp4, *.mov, ...          # Video files
└── _cyne_db/                  # Database folder
    ├── metadata.db            # SQLite
    ├── chroma_data/           # ChromaDB vector store
    ├── faces/                 # Face encodings + names
    └── indexed_files.json     # Processing tracker
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
| `psutil` | >=5.9.0 | RAM monitoring for dynamic batch sizing |
| `python-dotenv` | >=1.0.0 | Load `.env` file for API keys and config |
| `numpy` | <2.0.0 | Numerical operations |
| `deepl` | >=1.0.0 | Translation API (optional) |

**External:** FFprobe (for robust video metadata extraction)

### Environment Variables

Configured via a `.env` file in the project root (see `.env.example`):

| Variable | Purpose |
|---|---|
| `DEEPL_API_KEY` | DeepL API key for high-quality translation (optional, falls back to Whisper) |

## AI Models Used

| Model | ID | Purpose |
|---|---|---|
| **CLIP** | `openai/clip-vit-large-patch14` | Visual embeddings (768-D) for semantic search and tag matching |
| **BLIP-2** | `Salesforce/blip2-opt-2.7b` | Natural language scene descriptions |
| **Whisper** | `large-v3` / `medium` (faster-whisper) | Speech transcription (accuracy vs speed mode) |
| **Llama-3.2** | `unsloth/Llama-3.2-3B-Instruct` (4-bit quantized) | Summary generation |
| **Phi-3** | `microsoft/Phi-3-mini-4k-instruct` | LLM fallback if Llama fails to load |

Models are lazily loaded (only when needed) and managed by the `AIBackend` singleton.

## Known Issues

- **No automated test suite** — no pytest, no unit or integration tests
- **Some debug logging** may still be scattered in the codebase
- **Limited export formats** — only SRT currently supported
- **No undo/redo** functionality in the UI
- **No timeline visualization** for search results or scenes
- **Face recognition** is available but not actively wired into the indexing workflow
- **Memory risk** with very large video libraries (mitigated by dynamic batch sizing but no streaming yet)
- **Single-user only** — no collaboration or cloud sync features

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
- **Graceful degradation** — LLM fails → template-based summary; model unavailable → skip

### Error Handling
- Try/except with `logger.error(...)` at the point of failure
- Workers emit error messages via `log_signal`
- Fallback paths when AI models fail (template summaries, skip operations)

### UI Theme
- Cinema Dark with Indigo accent (`#6366f1`), background `#0f0f0f`, surface `#1a1a1a`
- All design tokens centralized in `gui/theme.py` (`COLORS` dict, `generate_stylesheet()`)
- `config.py` re-exports `COLORS` and `STYLESHEET` for backward compatibility
- Font: Inter / Segoe UI, 13px base
- GUI files reference `COLORS['key']` — no hardcoded hex colors in `main_window.py`

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
