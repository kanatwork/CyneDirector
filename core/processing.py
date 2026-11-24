"""Shared serial execution boundary for GUI workers and durable runners.

The ledger/preflight/runner import without Qt or ML. The legacy model algorithm
adapters are imported lazily, and remain the single implementation of inference.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import json
import threading

from core.processing_lock import ProcessingLock, ProcessingBusy
from core.source_state import source_signature
from core.workspace import Workspace, WorkspaceError, probe


@contextmanager
def processing_guard(project, files, stages):
    with ProcessingLock():
        workspace = Workspace.load(project)
        import config
        from core.memory_budget import MemoryPolicy
        policy = MemoryPolicy.from_settings(config._settings.to_dict())
        report = workspace.preflight(files, stages, config._settings.to_dict())
        if report["errors"]:
            raise WorkspaceError("unsupported_media", "; ".join(e["error"] for e in report["errors"]))
        if not report["ok"]:
            raise WorkspaceError("waiting_capacity", "Insufficient destination capacity including reserve and estimated outputs")
        for asset in report["assets"]:
            for stream in asset["metadata"]["streams"]:
                if "index_visuals" in stages and stream.get("codec_type") == "video":
                    policy.dimensions(int(stream.get("width",0)),int(stream.get("height",0)))
        from core.database import Database
        db = Database()
        old = getattr(db._local,"memory_policy",None)
        db._local.memory_policy = policy
        try:
            for path in files:
                db.get_bounded_video_metadata(path,policy)
            from core.source_state import source_locations
            with source_locations(workspace):
                yield workspace
        finally:
            if old is None:
                del db._local.memory_policy
            else:
                db._local.memory_policy = old


def model_load_options():
    """Jobs use explicit local cache locations and forbid surprise downloads."""
    opts = {}
    if os.environ.get("CYNE_JOB_OFFLINE") == "1":
        opts["local_files_only"] = True
        opts["cache_dir"] = str(Path(os.environ["HF_HOME"]) / "hub")
    return opts


def whisper_load_options():
    return {"local_files_only": True, "download_root": str(Path(os.environ["HF_HOME"]) / "hub")} if os.environ.get("CYNE_JOB_OFFLINE") == "1" else {}


class AppProcessor:
    """One asset/stage at a time; completed publications reconcile after a crash."""
    def __init__(self, project, workspace, settings):
        self.project, self.workspace, self.settings = str(project), workspace, settings
        self._environment = None

    def checkpoint(self, item):
        return {"item_id": item["id"], "signature": item["signature"], "settings": self.settings}

    def reconcile(self, item):
        if item["stage"] == "inventory":
            return None
        path = Path(self.project) / "_cyne_db" / "metadata.db"
        if not path.exists():
            return None
        # Avoid opening Chroma/models merely to inspect a committed checkpoint.
        with sqlite3.connect(path.as_uri()+"?mode=ro", uri=True) as db:
            row = db.execute("SELECT json_data FROM video_metadata WHERE video_path=?", (item["path"],)).fetchone()
        meta = json.loads(row[0]) if row else {}
        stage = "visual" if item["stage"] == "index_visuals" else "transcript"
        checkpoint = dict(meta.get(stage+"_job_checkpoint") or {})
        generation = checkpoint.pop("generation", None)
        if (checkpoint == self.checkpoint(item) and generation is not None and generation == meta.get(stage+"_generation")
                and meta.get(stage+"_source_signature") == item["signature"] and self.workspace.asset(item["path"])["signature"] == item["signature"]):
            return {"reconciled": True, "generation": meta.get(stage+"_generation"), "duration": meta.get("duration", 0),
                    "artifacts": {k: meta[k] for k in ("thumbnail_path", "proxy_path") if meta.get(k)}}
        return None

    def execute(self, item, allowed, log):
        if item["stage"] == "inventory":
            return probe(self.workspace.resolve_source(item["path"]))
        self.workspace.check_locations()
        cache = Path(self.workspace.data["destinations"]["models"]["path"])
        if self._environment is None:
            self._environment = {key: os.environ.get(key) for key in ("HF_HOME", "TORCH_HOME", "CYNE_JOB_OFFLINE")}
        os.environ.update(HF_HOME=str(cache), TORCH_HOME=str(cache/"torch"), CYNE_JOB_OFFLINE="1")
        import config
        if not hasattr(self, "_settings_before"):
            self._settings_before = (config._settings, config.USE_BLIP2, config.GENERATE_PROXIES)
        config.load_project_settings(self.project)
        for key, value in self.settings.items():
            config._settings.set(key, value)
        config.USE_BLIP2 = config.get_setting("blip_variant") == "blip-2"
        config.GENERATE_PROXIES = config.get_setting("generate_proxies", False)
        from core.database import Database
        from core.ai_models import AIBackend
        db = Database()
        if db.client is not None and db.project_path and Path(db.project_path).resolve() != self.workspace.project:
            raise ProcessingBusy("A different project owns this app's database; close it before running this job")
        if db.project_path != self.project or db.client is None:
            db.initialize(self.project)
        AIBackend().configure_from_settings()
        if item["stage"] == "index_visuals":
            from workers.indexer import IndexerWorker
            worker = IndexerWorker([item["path"]], self.project, mode=self.settings.get("mode", "speed"))
        else:
            from workers.transcriber import TranscriberWorker
            worker = TranscriberWorker([item["path"]], self.project, mode=self.settings.get("mode", "speed"))
            worker.force_reprocess = True
        worker.log_signal.connect(log)
        # Existing algorithms repeatedly read is_running, and validate it at commit.
        # Publication also checks the runner's live lease/cancellation predicate.
        stop = threading.Event()
        def monitor():
            while not stop.wait(.5):
                if not allowed():
                    worker.stop()
                    return
        monitor_thread = threading.Thread(target=monitor, name="cyne-stage-control", daemon=True)
        monitor_thread.start()
        try:
            with db.publication_context(self.checkpoint(item), allowed):
                worker.run()
        finally:
            stop.set(); monitor_thread.join()
        if worker.errors:
            raise RuntimeError("; ".join(worker.errors))
        if not allowed():
            raise RuntimeError("Cancelled or lease lost before completion")
        committed = self.reconcile(item)
        if committed is None:
            raise RuntimeError("Worker returned without publishing this job checkpoint")
        committed["reconciled"] = False
        return committed

    def close(self):
        try:
            if self._environment is not None:
                from core.ai_models import AIBackend
                AIBackend().unload_models()
        finally:
            for key, value in (self._environment or {}).items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            if hasattr(self, "_settings_before"):
                import config
                config._settings, config.USE_BLIP2, config.GENERATE_PROXIES = self._settings_before
