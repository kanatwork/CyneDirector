"""Persistent file/stage checkpoints, lease fencing, and explicit wait states."""
import threading
import time
import uuid

from core.jobs import JobConflict, JobStore
from core.processing_lock import ProcessingLock, ProcessingBusy
from core.source_state import source_signature
from core.workspace import Workspace, WorkspaceError


class JobRunner:
    def __init__(self, project, processor_factory=None, preflight=None, heartbeat_interval=2, lease_seconds=15, on_status=None):
        self.project = project
        self.store = JobStore(project)
        self.processor_factory = processor_factory
        self.preflight = preflight
        self.heartbeat_interval = heartbeat_interval
        self.lease_seconds, self.on_status = lease_seconds, on_status or (lambda status: None)
        if not 0 < heartbeat_interval < lease_seconds / 2:
            raise ValueError("Heartbeat interval must be less than half the lease")

    def run(self, job_id):
        # OS lock outlives a lease and is released by kernel on process death.
        # A stalled/partitioned heartbeat cannot admit another model publisher.
        with ProcessingLock():
            return self._run_owned(job_id)

    def _run_owned(self, job_id):
        owner = uuid.uuid4().hex
        if not self.store.claim(job_id, owner, self.lease_seconds):
            return self.store.status(job_id)
        stop, lease_lost, cancelled = threading.Event(), threading.Event(), threading.Event()

        def beat():
            while not stop.wait(self.heartbeat_interval):
                try:
                    if self.store.heartbeat(job_id, owner, self.lease_seconds) == "cancelled":
                        cancelled.set()
                except Exception:
                    lease_lost.set()
                    return

        thread = threading.Thread(target=beat, name="cyne-job-heartbeat", daemon=True)
        thread.start()
        state, error, processor = "failed", None, None
        try:
            workspace = Workspace.load(self.project)
            status = self.store.status(job_id)
            payload = status["payload"]
            if payload["workspace_id"] != workspace.data["id"]:
                raise WorkspaceError("configuration", "Job belongs to another workspace")
            factory = self.processor_factory
            if factory is None:
                from core.processing import AppProcessor
                factory = AppProcessor
            processor = factory(self.project, workspace, payload["settings"])
            # Only unfinished work needs new capacity. Completed generations stay.
            pending = [i for i in status["items"] if i["state"] == "pending"]
            from core.workspace import probe
            metadata_cache = {}
            def cached_probe(path):
                if path not in metadata_cache:
                    metadata_cache[path] = probe(workspace.resolve_source(path))
                return metadata_cache[path]

            def checked(files, stages, settings):
                return workspace.preflight(files, stages, settings, probe_fn=cached_probe)

            check = self.preflight or checked
            if pending:
                report = check([i["path"] for i in pending], list(dict.fromkeys(i["stage"] for i in pending)), payload["settings"])
                with self.store.connection() as db:
                    self.store.event(db, job_id, "preflight", report)
                if not report.get("capacity_ok", report["ok"]):
                    raise WorkspaceError("waiting_capacity", "Reserve plus estimated outputs exceeds free destination capacity")
            bad_inputs = {(e["path"], stage): e["error"] for e in report.get("errors", [])
                          for stage in e.get("stages", payload["stages"])} if pending else {}
            for item_index, item in enumerate(pending):
                desired = self.store.heartbeat(job_id, owner, self.lease_seconds)
                if desired != "running":
                    state = desired
                    break
                workspace.check_locations()
                workspace.asset(item["path"])
                if (item["path"], item["stage"]) in bad_inputs:
                    self.store.begin_item(job_id, item["id"], owner)
                    self.store.finish_item(job_id, item["id"], owner, "failed", error=bad_inputs[(item["path"], item["stage"])])
                    continue
                if workspace.asset(item["path"])["signature"] != item["signature"]:
                    self.store.begin_item(job_id, item["id"], owner)
                    self.store.finish_item(job_id, item["id"], owner, "failed", error="source_changed: submit a new job for the new source revision")
                    continue
                # Recheck headroom at each boundary, after preceding outputs exist.
                report = check([item["path"]], [item["stage"]], payload["settings"])
                if not report["ok"]:
                    raise WorkspaceError("waiting_capacity", "Destination headroom fell below reserve")
                self.store.begin_item(job_id, item["id"], owner)
                self.on_status(self.store.status(job_id))
                started = time.monotonic()

                def allowed():
                    if lease_lost.is_set() or cancelled.is_set():
                        return False
                    try:
                        valid = self.store.heartbeat(job_id, owner, self.lease_seconds) != "cancelled"
                        workspace.check_locations()
                        return valid and workspace.asset(item["path"])["signature"] == item["signature"]
                    except Exception:
                        return False

                def log(message):
                    with self.store.connection() as db:
                        self.store.event(db, job_id, "log", {"message": message}, item["id"])

                try:
                    result = processor.reconcile(item)
                    if result is None:
                        result = processor.execute(item, allowed, log)
                    if not allowed():
                        raise RuntimeError("Cancelled, media missing, or lease lost")
                    if workspace.asset(item["path"])["signature"] != item["signature"]:
                        raise RuntimeError("source_changed during stage")
                    self.store.finish_item(job_id, item["id"], owner, "completed", result=result,
                                           elapsed=time.monotonic()-started)
                    self.on_status(self.store.status(job_id))
                except Exception as exc:
                    if isinstance(exc, ProcessingBusy):
                        self.store.defer_item(job_id, item["id"], owner, str(exc), time.monotonic()-started)
                        raise WorkspaceError("waiting_resource", str(exc)) from exc
                    try:
                        workspace.check_locations()
                    except WorkspaceError as media_error:
                        if media_error.code == "waiting_media":
                            self.store.defer_item(job_id, item["id"], owner, str(media_error), time.monotonic()-started)
                            raise media_error
                        raise
                    desired = self.store.heartbeat(job_id, owner, self.lease_seconds)
                    self.store.finish_item(job_id, item["id"], owner,
                                           "cancelled" if desired == "cancelled" else "failed",
                                           error=str(exc), elapsed=time.monotonic()-started)
                    if desired == "cancelled":
                        state = "cancelled"
                        break
            else:
                counts = self.store.status(job_id)["counts"]
                state = "failed" if counts.get("failed") or counts.get("cancelled") else "completed"
        except WorkspaceError as exc:
            state = exc.code if exc.code in ("waiting_media", "waiting_capacity", "waiting_resource") else "failed"
            error = f"{exc.code}: {exc}"
        except KeyboardInterrupt:
            state, error = "interrupted", "Runner interrupted; resume from the last committed file/stage"
        except Exception as exc:
            state, error = "failed", str(exc)
        finally:
            try:
                if processor is not None and hasattr(processor, "close"):
                    processor.close()
            except Exception as exc:
                state, error = "failed", f"Processor cleanup failed: {exc}"
            finally:
                stop.set(); thread.join()
            if not lease_lost.is_set():
                self.store.release(job_id, owner, state, error)
        return self.store.status(job_id)
