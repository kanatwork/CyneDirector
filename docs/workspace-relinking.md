# Safe SSD relinking and workspace updates

Use this when the original-media directory appears at a new mount path, or when
you want future generated files/models to use another existing directory. This
does not move/copy footage, relocate the project database, migrate model downloads,
or rewrite `.cyne`, metadata/vector source keys, job payloads or old derivatives.

## Native Mac workflow

1. Finish or pause active processing. Open **File → Workspace & Jobs…**.
2. Choose the original-media root under **Relink one root**, then choose its
   existing folder at the new location. Leave this blank for destination-only updates.
3. Set **Generated files**, **Model cache**, or **Free-space reserve** as needed.
   These destinations must already exist and stay separate from original media.
4. Click **Preview workspace update**. Verification runs in a background thread.
   Review the changes displayed, then click **Apply reviewed workspace update**.
5. Explicit jobs and playback now resolve the new location. Reopen the project
   to restart automatic watching; the existing watcher is stopped after GUI apply.

Closing or pressing Escape during verification requests cancellation and waits for the worker to
retire. Cancellation before commit leaves configuration unchanged. A replacement
directory can require full-file hashing and take substantial time; the GUI stays
responsive. Preview/apply are explicit actions and never start an 800 GB scan or
inference job automatically.

The media tree keeps its original source keys/folder labels. Jobs expose both
`path` (stored identity) and `resolved_path` (current physical file), plus workspace
revision and any location error. Offline files remain listed/checked and survive
project saves. Existing custom `.cyne` fields are retained during explicit Save.
Playback, technical metadata, thumbnails, reveal/drag and processing use resolved
media locations; new imports at a relinked path reuse existing keys.

## Local JSON commands

Run from this checkout. Commands work with an existing configured project and
can inspect its pins even when its media is offline:

```bash
./cyne.command --project "/path/to/project" workspace inspect
./cyne.command --project "/path/to/project" workspace plan \
  --relink ROOT_ID "/Volumes/Wedding 1/Originals"
./cyne.command --project "/path/to/project" workspace status CHANGE_ID
./cyne.command --project "/path/to/project" workspace apply CHANGE_ID
```

Find `ROOT_ID` in `workspace inspect`; do not infer it from a folder name. A plan
contains the exact proposed configuration, affected roots, verification method,
known-source count, signatures/hashes and checksums. Planning writes only a new
inspection journal. Apply revalidates that saved plan and commits one complete
configuration replacement. Repeating the same apply returns `applied` without
repeating a migration. A later update makes an older plan `superseded`.

Destination/reserve changes and additional media roots can be combined with a
relink, or planned independently:

```bash
./cyne.command --project "/path/to/project" workspace plan \
  --output "/Volumes/EditWorkspace/CyneGenerated" \
  --model-cache "/Volumes/EditWorkspace/Models" --reserve-gib 20
./cyne.command --project "/path/to/project" workspace plan \
  --add-media-root "/Volumes/Wedding/Camera B"
```

`--relink ROOT_ID FOLDER`, `--seal-root ROOT_ID`, and `--add-media-root FOLDER`
can be repeated. Removing roots, relocating the project/database, copying media,
and moving existing derivative/model files are intentionally separate operations.
An added root gets a new ID; an existing root keeps its ID on relink. Overlapping
root aliases that could reassign assets are rejected. A configuration created by
an older build with overlapping media roots needs explicit remediation before updates.

## How a relink is verified

For the same directory on the same volume, volume UUID + inode (or device + inode
where UUID is unavailable) establish identity. Known media must still have the
same size/mtime signatures. Relative camera paths must match exactly: another
`C0001.MP4` in a different folder never substitutes for a missing source.

A different directory/drive requires full SHA-256 verification of **every known
source**, in bounded 4 MiB reads. Size/mtime alone, even with identical basenames,
is not accepted. If both roots are online, the app compares the pinned original
and candidate and rechecks them on apply. A copied source must preserve its
original size/mtime as well as content, so existing job/stage signatures remain valid.
Files that changed revision require a new analysis rather than a relink shortcut.

To prepare for a replacement/backup drive while the original is still online:

```bash
./cyne.command --project "/path/to/project" workspace plan --seal-root ROOT_ID
./cyne.command --project "/path/to/project" workspace apply CHANGE_ID
```

The GUI's **Record content hashes** does the same for the selected root. These
hashes cover project-known sources from the asset ledger, metadata and top-level
`.cyne` files, including preserved legacy aliases. This is not a full SSD backup
manifest: unknown files, nested project files and unrelated folders are not enrolled.
Hashing a fully registered 800 GB library reads those bytes and may take a long time.

An offline original with a different-identity candidate needs a previously sealed
hash for every known source. Without it, verification fails; reconnect the original
first. An empty/unregistered root cannot prove that a different directory is the
same media; register it separately. Conflicting existing metadata keys are reported
and left intact rather than merged. Source changes, missing relative files, symlink
escapes, changed/replaced target directories, corrupt journals and stale plans fail
before configuration commit. Historical aliases always resolve through the pinned
current root, even if a wrong file later appears at the former mount path.

## Configuration and recovery contract

Workspace ID, root IDs and root-relative asset IDs remain stable. Existing immutable
job payloads/settings, stage attempts/checkpoints, vector generations, source keys,
artifact references and custom project fields remain in place. A paused job resumes
only unfinished stages; publication-before-ledger reconciliation still works after
relinking. Submitting the same scope at its new path deduplicates to the existing job.

New output/model paths affect subsequent execution. Existing derivatives are not
moved; old output directories remain pinned in `output_history`. Existing artifacts
can still be inspected, quarantined and restored when their original pinned output
location is online. Offline historical output does not block new output writes.
Derivative-directory relocation to a new mount path is not automated: reconnect its
old location to use/maintain those old artifacts. Original-media relinking remains
available independently. No cache migration or physical SQLite/HNSW shrink is performed.

Unapplied retention plans become stale after a workspace revision. Make a fresh
retention plan; already quarantined copies remain restorable across destination
updates. Restore/purge recheck the corresponding historical output pin and hashes.
See the [retention contract](memory-retention.md).

Updates use the inference ownership lock plus a configuration lock shared with job
submission. A worker executing a stage blocks updates. Active runners finish under
one configuration; existing queued jobs resolve the current configuration when
they next run, while retaining their frozen processing settings. Source membership
changes between plan and apply invalidate the plan. Unchanged offline roots may
remain configured; normal processing preflight still requires its configured roots.

The sole commit point is fsynced temporary JSON → atomic replace of
`_cyne_db/workspace.json`, followed by a parent-directory fsync where supported.
Checksummed journals live in `_cyne_db/workspace-changes/`. Process death before
replace leaves the old configuration; death after replace is recognized as applied.
Use `workspace status CHANGE_ID`, then retry apply if it still says `planned`.
There is no multi-database path rewrite to recover halfway. Earlier generations of
the app do not implement the new resolver; use this build after relinking.

Default capacity reserve remains **20 GiB**. Selecting a new destination does not
bypass preflight or create an absent SSD mount. Tests lower reserve only on small,
disposable fixtures. Physical exFAT/APFS unplug/remount, full disk, system power-loss,
real backup-copy acceptance and the representative wedding pilot remain required.
See the [verification report](audits/2026-11-24-workspace-relinking.md).
