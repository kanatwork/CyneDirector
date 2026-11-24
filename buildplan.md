# CyneDirector — editor product and build plan

Updated 24 November 2026 (Asia/Kolkata). **All 36 product questions answered;
27B confirms a search-first home screen with recent results.** Use inline chat, never popup forms.

This replaces the [previous engineering task order](docs/archive/buildplan-before-product-discovery-2026-11-24.md).
Existing implementation and verification remain evidence, not the product vision.
Read the [product brief](docs/product-brief.md) and [decision record](docs/product-decisions.json).

## Confirmed direction

- Serve solo editors and small teams making story-led films. Understand raw footage
  and develop an evidence-grounded story; fast retrieval of a shot/performance/line
  is the immediate pain. The first valuable result is a useful footage brief/paper edit.
- Support weddings, fiction, documentaries, commercials and social content equally
  at launch. The approximately 800 GB wedding is one intended project, not the
  product's genre boundary. Validate on Kanishkar's own available projects first.
- Target Apple Silicon Macs and mainstream Windows editing PCs, with analysis tiers
  and NVIDIA-first Windows GPU acceleration. Intel Macs are excluded. Define and
  validate supported OS/hardware baselines; do not assume every existing path works.
- A desktop companion with reliable file-based Premiere handoff. Suggest source
  matches for review; Premiere handles editing synchronization. Resolve follows.
- **Redesign the whole application before completing a new workflow.** This does
  not authorize an automatic framework/backend rewrite or model migration.
- Both **in-app AI chat and portable external-AI context packs** are launch scope.
  Optional cloud analysis is offered during project setup; provider/input/cost
  details remain to be designed. This is not permission to upload footage now.
- English speech, including Indian English accents, is launch scope. Hindi,
  multilingual/code-switching and translation requirements are deferred. Preserve
  original transcripts, existing translations and multilingual capabilities/data.
- Add a [GitHub release updater](docs/release-updater.md) to installed-app delivery.
- Preserve originals, existing projects, corrections and verified safety behavior.
  Infrastructure/model changes must serve a named editor outcome or real failure.
- **Phone use means Codex supervising development.** CyneDirector mobile UI,
  phone job control/previews and a remote product API are outside scope. See
  [the clarification](docs/phone-control.md).

## Confirmed journey and scope

After offload/backup: create the project/creative brief and add media, separate
production audio and context documents. Receive quick source-wide coverage,
then deeper useful/overnight analysis. Browse editable virtual groups or search
for a moment; inspect it with a synchronized player, filmstrip and transcript.
Correct labels, mark ranges with keyboard/text selection, favorite/reject and note.
Develop a paper edit in-app or with a portable context pack, then export reviewed
markers/selects to Premiere. Support a primary film and its related versions.

The knowledge hierarchy is project → scenes/events/topics → clips → moments.
Timed visual observations, dialogue/speakers, notable sound and technical flags
support review. A roster/context guide and optional reference images help reviewed
identity suggestions. Technical flags never automatically discard material.

The whole design must cover setup, find/review, story, deliverables and operational
states. The confirmed default home screen emphasizes a prominent search box and
recent results (27B), with project coverage available elsewhere in the design.

## D0 — Consolidate the product decisions

The [discovery record](docs/product-discovery.md) records all explicit answers.
All 36 are settled, including 27B and the subsequent English-only clarification.
Do not reinterpret recommendation letters using the superseded questionnaire
or restart discovery batches. Any further design questions belong inline.

The [brief](docs/product-brief.md) now establishes the promise, confirmed scope,
editor journey, trust rules, platforms and release/updater requirement. Separate
remaining design details from the completed questionnaire: providers, exact formats,
interaction details and hardware thresholds still need specification. The default
home screen is settled; proceed with complete application design.

## D1 — Establish the editor sample and outcomes

Start with Kanishkar's own available projects, as chosen in 36B. Record actual
coverage across all five launch genres; a wedding alone cannot establish equal
genre usability. Document logging/search/story decisions, existing Premiere habits,
workarounds and time spent. Supplement missing genres with clearly labeled scenarios
until real project evidence exists; do not claim those scenarios are validation.

Choose a bounded sample with backups and measured workspace headroom. Include
long clips, English speech including Indian English accents, dialogue/B-roll,
weak audio, duplicate basenames, multiple cameras and actual source formats. The
real SSD/full library is not accepted yet. About 8.2 GiB was free internally at the
last pipeline verification; the default 20 GiB reserve correctly blocked that
filesystem then. Re-measure before running; do not start 800 GB to discover setup problems.

Measure time/success finding and reviewing a known shot/line, correction effort,
source-citation accuracy and whether a paper edit is useful. Establish baselines
and pass thresholds before comparing models or claiming editor time saved.

## D2 — Redesign the whole application

This precedes completing a new workflow, as explicitly chosen in 5C. Produce:

1. Complete information architecture and entities, including project/creative brief,
   virtual organization, source moments, corrections and related film versions.
2. A desktop visual system, reusable controls, keyboard and accessibility behavior.
3. Connected core screens for setup/cloud choice, progressive coverage, search,
   synchronized review/selects, in-app AI, paper edit, context export and Premiere handoff.
4. Secondary job/storage/model/provider settings and update/restart interactions.
5. Empty, partial, uncertain, processing, offline, error, recovery and version states.
6. Connected prototypes with tasks from all five genres, reviewed first on the
   user's own projects. Record evidence and gaps; do not assume a recruited beta cohort.

A proposed organization is Project/Brief, Find & Review, Story, Deliver, plus
secondary operations/settings. These are design proposals, not final navigation
or a replacement for the confirmed search-first home screen. Review the complete design before choosing the
implementation sequence. Preserve the safety contract regardless of UI framework.

## D3 — Define shared evidence for in-app AI and context export

Both interfaces are confirmed launch requirements. Specify one evidence contract:

- Every source accounted for, with offline/failed/skipped/unanalysed spans. Coverage
  is visible; a summary is never represented as exhaustive understanding.
- Stable portable asset/range references, source timebase, original transcript,
  any existing translation kept separately, editable speakers and timed visual records.
- Separate observations, quotations, interpretations, proposed narration, unknowns
  and review/correction state. Never invent relationships or real spoken lines.
- Readable brief plus structured records/transcripts and optional labeled contact
  sheets. Include the creative brief, coverage/method versions and editor corrections.
- Project/scene/event/topic/clip/moment hierarchy, chunking/indexing and versioned
  changes. Account for chatbot context/file limits rather than one giant dump.
- A paper edit with quotes, source ranges and visual coverage. Both chat and exported
  packs retain inspectable evidence. Design cloud data scope and cost controls.

Current sparse BLIP frame captions and 4,096-character summary inputs do not meet
this contract. Full bounded transcripts and source metadata exist separately;
rich visual coverage, speaker review and complete AI/export workflows remain to
build. See [models](docs/models.md) and the [candidate evaluation](docs/model-evaluation-2026-11-24.md).

Benchmark the existing stack against practical video/retrieval/speech candidates
using these outputs. English recognition, Indian English accent robustness,
source alignment and diarization need separate checks. Hindi, code switching and
translation are deferred launch requirements. No model wins by release date.
Use an isolated environment for incompatible dependencies; preserve existing indexes.

## D4 — Implement the designed experience in slices

After reviewing the complete design and sample tasks, select implementation slices
that support the whole journey. Likely dependencies include coverage-aware records,
fast source review, correction/select persistence, retrieval, shared AI context and
paper-edit evidence. Keep design scope broad and implementation reviewable.

Premiere handoff is confirmed **file-based reviewed markers/selects**, not a plugin
or autonomous finished edit. Specify/test actual interchange with original source
frames/timebases, audio and relinking. Preserve portable records for Resolve later.

Interactive model ownership, FFmpeg child cancellation, independent stage versions
and durable watcher/translation routing remain engineering backlog. Advance them
when required by the designed flow or a demonstrated correctness/safety failure.

## D5 — Package, update and validate desktop releases

Build installable Apple Silicon Mac and declared Windows artifacts. Include the
[accepted updater](docs/release-updater.md): published stable GitHub Releases,
compatible assets, notes, safe download/restart, data preservation and recovery.
Keep app installation separate from media, projects, jobs/settings and model caches.
Do not silently replace model indexes or trigger full-library reprocessing.

Validate upgrading an installed older build on both platforms, including unavailable
network, incompatible assets, failed verification, interrupted installation, space,
active work and schema recovery. A source checkout/version notification is not an
installed update test. Packaging/framework choices precede updater implementation.

Initial acceptance is on the user's own available projects (36B). Check usefulness,
source accuracy, correction effort, responsiveness, offline recovery, installation
and Premiere handoff. Broader beta/public rollout is not implied. Physical SSD,
power-loss, full-library and model-quality gates remain necessary wherever claimed.

## Evidence and readiness

The latest technical milestone has **201 passing regressions**, native Cocoa
startup/jobs/configuration GUI checks and cached-model processing after a simulated
root relink. These establish engineering behavior, not editor usefulness.

- [Publication checkpoint and fresh verification](docs/audits/2026-11-24-publication.md)
- [Latest technical audit](docs/audits/2026-11-24-workspace-relinking.md)
- [Workspace/jobs](docs/workspace-jobs.md) · [Relinking](docs/workspace-relinking.md)
- [Memory/retention](docs/memory-retention.md) · [Model refresher](docs/models.md)
- [PRD/backlog inventory](PRD.md) · [Implementation map](CLAUDE.md)

The old **67/100** is historical: its rubric included phone operation the user did
not require. Define a revised rubric around retrieval/review, grounded story value,
editor UX, handoff, reliability and desktop delivery. Agree thresholds and collect
evidence before rescoring; questionnaire answers alone do not raise app readiness.

## Next working instruction

Use the [complete redesign handoff](docs/redesign-handoff.md) as the execution
brief for the next task. It defines the required design/prototype artifacts,
decision traceability, evidence-pack examples, model evaluation, updater planning
and verification criteria without authorizing a production rewrite.

```text
Read docs/redesign-handoff.md and its authoritative product references. Complete
the whole-app design, connected prototype and validation artifacts specified there.
Honor all 36 answers, the English-only clarification and updater requirement.
Preserve the current local checkout, originals, existing data and verified safety
behavior. Ask essential questions inline. Review the complete design before
production workflow implementation or any model/framework migration.
```
