# CyneDirector — discovery decisions

24 November 2026. **36/36 answered. Question 27B and the English-only
launch clarification are confirmed.**

The user completed the first six questions, then requested all remaining questions
inline and answered them using numbered choices. **Use inline chat only; do not
send popup questionnaires.** The adapted inline wording supersedes the earlier
form/questionnaire. In particular, 9A means one film with related versions, 19A
means the knowledge hierarchy, 31A means file-based markers/selects, and 36B means
validation on the user's own available projects first.

Read the [product brief](product-brief.md), [active build plan](../buildplan.md) and
[machine-readable decisions](product-decisions.json). Previous question wording is
[archived](archive/product-discovery-before-inline-answers-2026-11-24.md).

## Explicit answers

| Question | Choice | Accepted meaning |
|---|---|---|
| 1 | A | Solo editors and small teams making story-led films |
| 2 | A | Understand raw footage and develop a story grounded in it |
| 3 | C | Support weddings, fiction, documentaries, commercials and social content equally from launch |
| 4 | A | Desktop companion with reliable file-based Premiere handoff |
| 5 | C | Redesign the whole application before completing a workflow |
| 6 | A | Evidence-linked footage brief and useful paper edit as the first valuable result |
| 7 | A | Enter after footage offload/backup, before detailed logging and rough cutting |
| 8 | B | Prioritize finding a particular shot, performance or spoken line |
| 9 | A | One primary film with related cutdowns, aspect ratios and alternate versions |
| 10 | A | Suggested editable virtual scene/event/interview/take/topic groups; originals remain in place |
| 11 | A | Suggest matching sources/groups for confirmation; leave editing synchronization to Premiere |
| 12 | A | Video, separate production audio and scripts, briefs, schedules or shot lists |
| 13 | A | Quick coverage across every source, followed by deeper analysis where useful |
| 14 | A, subsequently narrowed | English speech including Indian English accents; original transcripts; Hindi/multilingual/code-switching/translation requirements deferred |
| 15 | A | Editable speaker labels with names assigned or confirmed by the editor |
| 16 | A | Timed shots, actions, subjects, framing and camera movement |
| 17 | A | Project roster/context guide, optional reference images and reviewed suggestions |
| 18 | A | Reviewable focus/shake/exposure/speech-clarity flags and notable sounds |
| 19 | A | Project overview → scenes/events/topics → clips → individual moments |
| 20 | C | Both portable external-AI export and in-app chat for launch |
| 21 | A | Readable brief, structured records and transcripts, with optional labeled contact sheets |
| 22 | A | Every source accounted for, timed records and explicit gaps/failures |
| 23 | A | Separate observations/quotes from interpretations, with unknowns and review status |
| 24 | A | Structured creative brief: audience, duration, tone, must-use material and exclusions |
| 25 | A | Paper edit with quotations, source ranges, visual coverage and separate narration suggestions |
| 26 | A | Versioned context packs with stable references and explicit changes/corrections/gaps |
| 27 | B | A prominent search box and recent results on the home screen |
| 28 | A | Player, filmstrip and synchronized transcript together |
| 29 | A | Keyboard In/Out plus transcript selection, favorites, rejects and notes |
| 30 | A | Hover/scrub or click a quotation to reach the source moment immediately |
| 31 | A | Reviewed ranges as markers/selects via tested Premiere interchange |
| 32 | A | Premiere first; portable records support Resolve next |
| 33 | B | Optional cloud analysis offered during project setup |
| 34 | A | Mainstream Apple Silicon and Windows editing PCs; analysis tiers and NVIDIA-first Windows GPU acceleration |
| 35 | A | Useful progressive results during a session, optional deeper overnight processing |
| 36 | B | Validate on the user's own available projects first |

Question 14 initially specified English, Indian English and Hindi. The subsequent
explicit clarification defers Hindi: **English, including Indian English accents,
is launch scope.** Multilingual/code-switching and translation requirements are
deferred; preserve existing multilingual capabilities, transcripts and translations.

## Questionnaire complete

**27B — A prominent search box and recent results** is explicitly accepted.
It aligns with the known-moment bottleneck in 8B and immediate source access in 30A.
A project overview remains available in the complete design. No questionnaire
answers are outstanding; precise layouts and technical contracts still need design.

## Additional accepted requirement

An updater should make it easy to stay current when a new GitHub Release is
published. This is now release scope, with a proposed safe notification/download/
restart flow in the [updater contract](release-updater.md). It is not implemented
by recording the requirement.

## Interpretation, not additional user answers

Fast search/source review is the daily-use entry point; a trustworthy footage brief
and paper edit is the larger value. Suggested organization, a synchronized review
workspace and editor corrections connect those two. Both in-app AI and portable
packs must use the same underlying evidence and source references.

The user permits optional cloud analysis during project setup. Model/provider,
input scope, cost controls, precise analysis budgets
and detailed UI behavior remain design details to specify. None implies uploading
current footage, installing models, or rewriting the tested backend now.

The next deliverable is the **whole application redesign**, retaining equal
wedding/fiction/doc/commercial/social scope and using the user's own projects as
the initial validation setting. See [the design/build sequence](../buildplan.md).
