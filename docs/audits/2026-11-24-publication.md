# Publication checkpoint — engineering foundations and redesign handoff

24 November 2026. This checkpoint accompanies the commit on
`codex/wedding-workflow-plan`, based on upstream `efd0930`. It captures the current
source, regression tests, Mac setup, operating guides, product decisions and
redesign handoff for continuation in another chat.

## What this checkpoint contains

- Safe per-file reprocessing/generation publication and source-relative scene timing.
- Apple Silicon setup/launch scripts, pinned dependencies and FFmpeg/FFprobe setup.
- SSD workspace/capacity checks, durable jobs, bounded clip buffers/speech windows,
  protected retention, verified root relinking and workspace configuration updates.
- All 36 product decisions, including the search-first home screen and later
  English-only clarification (Indian English accents included; Hindi deferred).
- The accepted GitHub release updater requirement and complete design execution brief.

The existing app remains a prototype. The complete redesign, in-app AI/context-pack
workflow, tested Premiere interchange, installed-build updater and Windows release
validation are planned; this publication does not claim they are implemented.

## Fresh pre-commit verification

| Regression suite | Passed |
|---|---:|
| search | 33/33 |
| review | 23/23 |
| safe-reprocessing | 28/28 |
| workspace-jobs | 39/39 |
| memory-retention | 41/41 |
| worker-memory | 3/3 |
| workspace-changes | 34/34 |
| **Total** | **201/201, no skips** |

Also passed: Python compilation, `pip check`, launcher/setup shell syntax,
documentation link checks and active-file whitespace checks with existing CRLF
endings recognized. The archived February build plan retains its original trailing
spaces; it is a historical snapshot excluded from the active-file whitespace check. The 28 application/test fingerprints from the latest technical audit
still match. A scan of pending files found no credential-pattern matches.

This fresh run used disposable test fixtures. Native GUI and actual cached-model
inference evidence remains in the earlier audits; those checks were not repeated
for this publication. No original footage or user project was processed, and no
new model was installed. Virtual environments, weights, caches and local verification
logs remain ignored and are not part of the commit.

Earlier audit/evidence files describe their verification-time state as uncommitted.
Those descriptions are historical snapshots, not the publication state of this
checkpoint. The former 67/100 rubric remains historical; publication does not change
the product's readiness score.

## Continue the design phase

Start the next chat on branch `codex/wedding-workflow-plan`. Read the
[complete redesign handoff](../redesign-handoff.md),
[product decisions](../product-decisions.json), [product brief](../product-brief.md)
and [active build plan](../../buildplan.md). Design the complete application and
connected prototype before implementing new production workflows.
