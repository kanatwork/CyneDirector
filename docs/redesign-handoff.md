# CyneDirector — complete application redesign handoff

Prepared 24 November 2026. This is the execution brief for the next design task.
It consolidates the completed questionnaire and subsequent clarifications; it
does not introduce new launch features or authorize production implementation.

## Objective

Design a coherent, usable and appealing desktop companion that helps solo
editors and small teams find the right footage, understand their material and
develop an evidence-grounded story before handing reviewed selections to Premiere.
Produce the complete application design before implementing new production
workflows. Think through real editorial decisions, product priorities, interaction
design and technical feasibility together.

Work in the existing local checkout:
`/Users/kanishkar/Desktop/The Tools/CyneDirector`

Preserve all existing uncommitted changes. Keep design/prototype files separate
from production behavior. Preserve originals, user projects, settings, annotations,
jobs, caches, indexes and verified safety behavior. Do not commit, push or publish
as part of this design task.

## Read first and inspect the actual product

Read these files under the checkout, in order:

1. [Completed decisions](product-decisions.json).
2. [Product brief](product-brief.md) and [discovery record](product-discovery.md).
3. [Active build plan](../buildplan.md).
4. [Requirements/backlog](../PRD.md) and [implementation map](../CLAUDE.md).
5. [Model baseline](models.md) and [dated candidate research](model-evaluation-2026-11-24.md).
6. [Updater requirement](release-updater.md), [latest technical audit](audits/2026-11-24-workspace-relinking.md)
   and linked storage/jobs/recovery guides where relevant.

Apply any applicable repository instructions. Inspect the current UI and relevant
source before proposing what to reuse or change. Launch the current app only when
it can be inspected without changing user projects, triggering model downloads or
processing footage. If that is unavailable, document the limitation and continue
from source and existing verification evidence.

Explicit later user clarifications take precedence. The decision record and brief
define accepted scope; older architecture, archives and recommended options do
not override it. Distinguish existing, partial, planned and proposed behavior.

## Fixed product decisions

- All 36 questionnaire answers are complete. **27B means a prominent search box
  and recent results on the home screen.** Keep coverage and project context easy
  to reach while search/review receives the primary emphasis.
- Launch covers weddings, fiction, documentaries, commercials and social equally.
  Use a shared workflow with appropriate scene/event/take/topic concepts; do not
  silently narrow scope to weddings or design five disconnected products.
- Support Apple Silicon Macs and mainstream Windows editing PCs. Intel Macs are
  excluded. Specify hardware tiers and NVIDIA-first Windows GPU acceleration;
  leave unverified compatibility explicit.
- English, including Indian English accents, is the launch speech requirement.
  Hindi, multilingual/code-switching and translation requirements are deferred.
  Preserve existing multilingual capabilities, stored transcripts and translations.
- Premiere is first, with **file-based reviewed markers/selects** and stable source
  references; portable records support Resolve later. Suggest camera/audio matches
  for confirmation; Premiere handles editing synchronization and finishing.
- Both **in-app AI chat and portable context packs for external AI** are launch
  requirements. Optional cloud analysis is offered during project setup, with
  meaningful provider, input-scope and cost choices still to be designed.
- Support one primary film and related cutdowns, aspect ratios and alternate versions.
- Include the GitHub release updater in the design and delivery plan.
- Phone use means Codex development supervision. CyneDirector mobile layout,
  remote job control and a custom phone API are outside current product scope.
- Initial validation uses the user's own available projects. The approximately
  800 GB wedding on an SSD is an important workload, not the genre boundary.

## Design the complete editor journey

Cover these connected steps, including what the editor sees, decides and receives:

1. **Project setup after offload/backup:** source folders, workspace locations and
   capacity, video/separate audio, scripts/briefs/schedules/shot lists, creative
   brief, project roster/context guide and optional reference images.
2. **Progressive understanding:** quick coverage of every source, useful partial
   results, deeper selected/overnight analysis, explicit gaps/failures and recovery.
   Organization is virtual and editable; original media remains in place.
3. **Find and review:** search/recent results, virtual groups and the hierarchy
   project → scenes/events/topics → clips → moments. Use synchronized playback,
   filmstrip and transcript; hover/scrub or click a quote to reach the source.
4. **Correct and select:** keyboard In/Out and transcript selection, favorites,
   rejects, notes, editable speaker/person labels and reviewed identity suggestions.
   Timed actions/subjects/framing/movement, notable sounds and technical-quality
   flags support review. Flags never automatically discard material.
5. **Develop a story:** shared project evidence for chat and context export, a
   structured creative brief, an editable paper edit with quotes, ranges and visual
   coverage, and separately identified proposed narration. Preserve corrections.
6. **Deliver and revise:** versioned context packs, related film versions, reviewed
   Premiere markers/selects, export validation, and offline/relinked source behavior.
7. **Operate and update:** secondary jobs, models/providers, storage/settings and
   published-release updates. Define safe restart, interrupted work, failures and
   recovery without interrupting review or losing data.

Design empty, loading, partial, uncertain, failed, offline, cancelled, recovery and
version-conflict states wherever they affect these journeys. Include desktop window
resizing, legible transcripts, focus/accessibility, and Mac/Windows keyboard conventions.

## Define the shared evidence and AI context contract

Specify a concrete schema and a small readable/structured example pack. Include:

- Stable asset IDs, portable source locators, source timebases and exact ranges.
- Original dialogue, editable speaker labels, timed visual observations and
  supporting thumbnails/contact sheets where enabled.
- A creative brief, project organization, roster/context and editor corrections.
- Distinct observations, quotations, interpretations, unknowns, review status and
  suggested narration. A proposed line must never appear as a real spoken quote.
- Every source accounted for, with actual analysis coverage, methods/versions,
  unanalysed spans and failures. Coverage accounting does not prove exhaustive
  semantic understanding.
- Versioned snapshots, stable references and explicit corrections/changes/gaps.
- A readable brief plus structured detail, transcripts and optional contact sheets,
  with an index/chunking strategy for realistic chatbot upload/context limits.

Demonstrate both in-app source checking and a portable pack an external AI can use
to propose a source-cited paper edit. Preserve existing translations separately
where present; new translation workflows are deferred. Do not upload actual media.

## Reevaluate models against the accepted tasks

Use the installed/tested stack as the baseline. Verify time-sensitive candidate
claims using current primary publisher documentation; the dated shortlist is
research, not a final selection. Explain each component in plain language: visual
retrieval, timed visual understanding, speech recognition/alignment, speaker turns,
sound/technical flags and grounded story generation. Separate model capabilities
from features that require sampling, storage, review or other application logic.

Produce an evaluation matrix and a bounded benchmark plan with matched samples,
editor-checked references, English/Indian English accuracy, timing, useful retrieval,
unsupported claims/omissions, throughput, peak memory, disk growth and Mac/Windows
runtime feasibility. Include local and optional cloud tradeoffs, licensing and
distribution constraints. Mark measured evidence versus published claims and
unknowns. Recommend candidates conditionally; do not declare a winner without
task evidence, install weights, change dependencies or migrate existing indexes.

## Specify safe delivery and updates

Design updates from published GitHub Releases for `kanatwork/CyneDirector`, using
compatible installed Mac/Windows assets. Show version/notes, download and safe
restart behavior, active-work handling, failed/interrupted update recovery and
schema compatibility. Preserve media/projects/jobs/settings/caches. Separate app
updates from model downloads/index migrations and full-library processing.

Provide a packaging/updater feasibility recommendation tied to the actual desktop
architecture. Explain dependencies and alternatives; do not assume a framework
rewrite. An updater notification or prototype does not count as a tested installer.

## Required outputs and completion criteria

Save durable, linked artifacts under `docs/design/` and an isolated prototype
directory. Start with an index that identifies what is ready for review. Deliver:

1. **Requirement traceability:** all 36 decisions, the English-only amendment and
   updater mapped to screens, behaviors, acceptance tasks and open implementation
   questions. Preserve the accepted launch scope; propose sequencing separately.
2. **Product/interaction specification:** navigation, entities, editor journeys,
   priorities, controls and state transitions, with reasons tied to editor tasks.
3. **Visual system and complete core screen designs:** typography, spacing, colors,
   controls, selection/focus states, keyboard behavior and desktop layouts.
4. **A runnable connected prototype:** exercise setup → progressive results →
   search → source review → correction/select → story/chat → pack/Premiere export,
   plus representative recovery and update states. Simulated analysis/export must
   be visibly labeled. Prototype code may be written separately without altering
   production workflows; use a lightweight local format with clear opening steps.
5. **Concrete evidence-pack and paper-edit examples**, plus the model evaluation
   matrix/benchmark plan and packaging/updater recommendation.
6. **Validation and implementation plan:** tasks, proposed measurable acceptance
   thresholds, dependencies, reviewable implementation slices and a revised
   desktop-product readiness rubric. Update the active build plan to the design's
   actual status. Do not increase the historical app score for design output alone.

Use the user's actual project context where already available. Otherwise use
clearly labeled representative demo data for all five genres, including a large
SSD inventory, long clips, duplicate names and offline media. A demo fixture is
not a real footage analysis, a storage benchmark or an observed editor session.
Do not process the full 800 GB library during design work.

Verify the prototype by opening it, exercising the specified routes/controls and
checking representative screen sizes and important failure/recovery states.
Inspect the rendered result, correct issues and record what actually passed.
Identify unavailable live integrations or hardware validation without pretending
they passed. Keep simulated exports separate from verified Premiere interchange.

Do not stop at a plan or generic wireframe descriptions: finish the reviewable
artifacts and prototype within the authorized design scope, recording genuine
blockers. Ask essential questions inline, never popup forms; do not repeat the
completed questionnaire. In the final handoff, link the design index/prototype,
summarize validation, and identify the decisions requiring the user's design review
before production implementation begins.
