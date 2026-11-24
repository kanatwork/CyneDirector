# Current models — editor-oriented refresher

For the latest candidate assessment against the confirmed five-genre product,
read the [24 November 2026 reassessment](model-evaluation-2026-11-24.md). The table
below records the existing working baseline; it is not the proposed future stack.

Checked against the local code, cache directories and existing inference evidence
on 24 November 2026. This describes what is wired today, not a claim that these
are the best current models for the future product.

## What is installed and has run on this Mac

| Model | Editorial job | Current use and practical limit |
|---|---|---|
| [CLIP ViT-L/14](https://huggingface.co/openai/clip-vit-large-patch14) | Match a phrase to visually similar frames; compare frames with tag phrases | `openai/clip-vit-large-patch14`. Cached and tested on MPS. Produces vectors, not captions or a story. The app also uses its text encoder for dialogue vectors in accuracy mode; multilingual/long-dialogue retrieval needs a separate quality benchmark. |
| [BLIP-large](https://huggingface.co/Salesforce/blip-image-captioning-large) | Turn a sampled image into a short caption | `Salesforce/blip-image-captioning-large`. Cached/tested on MPS and selected by default. Current worker captions at most a few retained scene images, with fallback samples; it does not watch and describe every action in a long video. |
| [YOLOv8m](https://docs.ultralytics.com/models/yolov8/) | Detect common objects and their positions | `yolov8m.pt`, cached/tested on MPS. The standard detector covers 80 COCO classes. Helpful for object evidence, not names, relationships, rituals, speaker identity or a story's meaning. |
| [Whisper small](https://github.com/openai/whisper), through [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Transcribe spoken words with timestamps | `Systran/faster-whisper-small` is cached/tested; current Mac path is CPU/int8. The app uses bounded audio windows and word timestamps. Recognition and join quality still need testing on actual wedding languages, music and overlapping voices. |

These models do different jobs. CLIP is useful for matching, BLIP for captions,
YOLO for object localization, and Whisper for speech. None combines all the raw
video/audio into a complete editor-level understanding of a project.

Faster-whisper is an optimized implementation using CTranslate2, not a separate
story model. It also integrates [Silero VAD](https://github.com/SYSTRAN/faster-whisper#vad-filter)
to filter likely non-speech. Speech detection is not speaker diarization or naming.

## Alternatives and optional paths in the code

- **Whisper base / medium / large-v3:** selectable accuracy-mode choices. The
  source default and download registry still request large-v3, while the tested
  Mac configuration explicitly uses small. Other sizes are not cached/tested in
  this checkout. Model size involves speed/accuracy/language tradeoffs, so measure
  the actual footage rather than assuming larger always produces a better edit.
  [Whisper model/language documentation](https://github.com/openai/whisper#available-models-and-languages)
- **BLIP-2 OPT-2.7B:** `Salesforce/blip2-opt-2.7b`, an optional heavier image/text
  alternative supporting image captioning and visual question answering. It is
  not downloaded/tested here; there is no measured advantage on this wedding.
  It is still an image-based path, not a complete temporal video analysis pipeline.
  [Model documentation](https://huggingface.co/Salesforce/blip2-opt-2.7b)
- **Local text summarizer:** the loader tries
  `unsloth/Llama-3.2-3B-Instruct-bnb-4bit`, then
  `microsoft/Phi-3-mini-4k-instruct`. These are text-generation paths: they receive
  captions/transcript text, not raw footage. Neither is cached/tested here. When
  unavailable, the application uses template summaries. The Llama quantized path
  is CUDA-oriented; Mac support is not established by its presence in the code.
  [Llama family documentation](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct),
  [Phi model documentation](https://huggingface.co/microsoft/Phi-3-mini-4k-instruct)
- **Face support:** dlib/face-recognition libraries are installed and `FaceDB`
  stores encodings, labels and appearances. The current indexing/person-search
  experience is incomplete; this is not a verified workflow for finding the bride,
  a parent or a named guest. A label/encoding store is not automatic identification.
- **DeepL:** optional cloud translation service for transcript text, not a local
  vision model. It is an implementation option, not a configured/tested service
  in this Mac verification. Original-language dialogue must remain separate from
  translations. Long legacy Whisper translation is explicitly limited today.

On NVIDIA Windows, code paths use CUDA and choose different speech defaults from
this Mac. A fresh Windows run and a declared hardware matrix are still needed.
Intel Macs are excluded from the product target. Apple Silicon support does not
imply every optional model has been validated on every Apple machine.

## Why current summaries cannot become the complete AI context export

The visual worker retains/captions only a few scene images. Its CLIP sampling
records can extend further, but matching vectors are not human-readable accounts
of everything that happened. A still caption can miss a brief gesture or the
sequence of actions that makes a shot editorially important.

The transcription worker preserves its bounded full transcript separately, but
feeds at most the first **4,096 characters** to summary generation. Existing clip
summaries therefore are not a complete representation of dialogue either.
There is no finished speaker diarization, sound-event or reviewed story-entity
pipeline, nor a completed AI context-pack export.

The proposed pack needs explicit source/analysis coverage, original evidence and
reviewable corrections. A plausible paragraph must never stand in for missing
analysis. An external AI cannot recover footage context that the package omitted.

## Model decisions after product discovery

Benchmark capabilities against editor tasks, then choose an implementation:

1. English speech (including Indian English accents), word timing and speaker labels.
   Hindi, multilingual/code-switching and translation are deferred launch requirements;
   preserve existing multilingual data/capabilities.
2. Visual action/shot coverage, including motion and short important events.
3. Dialogue retrieval independently of image/text matching.
4. Exact quote/source references and uncertainty in exported context.
5. Runtime, memory, storage and correction effort on Apple Silicon and Windows.

Possible capability gaps may justify video-aware vision analysis, dedicated text
embeddings or diarization. These are hypotheses to evaluate, not selected model
replacements. Reuse existing models wherever they meet the accepted quality bar.

Implementation references: [AI loaders](../core/ai_models.py),
[visual worker](../workers/indexer.py), [speech worker](../workers/transcriber.py),
[summary code](../core/summary_generator.py), [registry](../core/model_manager.py).
The [Mac verification](audits/2026-11-24-macos-runtime.md) and
[relinking verification](audits/2026-11-24-workspace-relinking.md) record actual runs.
