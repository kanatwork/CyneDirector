# CyneDirector reassessment — efd0930

Superseded by [safe-reprocessing verification](2026-11-24-safe-reprocessing.md): current score 55/100. The 48-point assessment below describes upstream efd0930 before local fixes.

24 November 2026, Asia/Kolkata. This supersedes the readiness judgment in the
[initial audit](2026-11-24-wedding-readiness.md), which remains historical evidence.

## Verdict: 48/100, previously 38/100

The new GitHub `main` is `efd093023c2b30410a5f11553b251e94f69e9f88`, dated
24 November 2026, 03:39:24 IST. It changes 22 files, adding 941 lines and removing
281 relative to `112388b`. The restored working checkout was fast-forwarded to
this commit while preserving local planning changes.

The same wedding/Premiere/phone rubric is used. This is readiness judgment,
not a measured percentage of completed code. The update materially improves
correctness; it does not yet deliver durable jobs, Premiere selects, or phone job
control. Real wedding-media quality and processing throughput remain unmeasured.

| Dimension | Before | Now | Reason |
|---|---:|---:|---|
| Media integrity and recovery | 10/25 | 16/25 | Better failure propagation, worker ownership, source freshness, and derivative naming; recovery/publication gaps remain |
| Finding useful moments | 12/20 | 15/20 | Better query semantics, duration query filtering, cache invalidation, and deterministic ranking |
| Premiere workflow | 2/20 | 2/20 | SRT improvements help, but no selects sequence/relink contract |
| Phone operation | 4/15 | 4/15 | No new persistent job/command interface or verified phone setup |
| Setup and compatibility | 5/10 | 5/10 | Source compatibility improvements; runnable Mac environment still absent |
| Validation and delivery | 5/10 | 6/10 | More regression tests, including real SQLite cases; integration scripts added but unexecuted here |
| **Total** | **38/100** | **48/100** | **+10** |

## Checks actually performed

Run in a clean detached worktree of the new commit, separately to avoid global
import stubs leaking between suites:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cyne-recheck-pycache python3 -m compileall -q core gui workers main.py config.py
python3 -m tests.smoke_search
python3 -m unittest tests.test_review_regressions -v
```

- Compilation: passed.
- Search smoke suite: **33/33 passed**, up from 23.
- Review regression suite: **20 passed, 1 errored** out of 21. The error is the
  existing Python 3.9 incompatibility importing `float | None` in
  `core/proxy_generator.py:65`, not an observed proxy-naming assertion failure.
- The remaining regression tests exercise subtitles, settings, real SQLite with
  mocked vector storage, and source-extracted GUI/queue logic. GUI doubles do not
  establish actual Qt lifecycle correctness.
- `tests/runtime_smoke.py` adds an offscreen Qt/FFmpeg/real-vector-store check
  with replacement AI QThreads. It was inspected but not run: dependencies and
  FFmpeg are unavailable on this checked Mac environment.
- `tests/cached_ai_smoke.py` was inspected, not run. It explicitly expects an
  RTX 5070/CUDA device and cached models; it is not a generic Mac validation.
- No model downloads, real wedding-media run, Premiere exchange, or phone test.

Test scripts in the commit are evidence of coverage intent, not proof they passed
on the other machine. No execution report from that machine was supplied.

## Reconciliation with the original findings

| ID | New status | Evidence and remaining limits |
|---|---|---|
| F01 naming collision | Addressed in code; isolated naming check passes | Proxy/thumbnail names include a hash of the normalized absolute source path. Extracting the actual naming function confirms three distinct names for two camera folders and two source extensions. The full module regression import is blocked here by Python 3.9. Mount-independent asset IDs and generation-safe output publication remain future work. |
| F02 next-worker ownership | Addressed; control-flow test passes | Completion detaches/deletes the finished worker before advancing the queue; GUI uses QThread `finished`. Actual Qt integration still needs execution. |
| F03 pause-boundary stall | Addressed; regression passes | Resume dispatches pending work when no current operation remains. This does not implement mid-inference checkpoints. |
| F04 shared freshness | Addressed for source changes; regression passes | Stage-specific mtime-nanosecond/size signatures prevent a visual scan certifying an old transcript. Settings/model versions and a separate embedding stage are still absent. |
| F05 swallowed writes | Substantially improved | SQLite read/write and visual-vector upsert failures propagate; rollback is tested. Temporal upsert still logs and swallows errors. Cross-store publication remains non-atomic. |
| F06 estimated timestamps | Still open | Indexer still divides clip duration evenly across detected scenes; no real cut timestamps are retained. |
| F07 cancellation/completion | Partially addressed | Errors and cancellation now affect GUI/background success and source-signature completion. The indexer still runs partial-file finalization, writes legacy last_scanned, and emits 100 after cancellation. |
| F08 settings root shape | Addressed; regression passes | Non-object JSON roots fall back to defaults. Atomic saves and comprehensive per-value validation remain separate work. |
| F09 search/filter/cache | Partially addressed | Engine duration queries, exact-phrase empty results, option-sensitive cache keys, refresh invalidation, and several semantic errors are fixed. GUI duration selection remains unused; GUI sorting/filtering still applies to a page rather than all candidates. |

The unchanged `config.py` still reports version 2.1.0. Use commit hashes to
distinguish these builds. The old AST probe script targets the original commit
and must not be used as a health check of this revised source.

## Highest-priority remaining work

1. **P1: preserve the previous valid index during reprocessing.** At
   `workers/indexer.py:190` the visual signature is cleared and at `:191` existing
   vectors are deleted before replacement processing starts. A failure or
   cancellation can therefore remove the last working visual index and leave a
   partial replacement. `core/database.py:197` similarly deletes transcript
   vectors before the transcript save commits. Use staged generations and publish
   only after successful persistence; retain the previous generation on failure.
   This is source-traced, not a simulated disk-failure integration result.
2. **P1: record real scene/frame times.** `workers/indexer.py:366` still assigns
   equal scene durations. Correct this before relying on temporal results or
   exporting Premiere in/out ranges.
3. **Finish truthful cancellation and worker shutdown.** Do not finalize a
   cancelled partial file or present 100% completion. `gui/main_window.py:2310`
   stops the foreground worker/watcher but still does not stop/join the background
   indexing worker before unloading shared models. Test shutdown with real Qt.
4. **Complete durable, bounded processing.** Queues remain memory-only. No
   crash/restart ledger, checkpoint recovery, media-root relinking, or independently
   versioned transcript-embedding stage exists. Scene images still accumulate for
   the duration of a file.
5. **Finish search UX**, then implement reviewed collections, Premiere exchange,
   and typed phone commands from the existing build plan.

The next task should verify the fixes on a supported Python runtime and close
remaining cancellation/shutdown/timestamp/publication issues. Do not reimplement
the worker-handoff, pause-boundary, or settings-root fixes already present.

The definition of 100 remains the [same acceptance rubric](../../buildplan.md):
real recovery and source fidelity, measured retrieval, verified Premiere selects,
phone-controlled durable jobs, reproducible setup, and a reconciled full-library
run. New feature count alone does not satisfy those gates.
