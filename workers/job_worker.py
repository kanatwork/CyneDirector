"""Qt adapter; durable execution and state live in core.job_runner/core.jobs."""
from PyQt6.QtCore import QThread, pyqtSignal
from core.job_runner import JobRunner
from core.jobs import JobStore


class DurableJobWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

    def __init__(self, project, job_id):
        super().__init__()
        self.project, self.job_id = project, job_id
        status = JobStore(project).status(job_id)
        self.file_paths = [a["path"] for a in status["payload"]["assets"]]
        self.is_running, self.errors = True, []

    def stop(self):
        # A window close pauses at a publication boundary; it never clears work.
        store = JobStore(self.project)
        if store.status(self.job_id)["state"] not in ("completed", "failed", "cancelled"):
            store.control(self.job_id, "pause")

    def run(self):
        def update(status):
            done = status["counts"].get("completed", 0)
            self.progress_signal.emit(min(99, int(done*100/max(status["total"], 1))))
            self.log_signal.emit(f"Job {self.job_id[:8]}: {done}/{status['total']} stages; {status['current_stage'] or 'checkpoint'}")
        try:
            result = JobRunner(self.project, on_status=update).run(self.job_id)
            if result["state"] == "completed":
                self.progress_signal.emit(100)
            else:
                self.errors.append(f"Job {result['state']}: {result.get('error') or 'see Workspace & Jobs'}")
        except Exception as exc:
            self.errors.append(str(exc))
        for error in self.errors:
            self.log_signal.emit(error)
