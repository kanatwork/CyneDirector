# Archived discovery questionnaire before inline answers

Historical wording. Inline questions 7–36 were subsequently adapted. Use the
current decision record for the meaning of accepted answers, especially 9, 19,
31 and 36. Links were adjusted for the archive location.

# CyneDirector — editor product discovery

24 November 2026. **Status: questions 1–6 decided; questions 7–36 pending.**

Confirmed: desktop for video editors on Apple Silicon Macs and Windows PCs;
Intel Macs are excluded. Phone use is Codex supervising development, not a mobile
CyneDirector requirement. Premiere and the wedding project are the known personal
workflow. The user wants to explore exporting footage knowledge to an external AI.

The previous task order emphasized engineering hardening without establishing a
coherent editor experience. That work protects data; it does not demonstrate a
useful or lovable product. The [active build plan](../../buildplan.md) now starts with
discovery, an editor journey, a prototype and outcome-based scope selection.

## Confirmed product vision — answers 1–6

CyneDirector is a desktop companion for solo editors and small teams making
story-led films. It helps them understand raw footage and develop stories grounded
in the material. Launch scope covers weddings, fiction, documentaries, commercials
and social content equally. It uses reliable file-based handoff to Premiere.

The next product/design phase is a **full application redesign before completing
a workflow**. The first result that establishes value is a footage brief and paper
edit linked to supporting evidence. The wedding remains one intended real project,
not a restriction on launch positioning or the only genre acceptance test.

| Question | Explicit answer | Implication |
|---|---|---|
| 1 — User | A: solo editors/small teams making story-led films | Optimize individual editorial work and lightweight team use |
| 2 — Promise | A: understand raw footage and develop a grounded story | Coverage, meaning, review and source evidence drive the experience |
| 3 — Launch breadth | C: weddings, fiction, docs, commercials and social equally | Shared core with credible workflows and acceptance cases for every listed genre |
| 4 — NLE role | A: desktop companion with file-based Premiere handoff | Companion interaction and reliable interchange; plugin/timeline scope is not assumed |
| 5 — Next cycle | C: redesign the whole app before completing a workflow | Whole-app information architecture, visual system and interaction/state designs precede workflow completion |
| 6 — First value | A: evidence-linked footage brief and useful paper edit | Judge source-grounded editorial usefulness, not model count or index throughput |

The user requested **six questions per batch**. Record answers before moving to
the next batch. Questions 7–36 below are the remaining decision inventory, not
approved answers. Reword future batches where necessary to respect the confirmed
multi-genre launch; do not quietly return to a wedding-first product.

## Design consequences of the confirmed choices

- Design a complete application structure and consistent visual/interaction
  system, including onboarding/project setup, analysis/coverage, browsing/search,
  source review, correction/logging, story context and export/handoff states.
- Map a common editorial journey and genre-specific needs: event coverage for
  weddings, scene/take/script context for fiction, speakers/themes for docs,
  brief/product/message coverage for commercials, and formats/hooks for social.
  These examples guide discovery; individual features still need decisions.
- Use representative scenarios from every launch genre in the design evaluation.
  Broad launch support needs more than changing the name of wedding event bins.
- Redesign first does not automatically select a new UI framework or require a
  rewrite of tested storage/media-safety code. Those are later implementation
  decisions informed by the full design.
- Review model options against this agreed product; see the
  [dated model reassessment](../model-evaluation-2026-11-24.md). New candidates remain
  untested on the app and are not an authorized environment/model migration.

## The questionnaire

Choose one primary answer per question, or supply your own. The original recommendation was **A**
in each question. The user explicitly selected **A, A, C, A, C, A** for 1–6. Answers can arrive in
batches, for example `1A, 2C, 3A`, with notes where needed.

1. **Who should we serve first?**
   A. Solo editors/small teams making story-led films. **Recommended.**
   B. High-volume studios with assistant editors/shared workflows.
   C. A broad editor/researcher/archivist/casual-creator audience.
2. **What is the main promise?**
   A. Understand raw footage and develop a story grounded in it. **Recommended.**
   B. Find a particular shot or line quickly.
   C. Automatically assemble a first rough cut.
3. **How narrow is the first version?**
   A. Prove it on the wedding, reusable for interviews/docs. **Recommended.**
   B. Wedding-only specialist.
   C. Equal support for every film/content genre at launch.
4. **How does it fit Premiere?**
   A. Desktop companion with tested file-based handoff. **Recommended.**
   B. Primarily a Premiere panel/plugin.
   C. Its own timeline and finishing application.
5. **What guides the next build cycle?**
   A. One useful import → review → story-context → handoff workflow. **Recommended.**
   B. More analysis features first.
   C. Redesign the whole app before completing a workflow.
6. **What first result makes it worthwhile?**
   A. An evidence-linked brief/paper edit useful for starting the film. **Recommended.**
   B. Reliable first-few-result retrieval of known moments.
   C. A usable selects sequence imported directly into Premiere.

7. **When does it enter the edit?**
   A. After offload/backup, before detailed logging/rough cut. **Recommended.**
   B. During an existing edit to find missing material.
   C. After delivery for archive search.
8. **Which bottleneck comes first?**
   A. Understanding the material and its possible story. **Recommended.**
   B. Finding a known moment.
   C. Organization and technical preparation for the NLE.
9. **What deliverable guides the wedding pilot?**
   A. One approximately 5–10 minute story-led film. **Recommended as a bounded pilot.**
   B. A 20–40 minute wedding film.
   C. Teaser, highlight film and full events together.
10. **How is media organized virtually, preserving originals?**
    A. Suggested, editable event/scene bins. **Recommended.**
    B. Manual bins/labels.
    C. Flat catalog plus search/filters.
11. **How should multicamera/external-audio relationships work first?**
    A. Suggested/confirmed event and angle links; NLE sync separate. **Recommended.**
    B. Automatic sync/merge into event timelines.
    C. Independent sources until later.
12. **What inputs beyond camera video?**
    A. Separate production audio and a written brief/schedule. **Recommended.**
    B. Video only.
    C. Audio, photos, reference films, music and project documents from launch.

13. **What analysis strategy?**
    A. Quick all-clip coverage, then deeper analysis as needed. **Recommended.**
    B. Deep analysis of everything before presenting results.
    C. Analyze only manually selected clips.
14. **What speech workflow? Add actual spoken languages in a note.**
    A. Multilingual/code-switched originals with optional English translations. **Recommended.**
    B. English only initially.
    C. One manually selected non-English language per project.
15. **What speaker identification?**
    A. Editable speaker labels, with names assigned/confirmed by the editor. **Recommended.**
    B. One manual speaker per file/audio track.
    C. Transcripts without speaker labels.
16. **What visual detail?**
    A. Timed actions/subjects, framing and camera movement. **Recommended.**
    B. A few captions and searchable object tags.
    C. Detailed emotional/relationship/story interpretations.
17. **How does the app learn people and event meaning?**
    A. Project roster/event guide, optional references, reviewed suggestions. **Recommended.**
    B. Anonymous descriptions only.
    C. Manual tagging of every relevant appearance.
18. **What usability/audio detail?**
    A. Reviewable technical flags, speech clarity and notable sounds. **Recommended.**
    B. Content/dialogue only; the editor judges usability.
    C. Extensive automatic quality grading/ranking.

19. **What priority for the AI-readable export?**
    A. Central first-version feature alongside source review. **Recommended.**
    B. Next milestone after search/selects.
    C. Secondary metadata export.
20. **How should external AI collaboration begin?**
    A. Portable export to the Claude/ChatGPT tool already used. **Recommended.**
    B. In-app chat connected to the user's API account.
    C. Both in the first release.
21. **What default export contents?**
    A. Readable overview, structured detail/transcripts, optional contact sheets. **Recommended.**
    B. One compact text document.
    C. Always include image/video evidence.
22. **What constitutes complete project context?**
    A. Every source accounted for; timed records and explicit analysis gaps. **Recommended.**
    B. Only automatically selected important moments.
    C. Brief summaries, with detail requested separately.
23. **How should facts and interpretation be presented?**
    A. Separate observations/quotes from interpretation, with unknowns/review state. **Recommended.**
    B. Observations/transcripts only.
    C. Editorial narrative first, evidence appendix second.
24. **What creative input comes first?**
    A. Brief: audience, duration, tone, must-use moments and exclusions. **Recommended.**
    B. Only a free-form prompt.
    C. AI proposes a direction before receiving preferences.
25. **What writing output first?**
    A. Paper edit: cited quotes, visual coverage and separate narration suggestions. **Recommended.**
    B. Beat outline plus footage-search suggestions.
    C. Polished script before source-clip selection.
26. **How should exported context change over time?**
    A. Versioned packs, stable references and a clear change/gap list. **Recommended.**
    B. Regenerate the full pack without revision tracking.
    C. A live AI connection to the current project.

27. **What is the home-screen focus?**
    A. Events, coverage, useful moments and next actions. **Recommended.**
    B. Search and recent results.
    C. Jobs, resources and detailed logs.
28. **What is the main review workspace?**
    A. Player, filmstrip and synchronized transcript together. **Recommended.**
    B. Clip grid plus separate player.
    C. Spreadsheet logging.
29. **How do editors make selects?**
    A. Keyboard In/Out and text selection, favorites/rejects/notes. **Recommended.**
    B. Keyboard ranges only initially.
    C. File-level ratings/tags before range selects.
30. **What signature interaction feels especially useful?**
    A. Hover/scrub or click a quote to reach the actual moment immediately. **Recommended.**
    B. An organized visual story map/contact sheet.
    C. Conversational theme/story proposals.
31. **What is the first Premiere handoff?**
    A. Reviewed ranges as markers/selects through tested interchange. **Recommended.**
    B. Manifest/timecodes for manual assembly.
    C. Plugin-created/modified Premiere sequences.
32. **How broad is initial NLE support?**
    A. Premiere first; portable records for Resolve next. **Recommended.**
    B. Premiere and Resolve equally at launch.
    C. All major NLEs at launch.

33. **What privacy/cloud policy?**
    A. Local default; explicitly choose exported/cloud text/images. **Recommended.**
    B. Optional cloud analysis selected during setup.
    C. Entirely offline, including story drafting.
34. **What desktop performance target?**
    A. Mainstream Apple Silicon/Windows editors, tiers, NVIDIA-first Windows acceleration. **Recommended.**
    B. Powerful workstations only initially.
    C. Equal NVIDIA/AMD/Intel Windows GPU acceleration at launch.
35. **What processing experience is acceptable?**
    A. Progressive useful results, optional deeper overnight work. **Recommended.**
    B. Deep overnight pass before reviewing anything.
    C. Near-instant results with a smaller analysis scope.
36. **How do we validate usefulness and delight?**
    A. Wedding pilot, then observe 3–5 working Mac/PC editors. **Recommended.**
    B. Personal wedding use only until that film is finished.
    C. Early public beta driven by feature requests.

## Proposed AI context pack

An export should help an external AI reason from evidence that the editor can
check. It cannot guarantee the AI understands the footage exactly as an editor
would, or recover important information that was never captured.

Candidate contents, pending questions 19–26:

| Layer | Contents |
|---|---|
| Creative brief | Intended film/audience/tone/duration, event guide, people/roles, must-use/excluded material |
| Source manifest | Stable IDs, portable paths, duration, rational rates/timebases, source/sequence timing distinctions and versions |
| Dialogue | Source/range-linked original transcript text, languages, speaker/review state, separate translation; recognition errors remain reviewable |
| Visual evidence | Timed shots/actions/subjects, relevant framing/motion, scene/sample precision and optional labeled frames/contact sheets |
| Editor decisions | Corrected labels, notes, reviewed ranges and accepted/rejected suggestions |
| Coverage | Which sources/spans/stages were analysed, failed, skipped or remain unknown; methods and limits |
| AI reading guide | Project/event/clip overview and chunk index; instructions to cite sources, preserve quote wording and distinguish proposed narration |

Readable Markdown and structured JSON/JSONL are candidate formats. Exact upload
formats/batch sizes must be tested against the chosen Claude/ChatGPT surface.
An external chatbot does not automatically gain access to linked local SSD files;
provide the relevant evidence with the pack. A single enormous document/ZIP is
not assumed to fit or be fully read. Keep detail addressable in event/clip chunks.

Coverage is not the same as semantic completeness. Every source can be accounted
for while an important glance or ritual is still missed. Use known editorial
tasks, a manually checked sample and visible unknowns to measure that gap. Model
similarity/detection scores are not automatically calibrated probabilities of
editorial truth. Start with method, coverage and review state.

## What happens after answers

Synthesize decisions into the one-page brief, v1/later scope, editor journey,
prototype tasks, acceptance criteria and revised score rubric. Identify conflicts
and material unknowns explicitly. Do not quietly treat all recommended options as
the approved backlog. Read the [model refresher](../models.md) to distinguish current
code from capabilities the proposed experience would still need.
