# Mac environment and real inference — verification

24 November 2026, Asia/Kolkata. Local work on upstream `efd0930`, branch
`codex/wedding-workflow-plan`. Changes are uncommitted and have not been pushed.
This supersedes the **55/100** score in the
[safe-reprocessing report](2026-11-24-safe-reprocessing.md); its generation/timing
contract and remaining storage/recovery limits still apply.

Historical score snapshot. The subsequent [workspace/jobs verification](2026-11-24-workspace-jobs.md)
raises current readiness to **65/100** with implemented capacity checks and durable
local jobs. The environment evidence below remains historical validation.

## Result: 60/100

The app now launches natively on this Mac with the full Python dependency set,
working FFmpeg/FFprobe, and tested core AI models. It is a running prototype in
early beta hardening, ready for controlled sample testing after choosing storage.
The wedding/Premiere/phone workflow remains incomplete.

| Dimension | Before | Now | Evidence for change / remaining gate |
|---|---:|---:|---|
| Media integrity and recovery | 19/25 | 20/25 | Active background worker now stops/joins before model unloading; real Qt shutdown check passes. Durable jobs and storage retention remain open |
| Finding useful moments | 17/20 | 18/20 | Real visual and speech inference works locally. Wedding retrieval quality, languages and reviewed collections still need acceptance |
| Premiere workflow | 2/20 | 2/20 | No Premiere selects interchange or proxy certification yet |
| Phone operation | 4/15 | 4/15 | No actual pairing test or durable job commands yet |
| Setup and hardware compatibility | 6/10 | 8/10 | Native Mac startup, full dependency lock/scripts, FFmpeg/FFprobe, MPS vision and CPU speech verified. Other hardware/packaging pending |
| Validation and delivery | 7/10 | 8/10 | All 82 regressions plus native GUI, Qt/storage/FFmpeg and real inference checks pass. Real-media scale/release gates remain |
| **Total** | **55/100** | **60/100** | Same wedding workflow rubric; engineering judgment, not percentage of code complete |

Full credit requires the acceptance evidence in [buildplan.md](../../buildplan.md):
durable bounded processing and recovery, measured wedding search quality, tested
Premiere selects/relink/audio, actual phone job control, and reconciled full-library
processing on the declared hardware. Installing dependencies alone cannot close
those gates.

## Installed and reproducible locally

| Component | Tested environment |
|---|---|
| Hardware / OS | Apple M4 Pro, 48 GiB unified memory, arm64, macOS 27.2.1 |
| Python | Homebrew 3.11.18; repository `.venv` |
| GUI | PyQt6 6.8.1, Qt 6.8.2, native `cocoa` platform |
| Video tools | FFmpeg 9.1 and FFprobe 9.1 in `/opt/homebrew/bin` |
| Build prerequisite | CMake 4.5.1; dlib 20.0.1 compiled successfully |
| Vision | torch 2.11.0, torchvision 0.26.0, transformers 4.57.6, ultralytics 8.4.218 |
| Speech | faster-whisper 1.2.1, CTranslate2 4.9.1; small / CPU / int8 |
| Storage / decoding | Chroma 0.4.24, NumPy 1.26.4, OpenCV 4.11.0.86 |
| Face libraries | face-recognition 1.3.0, face_recognition_models 0.3.0; dlib HOG / CPU smoke |

All packages in `requirements.txt` are installed. Optional DeepL is not required
for local inference and was not installed/tested. The exact environment, including
transitive dependencies and setuptools, is in
[requirements-macos.lock](../../requirements-macos.lock). Bootstrap compatibility
bounds are in [constraints-macos.txt](../../constraints-macos.txt).
NumPy/OpenCV/Chroma and torch/torchvision are deliberately held to the tested set.
Setuptools stays below 81 because the face-model package uses `pkg_resources`;
its deprecation warning remains an upstream maintenance issue. Posthog 3.x avoids
the old Chroma telemetry API mismatch seen during the earlier isolated audit.

[setup_macos.sh](../../setup_macos.sh) installs Homebrew prerequisites and the lock
into `.venv`; an in-place repeat completed with exit 0 and `pip check` reported no
broken requirements. It targets native Apple Silicon. This is not evidence of a
clean second-machine installation or a distributable/notarized `.app`.

[run.command](../../run.command) is executable and can be double-clicked in Finder.
It selects the venv and sources [scripts/macos_env.sh](../../scripts/macos_env.sh)
to supply Homebrew PATH, local caches and MPS fallback without global shell edits.
The prior system Python 3.9 interpreter was not replaced.

## Startup and fixes found during testing

`tests.macos_startup_smoke` ran the actual `main.main()` entry point on a disposable
project. It rendered the welcome screen, first-run model dialog, and main window
using native Cocoa. Only dialog selection and closing were automated; additional
model downloads were skipped. No Qt exceptions were captured. The test redirects
recent-project configuration and disables automatic indexing for its own project.

The first native layout exceeded the laptop display. The metadata inspector and
search filters now scroll, and the initial window respects available screen size.
The final native startup check asserts that the window fits the display. The status
indicator now reports **Apple GPU (MPS)** using the selected backend; it previously
said CPU Only on this Mac. The high-DPI policy is applied before creating Qt.

`BackgroundIndexer.shutdown()` stops its timer, clears pending work, disconnects
the completion handler, and stops/joins the active worker before AI model unloading.
The integration check closes the window with an active real QThread and verifies
that both worker and timer have stopped. This fixes shutdown ownership; it does
not implement durable queues or fully coordinate concurrent foreground/background
model use.

Native Qt/MPS checks ran on the host outside the restricted tool sandbox. Inside
that sandbox Qt's CPU-feature check could not read the host feature flags and
aborted about NEON. Host checks confirmed arm64/NEON and passed. This distinction
does not affect launching the app normally from Finder/Terminal.

Local screenshots and raw runtime reports are retained in
`.cache/mac-verification/{welcome.png,models.png,main-window.png,startup.json,inference.json,environment.json}`.
The consolidated [evidence JSON](2026-11-24-macos-runtime-evidence.json) is retained
in this repository with package versions, outcomes, model revisions and source hashes.

## Real model inference

Each check uses the application's model loader, with actual weights and inference.
All five checks also passed in a second cached run with Hugging Face offline mode;
YOLO used its local weight file. This was not an OS-enforced network-isolation test.

| Model/check | Fixture and observed result | Device |
|---|---|---|
| CLIP ViT-L/14 | Synthetic red square; image vector 1×768, text vectors 2×768; full 13,182-tag bank. Red similarity 0.2537 > blue 0.2075 | Actual output `mps:0` |
| BLIP-large | Caption: “a photo of a red square with a white background” | Model `mps:0` |
| YOLOv8m | Packaged Ultralytics bus image; detected bus and four people | Model and result tensors `mps:0` |
| Whisper small | Mac `say` speech, converted by FFmpeg to 16 kHz mono; exact transcript “On our wedding day, I promise to stand by your side.”; segment 0.00–3.08 s | CPU / int8 |
| Face library | Blank 128×128 image returns no faces without import/native-library failure | dlib HOG / CPU |

These are capability checks, not wedding accuracy/throughput measurements. Cached
process timings include model loading and differ from first-run download/warmup.
They must not be extrapolated to 800 GB. The face check does not establish positive
face identification, embeddings, clustering, or indexing integration.

Only CLIP, BLIP-large, YOLOv8m and Whisper small weights were downloaded. Optional
BLIP-2, LLM summaries, large-v3, and DeepL translation remain untested. The current
Whisper implementation deliberately uses the verified CPU/int8 path on Mac;
CTranslate2's experimental MPS speech backend is not enabled.

The model registry/default accuracy setting still requests **large-v3**, even
though small is cached. Choose **Skip for Now** in the first-run download dialog
and select **Settings → AI / Models → Whisper Model → small** for the tested setup.
Speed mode also chooses small on this Mac. Model registry size estimates and
variant-aware cache status need improvement before unattended downloads.

## Regression and integration evidence

| Check | Result and scope |
|---|---|
| Search suite | 33 passed; dependency stubs, separate process |
| Review regressions | 21 passed; injected storage/settings failures |
| Safe reprocessing/timing | 28 passed, no skips; includes real Chroma persistence/reopen and generated/decoded uneven cuts |
| Runtime integration | Passed; real SQLite/Chroma, FFmpeg thumbnails/proxies with distinct same-basename sources, Qt index→transcribe handoff and active-worker shutdown; short AI worker doubles |
| Native startup | Passed; native Cocoa actual entry point, disposable project, automated dialogs/close |
| Cached inference repeat | Passed; all five real-model/library checks above |
| Environment | `pip check`, repeated setup script, Python compilation, shell syntax checks passed |
| Diff whitespace | Passed with `git -c core.whitespace=cr-at-eol diff --check`; existing background-indexer file retains CRLF |

Commands and exit codes are in the evidence JSON and reproduction instructions
are in [README.md](../../README.md). Injected disk-full/settings errors and
offscreen Qt animation warnings are expected test diagnostics, not inference or
native-startup failures.

## Media preservation, capacity and next work

No original wedding footage was read, moved, renamed, overwritten or transcoded.
No existing user project was opened. Test media/projects lived in temporary
directories; screenshots and small verification fixtures remain in the ignored
cache. `/Volumes` contained Macintosh HD and Recovery, with no wedding SSD mounted.

About **8.7 GiB** remained free internally after setup; `.venv` uses approximately
1.9 GiB and `.cache` approximately 3.8 GiB. The bounded inference check refuses
further model work below 5 GiB; this is not a processing capacity policy. The plan's
proposed 20 GiB processing reserve plus estimated outputs has not been implemented.

`CYNE_CACHE_DIR` lets the launcher select another Hugging Face/Torch/config cache.
It does not migrate existing downloads, move root-level YOLO weights, or relocate
project derivatives. A media-root/output-root abstraction and capacity checks are
still required to keep an originals SSD separate from generated data.

Next implement capacity preflight, durable jobs/checkpoints, and bounded memory;
design snapshot-safe generation retention and benchmark query/storage growth.
Then inventory the mounted SSD without modifying originals, establish backup and
workspace paths, and run a representative 10–20 GB wedding pilot. Validate actual
languages, codecs, VFR/timebase, search quality and resource use. Premiere selects
and phone job control follow their build-plan gates. No full 800 GB processing,
Premiere import, phone pairing, Windows execution, or release packaging was tested.
