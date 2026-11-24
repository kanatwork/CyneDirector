# CyneDirector — product brief from the discovery answers

24 November 2026. **All 36 questions explicitly answered; 27B confirms search and recent
results on the home screen.** The [decision record](product-decisions.json) is authoritative.
Inline answers use the revised questionnaire; they supersede the earlier popup
wording. Do not send further popup questionnaires.

## Product definition

CyneDirector is an AI-assisted footage search and story-development desktop
companion for solo editors and small teams. It helps editors locate the right
picture or dialogue, understand their raw material, develop an evidence-linked
paper edit, and hand reviewed selections to Premiere.

Launch scope covers weddings, fiction, documentaries, commercials and social
content equally. Support Apple Silicon Macs and Windows editing PCs, with
NVIDIA-first Windows GPU acceleration and tiered analysis. Intel Macs and a
CyneDirector mobile UI are excluded. Phone usage means Codex supervising development.

The next milestone is the **complete application redesign**, before completing
a new workflow. This is not approval for an automatic framework/backend rewrite.

## Most important interpretation

**Fast, trustworthy retrieval is the daily-use entry point. Grounded story
development is the larger value.**

The user chose story understanding as the main promise (2A), but locating a known
shot/performance/line as the immediate bottleneck (8B), with immediate source
access as the signature interaction (30A). The review workspace therefore needs
to earn trust through quick search, playback and source checking. Story assistance
builds on that reviewed evidence. A chat-only shell or a dashboard of models/jobs
would miss much of the chosen experience.

Question 27B now explicitly confirms a prominent search box and recent results
as the home-screen emphasis. Keep project overview/coverage accessible in the
complete design; the exact layout remains to be designed.

## Confirmed user journey

1. **Set up after offload/backup.** Add video, separate audio and relevant scripts,
   briefs, schedules or shot lists. Supply audience, tone, duration, must-use and
   excluded material; optionally enable cloud analysis during setup.
2. **Get progressive coverage.** Account for every source in a quick first pass.
   Show useful partial results, incomplete/failed spans and the option for deeper
   selected or overnight analysis.
3. **Find and inspect.** Search picture/dialogue, browse suggested editable virtual
   groups, and review a synchronized player/filmstrip/transcript. Hover/scrub or
   click a quote to reach the actual source moment quickly.
4. **Correct and select.** Confirm speaker/person/character/event labels, edit
   mistakes, mark In/Out or transcript ranges, favorite/reject and add notes.
   Suggest camera/audio relationships for review; Premiere handles editing sync.
5. **Develop the story.** Use both in-app AI chat and portable external-AI context
   packs. Draft a paper edit with quotations, visual coverage, source ranges and
   separately identified proposed narration. Corrections remain part of the project.
6. **Deliver and revise.** Export reviewed markers/selects through tested Premiere
   interchange. Support one primary film with related cutdowns/aspect ratios/versions.
   Keep context-pack versions and stable source references. Resolve support follows.

## Confirmed first-release scope

| Area | Required experience |
|---|---|
| Project knowledge | Project → scene/event/topic → clip → moment hierarchy; genre-appropriate names and editable suggestions |
| Picture | Timed subjects/actions/framing/movement; reviewable focus/shake/exposure flags |
| Sound/dialogue | English, including Indian English accents; editable speaker labels and original transcripts; notable sounds and speech-clarity flags |
| People/context | Small roster/context guide, optional reference images and reviewed suggestions |
| Review/selects | Integrated player/filmstrip/transcript, fast source seeking, keyboard ranges, text selection, favorites/rejects/notes |
| AI | Both in-app chat and external-AI export; creative brief; citations, coverage, corrections and distinct interpretations |
| Export | Readable brief + structured records/transcripts, optional contact sheets, versioning and tested Premiere marker/select handoff |
| Processing | Progressive results, quick/deep tiers, optional project-level cloud analysis, truthful failures/recovery |
| Delivery | Installable Mac/Windows builds and an updater for new published GitHub Releases |

These are product requirements, not claims of completed functionality. The existing
app has verified media-safety/job foundations but lacks much of the chosen review,
story, AI-chat/context-export, interchange and delivery experience.

## Trust and editorial control

- Every source is accounted for; analysis coverage is not a guarantee that every
  meaningful detail was understood. Expose missing/failed/uncertain analysis.
- Keep observed evidence, recognized/reviewed quotation text, interpretation and
  proposed narration distinguishable. Source citations must remain inspectable.
- Editor corrections, names and creative constraints guide AI output. The model
  cannot invent family relationships or turn a suggested line into a real quote.
- Technical flags are review aids, not automatic discard decisions. Handheld motion
  or an imperfect image can be editorially intentional or irreplaceable.
- Cloud analysis is an optional project setup choice with clear data scope and cost.
  This questionnaire answer is not a request to upload current footage now.
- Originals and existing projects stay protected. A select/reject is virtual.

## Language and model consequences

The user subsequently deferred Hindi: launch speech scope is **English, including
Indian English accents**. Multilingual/code-switching and translation requirements
are deferred too. Preserve existing capabilities, transcripts and translations;
this scope change does not remove stored data or disable current models.

Keep the current models as a reproducible baseline. Evaluate contemporary video
understanding and retrieval against these editorial tasks. For speech, compare
English recognition, names, accent robustness, speaker labels and useful source
timing. Lack of Hindi support no longer disqualifies an English candidate; models still
need a matched desktop benchmark before selection. See the
[updated model review](model-evaluation-2026-11-24.md).

## Redesign deliverable

Produce a complete, connected application design before choosing the implementation
sequence: information architecture, navigation, visual language, reusable components,
keyboard behavior and core screens/states from setup through export/update/recovery.

Proposed work areas for design exploration:

- Project/brief and analysis coverage.
- Find/review, logging and selects.
- Story/paper edit with AI assistance and source evidence.
- Deliverables, context versions and export.
- Secondary job, model/provider, storage and application-update settings.

These areas are design proposals, not final navigation labels. The search-first
home-screen emphasis is confirmed by 27B.
The same conceptual workflow should use appropriate genre concepts: events/people
for weddings, scenes/takes/characters for fiction, speakers/themes for docs,
brief/product/message coverage for commercials and hooks/versions for social.

## Validation and scope discipline

The user selected **their own available projects first** (36B), not an external
editor cohort or immediate public beta. Start there. Equal five-genre launch remains
the product scope; record which genres have actual validation evidence rather than
claiming that one wedding proves all of them.

Three key tasks should shape the prototypes and later benchmarks:

1. Find and inspect a known shot, performance or line with little friction.
2. Produce a useful paper edit whose quotations/visual claims can be checked.
3. Bring reviewed selections into Premiere and revise them without losing context.

Full app redesign, broad genres, in-app chat **and** portable export are a
substantial release scope. Design them together, then implement in slices that
support the agreed end-to-end experience. Model upgrades and infrastructure tasks
must serve a named user outcome or demonstrated safety/correctness need.

## New requirement: GitHub release updater

The updater is accepted product scope. Proposed experience: check for new stable
published releases, show version/release notes, download the correct platform build,
then offer installation at a safe restart. Updates preserve user projects, media,
jobs/settings and caches. App/model/schema changes need explicit compatibility and
recovery handling. See the [release/updater contract](release-updater.md).

This turn records the requirement; it does not install an updater or bypass the
user's redesign-first sequence. The release pipeline and installed-build update
flow must be implemented and verified before claiming update support.
