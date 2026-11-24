# Model reassessment for the confirmed editor product

Research checked 24 November 2026. **Publisher-documentation review, not a new
local performance benchmark or a model migration.**

## Product decisions this review serves

Questions 1–6 are confirmed: solo editors/small teams; footage-grounded story
development; equal wedding/fiction/documentary/commercial/social launch support;
desktop companion with file-based Premiere handoff; complete application redesign
before workflow completion; first value is an evidence-linked footage brief/paper edit.

The model stack should produce useful, traceable observations across those genres.
A generic image caption or fluent summary is not sufficient evidence of that.
The latest clarification narrows launch speech to **English, including Indian
English accents**; Hindi and multilingual/code-switching/translation requirements
are deferred. The inline answers confirm timed visual observations, editable speakers, progressive
analysis, both in-app AI and portable packs, and optional project-setup cloud
analysis. Hardware tiers target mainstream Apple Silicon/Windows editing PCs.
Exact minimums/provider/input/cost details still require design. All 36 questions
are answered; 27B confirms a search-first home screen. See the [product brief](product-brief.md).

## Conclusion

The installed stack is **not the latest overall** and should not be assumed to
be the best fit for the confirmed product. Keep it as a reproducible baseline.
Prioritize research/benchmarks for video understanding, retrieval and speech
quality. Select a winner by editorial usefulness and measured desktop behavior,
not release date or publisher leaderboard alone.

## Installed versus candidates

| Job | Current code/cache | Reassessment and candidate set |
|---|---|---|
| Describe visual events | BLIP-large tested; BLIP-2 optional/uninstalled | Highest-priority replacement benchmark. Compare compact **Gemma 4 E2B/E4B**, a **Gemma 4 12B** quality tier and **Qwen3.5-4B** against the baseline. They provide contemporary multimodal/video-capable paths; application sampling/coverage still needs its own design. [Gemma releases](https://gemma.ai/models/releases/), [video guide](https://gemma.ai/get-started/capabilities/video/), [Qwen model](https://huggingface.co/Qwen/Qwen3.5-4B) |
| Search images/dialogue | CLIP ViT-L/14 for images and accuracy-mode transcript vectors | Test **EmbeddingGemma 2** for shared retrieval across text/image/video/audio. Compare a separate text path such as **Qwen3-Embedding-0.6B**, with **SigLIP 2** as a visual-retrieval comparator. These are candidates, not installed replacements. [EmbeddingGemma 2](https://gemma.ai/models/embeddinggemma/model-card-v2/), [Qwen text model](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B), [SigLIP 2](https://huggingface.co/google/siglip2-so400m-patch14-384) |
| Transcribe speech | Whisper small tested; large-v3 is the app's accuracy/default registry choice | Keep small as a baseline/fast candidate. Compare **large-v3**, **large-v3-turbo** and **Qwen3-ASR-0.6B/1.7B** on actual languages, noise, singing/music and timing. Turbo is not a speech-translation replacement. [Whisper](https://github.com/openai/whisper#available-models-and-languages), [Qwen ASR](https://huggingface.co/Qwen/Qwen3-ASR-1.7B) |
| Attribute speaker turns | No complete implemented diarization workflow | For the confirmed editable speaker workflow, test the official **pyannote speaker-diarization-community-1** pipeline. It separates speaker turns; it does not automatically establish names or relationships. [Official model](https://huggingface.co/pyannote/speaker-diarization-community-1), [publisher description](https://www.pyannote.ai/blog/community-1) |
| Detect object boxes | YOLOv8m tested | **YOLO26** is the newer released Ultralytics generation documented for January 2026. Benchmark it only if boxes/tracking add editor value. Detector-class coverage and open-ended editorial description are different requirements. [YOLO26](https://docs.ultralytics.com/models/yolo26/) |
| Write short summaries | Optional Llama-3.2 3B/Phi-3 paths; no weights tested here | Do not treat the old optional choices as the default future writing architecture. A modern multimodal candidate may also generate structured text, but the first value requires source evidence and usable export. Question 20C now requires both in-app chat and external-AI packs; evaluate shared evidence quality and optional cloud providers alongside local writing candidates. |

## What “latest” means here

Google's release log lists Gemma 4's initial models on **31 March 2026**, the
12B Unified model on **3 June 2026**, and **EmbeddingGemma 2 on 6 October 2026**.
These are materially newer families than the current caption/retrieval stack.
[Official release log](https://gemma.ai/models/releases/)

EmbeddingGemma 2's publisher describes a 740M-parameter model with shared
768-dimensional text/image/video/audio embeddings and multilingual support. That
makes it an unusually relevant candidate for this product, not proof that it wins
our dialogue or footage queries. [Model card](https://gemma.ai/models/embeddinggemma/model-card-v2/)

Qwen's current homepage also announces **Qwen4-Max, 16 November 2026**, at a vastly
different 2.4-trillion-parameter scale. That is not a sensible direct local download
for this desktop app. Our compact Qwen3.5 candidate is chosen for practical
evaluation, not because it is the newest Qwen flagship. [Publisher](https://qwen.ai/)

## Important speech qualifications

- Qwen3-ASR supports **30 languages plus 22 Chinese dialects**, rather than 52
  distinct languages. Its timestamp path may use a separate forced aligner with
  **11-language** support. Check language support for recognition and alignment
  independently before promising useful edit points. [ASR/aligner documentation](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- **Scope refinement:** Hindi is now deferred. Qwen3-ASR recognition and forced
  alignment language lists still need separate checks if multilingual scope returns.
- NVIDIA **Parakeet-TDT-0.6B-v3** can return to the English speech benchmark
  shortlist. The earlier Hindi-based exclusion no longer applies; measure Indian
  English accent accuracy, timing and Mac/Windows runtime feasibility before
  choosing it. No model migration follows from the scope change. [Official model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Transcription, word alignment, translation and speaker diarization are separate
  capabilities. Evaluate them independently, then verify the combined source
  timing and speaker/quote record. A diarized transcript is not verified identity.

## Mac and PC feasibility

Google documents native Apple Silicon inference through MLX, including community
conversions for Gemma 4. That is a promising Mac benchmark route; it is not proof
that our app already supports it or that every conversion has identical quality.
Windows needs its own validated runtime/backend. [MLX guide](https://gemma.ai/deployment/mlx/)

Memory depends on quantization, context, frame count, runtime and concurrent
models. Published static-weight memory tables exclude significant context/runtime
costs. Do not size the product only for this 48 GiB M4 Pro or promise that a large
context fits just because quantized weights fit. [Memory planning](https://gemma.ai/models/gemma-4/)

The working app pins Transformers below 5 in `constraints-macos.txt`; Google's
current video example asks for Transformers **5.10.1 or newer**. Benchmark in a
separate environment/cache budget, or assess an alternative runtime. A blanket
upgrade of the working environment is not part of this review.
[Video dependencies](https://gemma.ai/get-started/capabilities/video/)

Different embedding models define different spaces even when both output 768
numbers. Future integration needs separate/versioned indexes and a controlled
transition; existing CLIP vectors cannot simply be mixed with a new encoder.

## How we will decide “best for CyneDirector”

Use the confirmed outputs and complete redesign to prepare a small matched
benchmark. Start with the user’s own available projects (36B), and record which
of the **five launch genres** actually have evidence. Kanishkar’s wedding is one
intended dataset; missing genres need appropriate samples before equal-support
claims. Benchmark English speech, including Indian English accents, explicitly;
Hindi/code-switching/translation are deferred acceptance requirements.

| Editorial task | What to measure |
|---|---|
| Explain a scene/take/event | Correct actions, subjects, ordering and important visual moments; unsupported claims and omissions |
| Use dialogue in a paper edit | Word/name accuracy, exact preservation of recognized/reviewed quotes, language switches, attribution and source timing |
| Find a moment by meaning | Useful reviewed hits, time to inspect the source and retrieval across the selected languages |
| Build a footage brief | Completeness/visibility of coverage, reliable references, correction effort and whether the resulting paper edit is useful |
| Run on desktop | Cold/warm time, throughput, peak memory, disk growth, cancellation, long-source bounds and Mac/PC behavior |

Examples across genres include event coverage (wedding), scene/take/script
relationships (fiction), speaker/theme evidence (documentary), brief/product/message
coverage (commercial), and hooks/formats (social). These are benchmark design
prompts, not an already approved feature list.

Use the same clips and prompts, editor-checked references and blinded output
review where possible. Publisher benchmarks are supporting evidence; they do not
establish a measured win on our footage. Long context is not a coverage guarantee.
Changing models alone will not fix sparse sampling or the app's bounded summary
input; the evidence/coverage design must address those explicitly.

No new model was downloaded, installed or benchmarked during this review. No
working dependency, original footage or user project was changed. The shortlist
is ready for use in the redesign/benchmark plan; it is not a final model selection.
