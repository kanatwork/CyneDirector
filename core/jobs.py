"""Versioned, additive job ledger. No Qt, models, or legacy database imports."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from core.workspace import STAGES, Workspace, WorkspaceError


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JobConflict(RuntimeError):
    pass


class JobStore:
    def __init__(self, project, clock=time.time):
        self.project = Path(project).resolve(strict=True)
        folder = self.project / "_cyne_db"
        if folder.is_symlink():
            raise WorkspaceError("unsafe_destination", "Job ledger cannot use a symlinked project database directory")
        if not (folder / "jobs.sqlite3").exists() and not Workspace.path(self.project).is_file():
            raise WorkspaceError("configuration", "Configure Workspace & Jobs before creating a job ledger")
        folder.mkdir(exist_ok=True)
        self.path, self.clock = folder / "jobs.sqlite3", clock
        if self.path.is_symlink():
            raise WorkspaceError("unsafe_destination", "Job ledger must be a separate regular file")
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise JobConflict("Unsupported job schema; ledger left unchanged")
            db.executescript("""
              CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, desired TEXT NOT NULL DEFAULT 'running',
                lease_owner TEXT, lease_until REAL, heartbeat REAL, created REAL, updated REAL, error TEXT);
              CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY, root_id TEXT NOT NULL, relative_path TEXT NOT NULL,
                original_path TEXT NOT NULL, UNIQUE(root_id, relative_path));
              CREATE TABLE IF NOT EXISTS job_items (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                asset_id TEXT NOT NULL REFERENCES assets(id), stage TEXT NOT NULL, ordinal INTEGER,
                signature TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                result TEXT, error TEXT, elapsed REAL NOT NULL DEFAULT 0, UNIQUE(job_id, asset_id, stage));
              CREATE TABLE IF NOT EXISTS job_events (
                cursor INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                item_id TEXT, timestamp REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS idx_items_job ON job_items(job_id, ordinal);
              CREATE INDEX IF NOT EXISTS idx_events_job ON job_events(job_id, cursor);
              PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, job_id, kind, detail, item_id=None):
        db.execute("INSERT INTO job_events(job_id,item_id,timestamp,kind,detail) VALUES(?,?,?,?,?)",
                   (job_id, item_id, self.clock(), kind, encoded(detail)))

    def submit(self, files, stages, settings=None, request_key=None, tasks=None):
        from core.workspace import configuration_lock
        with configuration_lock(self.project):
            return self._submit_owned(files,stages,settings,request_key,tasks)

    def _submit_owned(self, files, stages, settings=None, request_key=None, tasks=None):
        workspace = Workspace.load(self.project)
        stages = list(dict.fromkeys(stages))
        if not stages or set(stages) - set(STAGES):
            raise ValueError("Select inventory, index_visuals and/or transcribe_audio")
        unique = {}
        for source in files:
            asset = workspace.asset(source)
            unique.setdefault((asset["root_id"], asset["relative_path"]), asset)
        # Preserve legacy metadata keys, including /var vs /private/var aliases.
        # Canonical paths establish containment; they must not silently re-key data.
        aliases = {}
        legacy = self.project / "_cyne_db" / "metadata.db"
        if legacy.exists():
            with sqlite3.connect(legacy.as_uri()+"?mode=ro", uri=True) as db:
                for row in db.execute("SELECT video_path FROM video_metadata"):
                    aliases.setdefault(os.path.realpath(row[0]), row[0])
        with self.connection() as db:
            known = {(r["root_id"], r["relative_path"]): r["original_path"] for r in db.execute("SELECT * FROM assets")}
        for key, asset in unique.items():
            asset["path"] = known.get(key, aliases.get(os.path.realpath(asset["path"]), asset["path"]))
        assets = sorted(unique.values(), key=lambda a: a["path"])
        if not assets:
            raise ValueError("No files selected")
        # Snapshot only processing options; do not copy API keys into the ledger.
        allowed = {"mode", "device", "whisper_model", "blip_variant", "batch_size", "keyframe_interval",
                   "generate_thumbnails", "generate_proxies", "language_preference",
                   "processing_memory_mib", "speech_chunk_seconds"}
        from core.settings_manager import DEFAULTS
        snapshot = dict(DEFAULTS, mode="speed")
        settings_file = self.project / "_cyne_db" / "settings.json"
        if settings_file.exists():
            stored = json.loads(settings_file.read_text())
            if not isinstance(stored, dict):
                raise ValueError("Project settings must be an object before submitting a job")
            snapshot.update(stored)
        snapshot.update(settings or {})
        settings = {k: v for k, v in snapshot.items() if k in allowed}
        from core.memory_budget import MemoryPolicy
        MemoryPolicy.from_settings(settings)
        if settings.get("mode", "speed") not in ("speed", "accuracy"):
            raise ValueError("Invalid processing mode")
        scope = {stage: {a["path"] for a in assets} for stage in stages}
        if tasks is not None:
            scope = {}
            for stage in stages:
                scope[stage] = set()
                for path in tasks.get(stage, []):
                    asset = workspace.asset(path)
                    key = (asset["root_id"], asset["relative_path"])
                    if key not in unique:
                        raise ValueError("Task source is outside this job")
                    scope[stage].add(unique[key]["path"])
            if any(not paths or not paths <= {a["path"] for a in assets} for paths in scope.values()):
                raise ValueError("Every stage needs a nonempty subset of the job's assets")
        # Physical paths can change without changing the request's source identity.
        assets=[{k:v for k,v in asset.items() if k!="resolved_path"} for asset in assets]
        payload = encoded({"workspace_id": workspace.data["id"], "assets": assets, "stages": stages, "settings": settings,
                           "tasks": {stage: sorted(paths) for stage, paths in scope.items()}})
        request_key = request_key or hashlib.sha256(payload.encode()).hexdigest()
        now, job_id = self.clock(), uuid.uuid4().hex
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT id,payload FROM jobs WHERE request_key=?", (request_key,)).fetchone()
            if prior:
                if prior["payload"] != payload:
                    raise JobConflict("Request key already belongs to a different scope/settings snapshot")
                return prior["id"]
            db.execute("INSERT INTO jobs(id,request_key,payload,state,created,updated) VALUES(?,?,?,'pending',?,?)",
                       (job_id, request_key, payload, now, now))
            ordinal = 0
            for asset in assets:
                asset_id = hashlib.sha256(encoded([asset["root_id"], asset["relative_path"]]).encode()).hexdigest()
                db.execute("INSERT OR IGNORE INTO assets VALUES(?,?,?,?)", (asset_id, asset["root_id"], asset["relative_path"], asset["path"]))
                for stage in stages:
                    if asset["path"] not in scope[stage]:
                        continue
                    db.execute("INSERT INTO job_items(id,job_id,asset_id,stage,ordinal,signature) VALUES(?,?,?,?,?,?)",
                               (uuid.uuid4().hex, job_id, asset_id, stage, ordinal, encoded(asset["signature"])))
                    ordinal += 1
            self.event(db, job_id, "submitted", {"items": ordinal})
        return job_id

    def status(self, job_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown job: {job_id}")
            result = dict(row)
            result["payload"] = json.loads(result["payload"])
            items = [dict(r) for r in db.execute("""SELECT i.*,a.original_path AS path,a.root_id,a.relative_path
                        FROM job_items i JOIN assets a ON a.id=i.asset_id WHERE i.job_id=? ORDER BY ordinal""", (job_id,))]
            counts = {}
            for item in items:
                item["signature"] = json.loads(item["signature"])
                item["result"] = json.loads(item["result"]) if item["result"] else None
                counts[item["state"]] = counts.get(item["state"], 0) + 1
            workspace=Workspace.load(self.project,check=False)
            result["workspace_revision"]=workspace.data.get("revision",0)
            for item in items:
                try: item["resolved_path"]=workspace.resolve_source(item["path"])
                except (OSError,WorkspaceError) as exc:
                    item["resolved_path"]=None;item["location_error"]=str(exc)
            result["items"], result["counts"], result["total"] = items, counts, len(items)
            result["elapsed_seconds"] = sum(i["elapsed"] for i in items)
            result["completed_stage_media_seconds"] = sum((i["result"] or {}).get("duration", 0) for i in items if i["state"] == "completed")
            by_asset = {}
            for item in items:
                by_asset.setdefault(item["asset_id"], []).append(item)
            result["completed_media_seconds"] = sum(max((i["result"] or {}).get("duration", 0) for i in group)
                    for group in by_asset.values() if all(i["state"] == "completed" for i in group))
            result["eta_seconds"] = None  # No fabricated percentage-derived ETA.
            result["runner_live"] = bool(row["lease_owner"] and (row["lease_until"] or 0) > self.clock())
            if row["lease_owner"] and not result["runner_live"]:
                result["persisted_state"], result["state"] = result["state"], "interrupted"
            current = next((i for i in items if i["state"] == "running"), None)
            result["current_file"] = current["path"] if current else None
            result["current_stage"] = current["stage"] if current else None
            return result

    def list_jobs(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT id,state,desired,created,updated,error FROM jobs ORDER BY created DESC")]

    def events(self, job_id, after=0, limit=200):
        self.status(job_id)
        with self.connection() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM job_events WHERE job_id=? AND cursor>? ORDER BY cursor LIMIT ?",
                                               (job_id, after, max(1, min(limit, 1000))))]
        for row in rows:
            row["detail"] = json.loads(row["detail"])
        return rows

    def control(self, job_id, action):
        if action not in ("pause", "resume", "cancel", "retry_failed"):
            raise ValueError("Unknown job control")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            active = row["lease_owner"] is not None and (row["lease_until"] or 0) > self.clock()
            if action == "retry_failed" and active:
                raise JobConflict("Stop the current attempt before retrying failed items")
            if action == "retry_failed":
                db.execute("UPDATE job_items SET state='pending',error=NULL WHERE job_id=? AND state IN ('failed','cancelled')", (job_id,))
                desired, state = "running", "pending"
            elif action == "resume":
                if row["state"] in ("completed", "failed", "cancelled"):
                    raise JobConflict("Use retry_failed for a terminal job")
                desired, state = "running", "running" if active else "pending"
            elif action == "cancel":
                desired, state = "cancelled", "cancelling" if active else "cancelled"
                db.execute("UPDATE job_items SET state='cancelled' WHERE job_id=? AND state='pending'", (job_id,))
                if not active:
                    db.execute("UPDATE job_items SET state='cancelled' WHERE job_id=? AND state='running'", (job_id,))
            else:
                if row["state"] in ("completed", "failed", "cancelled"):
                    raise JobConflict("Job already ended")
                desired, state = "paused", "pausing" if active else "paused"
            db.execute("UPDATE jobs SET desired=?,state=?,updated=?,error=NULL WHERE id=?", (desired, state, self.clock(), job_id))
            self.event(db, job_id, action, {"boundary": "file/stage; pause finishes current stage, cancel prevents publication"})

    def claim(self, job_id, owner, ttl=15):
        now = self.clock()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["lease_owner"] and (row["lease_until"] or 0) > now:
                raise JobConflict("Job already has a live runner")
            if row["state"] in ("completed", "failed", "cancelled") or row["desired"] != "running":
                return False
            interrupted = db.execute("UPDATE job_items SET state='pending',error='Interrupted; stage will reconcile/retry' WHERE job_id=? AND state='running'", (job_id,)).rowcount
            if interrupted:
                self.event(db, job_id, "interrupted", {"requeued": interrupted})
            db.execute("UPDATE jobs SET state='running',lease_owner=?,lease_until=?,heartbeat=?,updated=?,error=NULL WHERE id=?",
                       (owner, now+ttl, now, now, job_id))
            self.event(db, job_id, "claimed", {"owner": owner, "pid": os.getpid()})
        return True

    def heartbeat(self, job_id, owner, ttl=15):
        with self.connection() as db:
            now = self.clock()
            updated = db.execute("UPDATE jobs SET heartbeat=?,lease_until=?,updated=? WHERE id=? AND lease_owner=? AND lease_until>?",
                                 (now, now+ttl, now, job_id, owner, now)).rowcount
            if not updated:
                raise JobConflict("Runner lost its lease")
            return db.execute("SELECT desired FROM jobs WHERE id=?", (job_id,)).fetchone()[0]

    def begin_item(self, job_id, item_id, owner):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, job_id, owner)
            if not db.execute("UPDATE job_items SET state='running',attempts=attempts+1,error=NULL WHERE id=? AND job_id=? AND state='pending'", (item_id, job_id)).rowcount:
                raise JobConflict("Item is not pending")
            self.event(db, job_id, "item_started", {}, item_id)

    def finish_item(self, job_id, item_id, owner, state, result=None, error=None, elapsed=0):
        if state not in ("completed", "failed", "cancelled"):
            raise ValueError(state)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, job_id, owner)
            if not db.execute("UPDATE job_items SET state=?,result=?,error=?,elapsed=elapsed+? WHERE id=? AND job_id=? AND state='running'",
                              (state, encoded(result) if result is not None else None, error, elapsed, item_id, job_id)).rowcount:
                raise JobConflict("Item is not running")
            self.event(db, job_id, "item_"+state, {"error": error, "result": result}, item_id)

    def _owned(self, db, job_id, owner):
        row = db.execute("SELECT lease_owner,lease_until FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row[0] != owner or (row[1] or 0) <= self.clock():
            raise JobConflict("Stale runner cannot write job state")

    def defer_item(self, job_id, item_id, owner, error, elapsed):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, job_id, owner)
            db.execute("UPDATE job_items SET state='pending',error=?,elapsed=elapsed+? WHERE id=? AND job_id=? AND state='running'",
                       (error, elapsed, item_id, job_id))
            self.event(db, job_id, "item_deferred", {"error": error}, item_id)

    def release(self, job_id, owner, state, error=None):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, job_id, owner)
            # A control request arriving at completion wins over the caller's snapshot.
            desired = db.execute("SELECT desired FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
            if desired in ("paused", "cancelled"):
                state = desired
            if state == "cancelled":
                db.execute("UPDATE job_items SET state='cancelled' WHERE job_id=? AND state IN ('pending','running')", (job_id,))
            elif state == "interrupted":
                db.execute("UPDATE job_items SET state='pending' WHERE job_id=? AND state='running'", (job_id,))
            db.execute("UPDATE jobs SET state=?,error=?,lease_owner=NULL,lease_until=NULL,updated=? WHERE id=?", (state, error, self.clock(), job_id))
            self.event(db, job_id, state, {"error": error})
