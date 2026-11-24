# SSD workspace and durable jobs

This is the implemented local workflow for metadata inventory, visual indexing,
and original-language speech transcription. Project data stays in the existing
project; new generated files use an explicitly configured workspace. Translation
and Premiere export have separate product decisions. Codex phone development is
outside the application requirements.

## Set up the workspace

Open **File → Workspace & Jobs…** in the Mac app. Enter original-media folders
(one per line), choose existing folders for generated files and model cache, and
set the free-space reserve. The default is **20 GiB per destination filesystem**.
Save the workspace before processing. The model-cache folder that already holds
the tested downloads on this Mac is:

```text
/Users/kanishkar/Desktop/The Tools/CyneDirector/.cache/huggingface
```

The project directory, generated-file destination and model cache must be outside
all original-media roots. They may share an SSD if capacity permits. If an older
project contains original media beneath its project directory, leave it intact;
plan a backed-up metadata relocation or a separate project before configuring.
The app does not move media, copy 800 GB, or migrate existing databases/artifacts.

All root folders must exist. Configuration records directory identity and, when
available on Mac, volume UUID. Missing/replaced directories fail closed; the app
does not deliberately recreate an offline SSD mount. New artifact directories are
namespaced by workspace ID, kind and generation. Existing artifact pointers stay
where they are.

Version 1 now supports additive configuration revisions and verified source-root
relinking through saved GUI/CLI preview/apply plans. Source keys, root/asset IDs
and existing job payloads stay stable. New output/model destinations affect future
jobs; old derivatives stay pinned in place. Do not hand-edit live paths or copy
databases to simulate relinking. See the [relink/update guide](workspace-relinking.md).
Project relocation, existing derivative/cache migration and physical SSD acceptance
remain separate gates.

## Run and supervise in the GUI

- Use the existing Video/Audio selections and **Start Indexing / Start Workflow**.
  Once configured, the entire pending visual/speech scope is saved as one durable
  job before its thread starts, including different source selections per stage.
- Or check sources, open **Workspace & Jobs**, choose Metadata inventory, Visual
  search and/or Speech, then submit. Inventory reads FFprobe metadata without AI.
  Repeated identical submissions reuse their job; select **Force a new analysis**
  for a deliberate new run with the same inputs/settings, keeping old job history.
  Use this dialog for model/settings reprocessing; the older source-freshness
  checkbox filter does not detect every algorithm/model-version change.
- The view shows persistent IDs, counts, current file/stage, heartbeat, errors and
  recent events. Completed/failed/cancelled/pending counts are stage counts.
- **Pause after stage** finishes the current publication, then stops dispatching.
  **Cancel** requests worker stop and prevents an uncommitted stage from publishing.
  A completed publication stays valid. Retry failed work explicitly.
- Settings editing is blocked while processing, preserving submitted options.
  Pausing lets you edit settings for a new job; resuming keeps the prior snapshot.
- Closing the jobs dialog keeps work running. Quitting the app requests a pause,
  waits for the current stage, and preserves pending work. Reopen the project and
  use **Run / resume** for the same job ID.

The configured durable queue currently supports visual and speech operations.
Turn off Translate for this queue; translation and the older automatic watcher
queue are not durable jobs. Configured watcher callbacks reject generated outputs
as source media; original-root automatic monitoring is still planned. Background
processing is disabled until a workspace
exists, and worker guards enforce source/capacity checks when it does run.

## Local JSON commands

Run from the repository through `./cyne.command` (Mac venv/PATH wrapper). The
equivalent cross-platform entry point is `python -m cyne_cli`. Use absolute paths;
`--project` is the project directory, not its `.cyne` file. The examples are
templates: choose actual mounted folders before running them.

```bash
./cyne.command --project "/path/to/WeddingProject" configure \
  --media-root "/Volumes/WeddingSSD/Originals" \
  --output "/Volumes/WorkSSD/CyneGenerated" \
  --model-cache "/path/to/existing/huggingface" --reserve-gib 20

./cyne.command --project "/path/to/WeddingProject" preflight \
  --files-from "/path/to/WeddingProject/Wedding.cyne" \
  --stage index_visuals --stage transcribe_audio

./cyne.command --project "/path/to/WeddingProject" submit \
  --file "/Volumes/WeddingSSD/Originals/CameraA/C0001.MP4" \
  --stage inventory --stage index_visuals --stage transcribe_audio \
  --mode accuracy --whisper-model small --request-key ceremony-pilot-01

./cyne.command --project "/path/to/WeddingProject" start JOB_ID
./cyne.command --project "/path/to/WeddingProject" status JOB_ID
./cyne.command --project "/path/to/WeddingProject" events JOB_ID --after 0
./cyne.command --project "/path/to/WeddingProject" pause JOB_ID
./cyne.command --project "/path/to/WeddingProject" resume JOB_ID
./cyne.command --project "/path/to/WeddingProject" cancel JOB_ID
./cyne.command --project "/path/to/WeddingProject" retry-failed JOB_ID
./cyne.command --project "/path/to/WeddingProject" list
```

Repeat `--file`/`--stage` to add scope. `--files-from` reads a JSON path array or an
existing `.cyne` file's `files` array without rewriting it. Repeated identical
submissions return the same ID; reusing a request key with different scope/settings
fails. Without a key, a hash of the source signatures, stages, workspace and
settings is used. A changed source revision needs a new submission/key.

`run JOB_ID` executes in the foreground and returns final JSON. `start JOB_ID`
launches a detached child using the same venv; it survives the launcher exiting.
Logs go under the selected generated-files workspace. `resume` and `retry-failed`
also launch a detached runner when appropriate. Other controls persist requests;
they do not rely on a chat staying connected. Each start targets one job; a busy processing lock can leave it pending. Check
status/logs and start it again after the owner finishes. There is no automatic
queue-draining or login/boot daemon yet.

Embedded Chroma has one project process owner. Close that project in the GUI
before CLI inference; otherwise it waits for the resource. When using the GUI's
runner, use its Run/resume control. CLI status/events/pause/cancel remain available
for its ledger. Inventory does not open Chroma. A processing lock serializes GUI
workers and detached processing jobs across projects; interactive search/model
ownership still needs further coordination.

## Capacity and recovery contract

Preflight groups the project, generated output and model-cache destinations by
filesystem, sums their estimates, then adds the reserve once per filesystem.
It runs before models and rechecks at every file/stage boundary. It reports:

- FFprobe duration, codecs, rational rates/timebases, orientation/tags, source
  timecode when present, and audio streams/channels.
- Estimated new visual data at 16 KiB/media-second plus 2 MiB/file, speech data
  at 4 KiB/second plus 1 MiB/file, and a 16 MiB project/control allowance.
- Thumbnails at 2 MiB/file; requested CRF proxies estimated at 4 Mbps ×1.25, plus
  one largest concurrent temporary derivative. These are provisional estimates,
  not measured wedding budgets or enforced bitrate/storage quotas.
- Existing generations reduce reported free space. New tracked derived generations
  now support explicit dry-run/verified quarantine/restore/delayed purge; legacy
  untracked data is protected. See [memory/retention](memory-retention.md).

Jobs use **cached models only**. Hugging Face/Whisper loaders receive explicit
local-only/cache options; missing YOLO weights do not trigger a job download.
First-run/manual model downloads are a separate UI path. Selecting a cache does
not migrate downloads or move the existing root-level YOLO weight.

About 8.2 GiB was free internally during verification. The default 20 GiB reserve
correctly blocked that filesystem. Synthetic integration tests used a temporary
64 MiB reserve for a few-second fixture; that is not a wedding-processing budget.
Choose storage/headroom and measure a representative sample before a large run.

The additive `_cyne_db/jobs.sqlite3` ledger uses WAL, full synchronous commits,
stable root/relative asset IDs, source size/mtime signatures, settings snapshots,
attempts, leases, heartbeats and monotonic events. `.cyne`, settings and existing
metadata/vector formats are preserved. Canonical paths validate containment;
existing metadata path aliases are retained instead of silently re-keyed.

Completed file/stages are not rerun within the job. Publication writes a job-item
checkpoint with its vector-generation pointer in the **same metadata transaction**.
A crash between publication and ledger completion is reconciled from that stamp;
cleared/superseded generations cannot masquerade as the committed work. Stale
runners cannot renew/commit after lease expiry. The OS processing lock also blocks
a second local owner while an older process still lives.

After process death, wait for the 15-second lease to expire, then run/resume the
same ID. An unfinished stage restarts from its beginning; this does not resume at
an arbitrary frame or speech segment. Missing drives and low capacity retain
pending work in `waiting_media` / `waiting_capacity`; another project process can
produce `waiting_resource`. Reconnect/restore headroom, then resume. Corrupt inputs
fail individually. Source changes prevent publication and require a new scope.

ETA stays null. Unique fully-completed asset media seconds and completed *stage*
media seconds are separate fields, rather than counting three stages as three
different clips. Bounded clip buffers/windowed speech and recoverable retention
now have [their own contract](memory-retention.md). Physical power-loss/filesystem
fault acceptance, real long-media quality/peaks, physical compaction and explicit data migration
and a representative 800 GB trial remain open in [buildplan.md](../buildplan.md).

## Checks

Run tests separately from the search suite's global dependency stubs:

```bash
source scripts/macos_env.sh  # bash
.venv/bin/python -m unittest tests.test_workspace_jobs -q
.venv/bin/python -m tests.durable_runtime_smoke
.venv/bin/python -m tests.workspace_gui_smoke
```

All fixtures are disposable synthetic media/projects. The native GUI test uses
a small publication adapter for its configured visual/speech queue; the separate
CLI test runs real cached CLIP/BLIP/YOLO/Whisper algorithms and validates old data,
new workspace derivatives and unchanged source/project-file hashes.
