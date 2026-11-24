# CyneDirector

Local AI video indexing and semantic search, implemented as a Python/PyQt6
desktop app. Current source version: **2.1.0**.

Restored from [kanatwork/CyneDirector](https://github.com/kanatwork/CyneDirector)
and updated to upstream `efd093023c2b30410a5f11553b251e94f69e9f88` on 24 November 2026.
The product is being refocused around working editors on **Apple Silicon Macs
and Windows PCs**. Confirmed launch scope covers weddings, fiction, documentaries,
commercials and social equally; the next design milestone is a full app redesign.
Premiere handoff is file-based; the first value is a brief/paper edit grounded in
source evidence. The approximately 800 GB wedding is one intended project. Phone use
means **Codex supervising development**; CyneDirector mobile UI is outside scope.
All 36 product questions are answered. The home screen emphasizes search and recent
results; launch speech scope is English, including Indian English accents.
The next milestone is the complete redesign, including both in-app AI and portable
context packs, optional cloud setup and a GitHub release updater. These are planned
requirements, not claims of implemented features. Use inline questions, not popups.

- [Current product-discovery and build plan](buildplan.md)
- [Confirmed product brief](docs/product-brief.md) · [36 confirmed answers](docs/product-discovery.md)
- [Accepted release-updater requirement](docs/release-updater.md)
- [Current model refresher](docs/models.md) · [Fresh model reassessment](docs/model-evaluation-2026-11-24.md)
- [Publication checkpoint and fresh verification](docs/audits/2026-11-24-publication.md)
- [Latest technical SSD relinking audit](docs/audits/2026-11-24-workspace-relinking.md)
- [Safe SSD relinking and workspace updates](docs/workspace-relinking.md)
- [Long-clip limits and safe generation retention](docs/memory-retention.md)
- [SSD workspace and durable-job guide](docs/workspace-jobs.md)
- [Tested Mac environment](docs/audits/2026-11-24-macos-runtime.md)
- [Safe reprocessing and scene-timing verification](docs/audits/2026-11-24-safe-reprocessing.md)
- [Codex-from-phone scope clarification](docs/phone-control.md)
- [Product requirements](PRD.md) · [Implementation map](CLAUDE.md)

## Launch on this Mac

The full dependency environment is installed in `.venv`. Double-click
**[run.command](run.command)** in Finder, or run:

```bash
./run.command
```

Native welcome/model dialogs and the main window passed startup testing on the
Apple M4 Pro, macOS 27.2.1. Visual inference uses the Apple GPU (MPS); the current
Whisper path uses CPU/int8. The layout now fits the laptop display.

CLIP ViT-L/14, BLIP-large, YOLOv8m, and Whisper **small** are downloaded and tested.
In a new project's **Settings → AI / Models**, select Whisper `small` to use the
tested speech model. The first-run model dialog still lists `large-v3` as required;
use **Skip for Now** for that additional download. The default accuracy setting otherwise
requests large-v3. BLIP-2 and LLM summary weights were not downloaded or tested.

## Configure storage and durable processing

Open **File → Workspace & Jobs…**. Register original-media folders and choose
separate existing project/output/model-cache folders. The default reserve is
**20 GiB per destination filesystem**; shared-volume estimates are added together.
The internal volume currently has only about **8.2 GiB free**, so that default
correctly blocks processing until storage/headroom is arranged.

Once configured, the normal visual/speech workflow saves the whole selected scope
as a durable job before starting. The jobs view also submits metadata inventory,
shows persistent progress, and offers pause/resume/cancel/retry. Closing the dialog
keeps work running; quitting the GUI pauses after the current stage. Existing
project data/artifacts remain in place; new derivatives use the selected workspace.

The same engine is available through `./cyne.command --project /path/to/project`
with JSON `preflight`, `submit`, `start`, `run`, `status`, `events`, `list`, `pause`,
`resume`, `cancel`, and `retry-failed`. Inventory is a submitted stage. Detached
runs survive their launcher exiting; completed file/stages checkpoint durably.
See the [guide](docs/workspace-jobs.md) for exact commands and GUI/CLI ownership,
configuration updates, cached-model and recovery limits. Premiere interchange remains unverified; Codex phone access is a separate
development-environment task.

## Reproduce the Apple Silicon environment

With Homebrew installed, run:

```bash
./setup_macos.sh
```

This installs Python 3.11, FFmpeg/FFprobe, and CMake through Homebrew, creates
`.venv`, installs [requirements-macos.lock](requirements-macos.lock), and runs
`pip check`. The tested set uses Python 3.11.18, Qt 6.8.2/PyQt 6.8.1, torch 2.11.0,
and Chroma 0.4.24. The script passed an in-place repeat; a clean second-Mac install
and packaged/notarized app remain unverified. It targets native arm64, not Rosetta.
Windows retains `setup.bat`/`run.bat`; its current build has not been re-tested here.

The launcher sets FFmpeg's PATH and keeps Hugging Face/Torch/configuration caches
under `.cache` without editing the global shell. YOLO's weight is currently
`yolov8m.pt` in the repository root. Models and `.venv` are ignored by Git.
To choose a different cache destination before setup/launch:

```bash
CYNE_CACHE_DIR="/Volumes/YOUR_WORKSPACE/CyneDirector-cache" ./run.command
```

That override does not move existing downloads, relocate YOLO weights, or select
project/proxy output paths. Existing user cache overrides may also take precedence.
About **8.2 GiB** remains free internally at this verification (`.venv` ≈1.9 GiB; `.cache`
≈3.8 GiB). Choose a workspace with measured output headroom before the wedding
pilot. Originals were not accessed or modified; the wedding SSD was not mounted.

## Verification

Run suites in separate processes because search tests install import stubs:

```bash
source scripts/macos_env.sh  # bash
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

All **201 regression checks**, native Cocoa startup, Qt/SQLite/Chroma/FFmpeg
integration and actual cached-model CLI processing passed. New checks cover process
kill/restart, publication/ledger reconciliation, cancellation, offline/replaced
roots, capacity, aliases, deduplication and legacy-data preservation. The native
GUI queue check uses a small publication adapter; the CLI separately runs real
CLIP/BLIP/YOLO/Whisper on generated video/speech and validates original/project
hashes, preserved legacy data, workspace derivatives and repeat-run attempts.

Reports/screenshots live locally in `.cache/mac-verification` and
`.cache/durable-verification`; consolidated evidence is linked from the
[latest audit](docs/audits/2026-11-24-workspace-relinking.md). This is not a wedding
quality/throughput benchmark. No original wedding footage or user project was
opened; the wedding SSD was not mounted.

Long-clip buffers and windowed speech now have explicit limits; over-limit stages
preserve the prior generation. Retention offers dry-run inspection, verified
quarantine, restore and a separate delayed purge for tracked derivatives. Existing
untracked data stays protected. See the [contract and commands](docs/memory-retention.md).

SSD root relinking and destination/reserve updates now use verified preview/apply
plans in the GUI and CLI. Stored source keys, asset IDs, job payloads and existing
derivatives stay in place. Offline files survive project saves. See the
[relinking guide](docs/workspace-relinking.md).

Next: design the complete app around the
[confirmed brief](docs/product-brief.md). Start validation on the user’s own projects.
Preserve the engineering backlog and validated safety work; select implementation
slices after the complete design establishes their editor value. The old 67/100 is a
historical score under a withdrawn phone-inclusive rubric. No full 800 GB run has
started.
