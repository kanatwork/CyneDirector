# CyneDirector - Gameplan v3 (Rewritten for Beta Execution)

Date: February 8, 2026  
Status baseline: `4.4 - Add Settings Panel` is complete.  
This document starts from the real current state and plans work from `5.0` onward.

## 1) Current Baseline (Actual Code State)

### 1.1 Confirmed in code

- Cross-platform device selection (CUDA -> MPS -> CPU) exists in `core/ai_models.py`.
- Whisper, CLIP, BLIP, YOLO model loading paths exist in `core/ai_models.py`.
- Visual indexing, YOLO detection, and metadata persistence exist in `workers/indexer.py`.
- Transcript generation and storage exist in `workers/transcriber.py`.
- Translation workflows exist in `workers/transcribe_translate_worker.py` and `core/translator.py`.
- Settings UI and persistence exist in `gui/settings_dialog.py` and `core/settings_manager.py`.
- File watcher + debounce exists in `workers/file_watcher.py`.
- Background incremental indexing exists in `core/background_indexer.py`.
- Model pre-download flow exists in `core/model_manager.py` and `gui/model_download_dialog.py`.
- FaceDB SQLite storage + migration exists in `core/face_db.py`.

### 1.2 Beta blockers and correctness gaps

- `Faces` and `Tags` navigation pages are still placeholders in `gui/main_window.py`.
- ~~Temporal search has a return-shape bug (`search()` expects mapping but temporal helper returns list) in `core/search_engine.py`.~~
- ~~Search filter UI omits active emitted types (e.g., `CAST`, `OBJECT (YOLO)`, `MULTI-MODAL`, `TEMPORAL SEQUENCE`) in `gui/search_tab.py`.~~
- ~~Search sort UI exposes options not implemented (`Duration`, `Date Added`) in `gui/search_tab.py`.~~
- Settings are only partially applied at runtime in `gui/main_window.py`.
- `auto_index_on_change` is not respected (watcher currently always starts) in `gui/main_window.py`.
- `generate_thumbnails` setting is not respected (thumbnails currently always generated) in `workers/indexer.py`.
- Search expects `faces` metadata, but indexing does not currently populate it end-to-end.
- Transcript embeddings are currently accuracy-mode only in `workers/transcriber.py`.
- ~~`WorkflowManager` defines `reorder_operation` twice in `core/workflow_manager.py`.~~
- Updater modules are missing (`core/updater.py`, `core/update_worker.py`, `gui/update_dialog.py`).
- Packaging/CI/release structure is missing (`build/`, `.github/workflows/`, `README.md`, `core/__version__.py`).
- OCR pipeline and offline-drive metadata flow are not implemented.
- Virtual collections are not implemented as a first-class feature.

### 1.3 Local verification completed

- Syntax compile check passed:
  - `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m compileall -q core gui workers main.py config.py`

## 2) CLAUDE.md Reconciliation

`CLAUDE.md` was used as context for architecture and intended capabilities. This plan corrects mismatches between intended capability and current shipped behavior:

- Claimed face-recognition capability is not yet a tester-ready product flow.
- Claimed robust search needs immediate hardening for temporal/query/filter correctness.
- Settings feature exists but is not fully wired to runtime behavior.
- Release operations (updater + CI packaging + docs) are not yet present.

This gameplan prioritizes closing those mismatches before broad beta distribution.

## 3) Beta Objectives and Exit Gates

Primary objective: ship a stable, tester-ready beta for Windows and macOS.

Exit gates:

- Crash-free session rate >= 99% in beta cohort.
- No open P0/P1 defects in indexing/search/playback path.
- End-to-end path works on CUDA, MPS, and CPU fallback.
- Faces and OCR are functional user-visible features (not placeholder/latent only).
- Updater + packaging path validated with repeatable artifacts.

## 4) Execution Plan (Starts at 5.0)

## Phase 5.0 - Beta Correctness Hardening (2-3 days)

Goal:
- Remove high-risk correctness and UX mismatches before adding features.

Status: Completed on February 8, 2026.

Deliverables:
- ~~Fix temporal query return-type bug in `core/search_engine.py`.~~
- ~~Align filterable match types with all emitted match types in `gui/search_tab.py`.~~
- ~~Implement or remove unsupported sort modes (`Duration`, `Date Added`).~~
- ~~Remove duplicate `reorder_operation` definition in `core/workflow_manager.py`.~~
- ~~Add a focused search/workflow smoke-check script.~~

Definition of done:
- ~~Temporal queries do not crash.~~
- ~~Filters can include all emitted result types.~~
- ~~Sort UI reflects implemented behavior only.~~
- ~~Workflow reorder behavior is deterministic.~~

Prompt for Claude Code:
"Stabilize beta-critical correctness issues. Read `core/search_engine.py`, `gui/search_tab.py`, and `core/workflow_manager.py`. Fix the temporal query return-shape bug, align filter options with emitted match types, and resolve unimplemented sort options (implement if metadata exists, otherwise remove). Remove duplicate reorder_operation definitions and keep one intended behavior. Add a small smoke-check script for query operators and temporal queries. If usage limits pause execution, end with a PAUSE HANDOFF: files changed, tasks done, tasks remaining, tests run, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste the PAUSE HANDOFF.
3. Resume with: `Resume exactly from this PAUSE HANDOFF. Do not redo completed work. Start with the listed next command and finish remaining tasks.`

Prompt for GPT-5.3-Codex:
"Audit Phase 5.0 changes for regressions. Review `core/search_engine.py`, `gui/search_tab.py`, `core/workflow_manager.py`, and the smoke-check script. Prioritize correctness in temporal handling, filter/sort behavior, and workflow queue semantics. If usage limits pause execution, end with a PAUSE HANDOFF: files reviewed, checks completed, open findings, and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste the PAUSE HANDOFF.
3. Resume with: `Resume review from this PAUSE HANDOFF. Continue unresolved checks first, then return remaining findings with file/line references.`

## Phase 5.1 - Settings Wiring and Runtime Truth (2-4 days)

Goal:
- Make completed settings feature behaviorally real across runtime paths.

Deliverables:
- Respect `auto_index_on_change` when starting watcher.
- Respect `generate_thumbnails` and `generate_proxies` in indexing.
- Wire `batch_size` and `keyframe_interval` to effective indexer behavior.
- Wire `device`, `model_quality`, and `whisper_model` into model/runtime selection.
- Apply `sidebar_default` and `accent_color` predictably.

Definition of done:
- Every active setting key in `core/settings_manager.py` is either fully wired or explicitly disabled with clear UX note.

Prompt for Claude Code:
"Wire settings to actual runtime behavior. Read `core/settings_manager.py`, `gui/settings_dialog.py`, `gui/main_window.py`, `workers/indexer.py`, `workers/transcriber.py`, and `core/ai_models.py`. Implement settings-driven behavior for watcher, thumbnail/proxy generation, batch/keyframe tuning, and model preferences while preserving backward compatibility with existing project settings. If usage limits pause execution, output PAUSE HANDOFF with completed wiring, pending wiring, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.1 from this PAUSE HANDOFF, continue pending wiring first, then run compile/smoke checks.`

Prompt for GPT-5.3-Codex:
"Review Phase 5.1 settings wiring for consistency, startup safety, and legacy-project compatibility. Validate that settings behavior matches UI expectations and does not introduce side effects. If usage limits pause execution, output PAUSE HANDOFF with verified areas, open risks, and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.1 review from this PAUSE HANDOFF and complete unresolved risk checks.`

## Phase 5.2 - Search UX Reliability for Testers (3-4 days)

Goal:
- Make search behavior stable, understandable, and repeatable during beta use.

Deliverables:
- Migrate search input to shared search component conventions.
- Stabilize pagination/filter/sort interaction state.
- Add explicit per-result availability state (`online/offline`) based on current path accessibility.
- Add search regression checklist for operators, semantic hits, transcript exact hits, YOLO hits.

Definition of done:
- Repeated multi-query sessions do not produce hidden/missing states or inconsistent controls.

Prompt for Claude Code:
"Harden search UX for beta reliability. Read `gui/search_tab.py`, `gui/widgets/search_bar.py`, and `core/search_engine.py`. Align search input with shared component conventions, stabilize pagination/filter/sort state transitions, and add explicit online/offline availability display based on path accessibility. Add a concise search regression script/checklist. If usage limits pause execution, output PAUSE HANDOFF with done/pending items and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.2 from this PAUSE HANDOFF. Complete pending search tasks and rerun regression checks.`

Prompt for GPT-5.3-Codex:
"Audit Phase 5.2 for event-order bugs and UI-state regressions. Focus on keyboard flow, pagination bounds, filtering interactions, and online/offline status handling. If usage limits pause execution, output PAUSE HANDOFF with validated checks, unresolved checks, and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.2 review from this PAUSE HANDOFF and finish unresolved interaction checks.`

## Phase 5.3 - Facial Recognition End-to-End (4-6 days)

Goal:
- Convert latent face infrastructure into a complete tester-visible feature.

Deliverables:
- Integrate face detection + embedding extraction in indexer pipeline.
- Persist `faces` metadata and appearance records (`FaceDB.add_appearance`).
- Replace Faces placeholder UI with enroll/rename/remove and appearance list.
- Wire person-name search and threshold controls.

Definition of done:
- A tester can enroll a face and retrieve appearances across library with timestamps.

Prompt for Claude Code:
"Implement face recognition end-to-end. Read `core/face_db.py`, `workers/indexer.py`, `core/search_engine.py`, and `gui/main_window.py`. Add indexing-time face detection/embedding, store searchable face metadata and appearance rows, and replace Faces placeholder page with functional management and appearance navigation. If usage limits pause execution, output PAUSE HANDOFF with completed tasks, pending tasks, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.3 from this PAUSE HANDOFF. Continue pending face-indexing/UI work and run smoke checks.`

Prompt for GPT-5.3-Codex:
"Audit Phase 5.3 face pipeline for false-positive controls, duplicate identity handling, DB consistency, and thread safety. Validate search/UI integration and threshold defaults across CUDA/MPS/CPU. If usage limits pause execution, output PAUSE HANDOFF with validated items, unresolved findings, and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.3 review from this PAUSE HANDOFF and finish unresolved defect checks.`

## Phase 5.4 - OCR + Offline Drive Search (4-6 days)

Goal:
- Deliver text detection and searchable offline-index behavior.

Deliverables:
- Add OCR extraction path in indexing pipeline.
- Store timecoded OCR text + confidence for ranking/context.
- Add `drive_id`, `relative_path`, and `online` metadata handling.
- Show clear offline-state treatment in search results.

Definition of done:
- Text-in-video queries work, and offline-indexed assets remain searchable with clear reconnect messaging.

Prompt for Claude Code:
"Implement OCR and offline-drive search behavior. Read `workers/indexer.py`, `core/database.py`, `core/search_engine.py`, and `gui/search_tab.py`. Add OCR extraction/storage/search ranking integration and add offline-drive metadata fields with online/offline result treatment. Include migration-safe handling for existing metadata. If usage limits pause execution, output PAUSE HANDOFF with schema changes, done/pending work, tests run, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.4 from this PAUSE HANDOFF. Complete pending OCR/offline-drive tasks and rerun migration/search checks.`

Prompt for GPT-5.3-Codex:
"Review Phase 5.4 for migration safety, ranking balance, and performance impact. Validate online/offline logic and fallback behavior for missing mounts. If usage limits pause execution, output PAUSE HANDOFF with unresolved checks and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.4 review from this PAUSE HANDOFF and finish unresolved migration/ranking checks.`

## Phase 5.5 - Collections + Tags Productization (4-6 days)

Goal:
- Replace remaining organizer placeholders with production behavior.

Deliverables:
- Add hierarchical virtual collections schema + operations.
- Implement collection tree and add/remove without moving source files.
- Replace Tags placeholder page with practical tag management workflows.
- Implement bulk tag apply/copy flows currently marked placeholder.

Definition of done:
- Testers can organize via virtual collections and bulk tag media without destructive file moves.

Prompt for Claude Code:
"Implement virtual collections and tags workflows. Read `core/database.py`, `gui/main_window.py`, `gui/media_tree.py`, `gui/metadata_panel.py`, and `gui/search_tab.py`. Replace placeholders with working collections/tags operations, preserving existing project compatibility. If usage limits pause execution, output PAUSE HANDOFF with completed work, pending work, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.5 from this PAUSE HANDOFF. Continue pending collections/tags tasks and run smoke validation.`

Prompt for GPT-5.3-Codex:
"Audit Phase 5.5 for edge cases: nested delete semantics, duplicate membership, bulk-tag correctness, and query performance impact. If usage limits pause execution, output PAUSE HANDOFF with unresolved checks and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.5 review from this PAUSE HANDOFF and complete unresolved edge-case checks.`

## Phase 5.6 - Updater + Version Governance (4-7 days)

Goal:
- Add safe update flow for external tester deployments.

Deliverables:
- Create `core/__version__.py` as single version source.
- Implement updater core + worker + dialog.
- Add startup update check + manual check action.
- Add checksum verification, timeout controls, and rollback path.

Definition of done:
- App can safely check/download/validate/apply updates with user-visible status and rollback safety.

Prompt for Claude Code:
"Implement updater and centralized versioning. Add `core/__version__.py`, `core/updater.py`, `core/update_worker.py`, and `gui/update_dialog.py`; wire startup and manual update checks in `main.py` and `gui/main_window.py`. Preserve project data and settings during updates. If usage limits pause execution, output PAUSE HANDOFF with completed pieces, pending pieces, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.6 from this PAUSE HANDOFF. Complete pending updater/version tasks and run safety checks.`

Prompt for GPT-5.3-Codex:
"Audit Phase 5.6 for security and failure behavior: version comparison correctness, trust boundaries, checksum enforcement, timeout behavior, and rollback integrity. If usage limits pause execution, output PAUSE HANDOFF with unresolved security checks and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.6 review from this PAUSE HANDOFF and finish unresolved security/failure checks.`

## Phase 5.7 - Packaging + CI Release Pipeline (4-8 days)

Goal:
- Produce repeatable beta artifacts for Windows and macOS.

Deliverables:
- Add build scripts under `build/windows/` and `build/macos/`.
- Add reproducible packaging config/spec.
- Add CI workflows under `.github/workflows/` for multi-OS builds.
- Publish updater-compatible release metadata.
- Add `README.md` with tester install/run/update guidance.

Definition of done:
- One workflow run can produce usable beta artifacts for both target OSes.

Prompt for Claude Code:
"Implement packaging and CI release pipeline. Add build scripts and workflow files, and create `README.md` for tester onboarding (install/run/update). Keep heavy AI models as first-run downloads, not bundled. If usage limits pause execution, output PAUSE HANDOFF with completed pipeline work, pending work, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.7 from this PAUSE HANDOFF. Complete pending packaging/CI/docs tasks and validate workflow syntax.`

Prompt for GPT-5.3-Codex:
"Review Phase 5.7 for determinism, reproducibility, diagnostics, and updater artifact compatibility. Focus on PyQt6/torch packaging pitfalls and CI failure clarity. If usage limits pause execution, output PAUSE HANDOFF with unresolved checks and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.7 review from this PAUSE HANDOFF and close unresolved packaging/CI checks.`

## Phase 5.8 - Beta Operations + Go/No-Go (1-2 weeks)

Goal:
- Run controlled beta with measurable decision criteria.

Deliverables:
- Beta test matrix (CUDA/MPS/CPU x media classes x library sizes).
- Bug report template + severity/risk rubric.
- Weekly beta release checklist.
- Benchmark protocol for precision/latency regression tracking.
- Exit report template with go/no-go criteria.

Definition of done:
- Release decision is evidence-based against pre-defined gates.

Prompt for Claude Code:
"Create beta operations artifacts under `docs/beta/`: test matrix, bug template, release checklist, benchmark protocol, and exit-report template. Keep artifacts lightweight and operational for a small team. If usage limits pause execution, output PAUSE HANDOFF with completed docs, pending docs, and exact next command." 

If Claude Code pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.8 from this PAUSE HANDOFF. Complete pending beta-ops artifacts and verify cross-links.`

Prompt for GPT-5.3-Codex:
"Review Phase 5.8 artifacts for missing gates, weak metrics, and cross-platform blind spots. Strengthen severity criteria and rollback triggers. If usage limits pause execution, output PAUSE HANDOFF with unresolved review tasks and exact next command." 

If GPT-5.3-Codex pauses due usage limits:
1. Start a new session in the same repo.
2. Paste PAUSE HANDOFF.
3. Resume with: `Resume Phase 5.8 review from this PAUSE HANDOFF and finish unresolved gate/metric checks.`

## 5) Strict Execution Order

1. Phase 5.0 - Beta correctness hardening
2. Phase 5.1 - Settings wiring
3. Phase 5.2 - Search UX reliability
4. Phase 5.3 - Face recognition end-to-end
5. Phase 5.4 - OCR + offline-drive search
6. Phase 5.5 - Collections + tags productization
7. Phase 5.6 - Updater + version governance
8. Phase 5.7 - Packaging + CI release pipeline
9. Phase 5.8 - Beta operations + go/no-go

## 6) Checkpoint Commit Naming

- `phase-5.0-beta-correctness`
- `phase-5.1-settings-wiring`
- `phase-5.2-search-ux-hardening`
- `phase-5.3-face-e2e`
- `phase-5.4-ocr-offline-drive`
- `phase-5.5-collections-tags`
- `phase-5.6-updater-versioning`
- `phase-5.7-packaging-ci`
- `phase-5.8-beta-ops`
