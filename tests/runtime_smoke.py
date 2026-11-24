"""Optional integration check using the installed app dependencies and FFmpeg.

Run from the project root: python -m tests.runtime_smoke
Uses synthetic footage, an offscreen Qt window, and real SQLite/Chroma storage.
AI workers are replaced with short QThreads; no models are downloaded or run.
"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["ANONYMIZED_TELEMETRY"] = "False"

import main  # Apply the app's Windows DLL bootstrap before importing Qt.
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import faulthandler
from unittest.mock import patch
from PyQt6.QtCore import QEventLoop, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication
from core.database import Database
from core.proxy_generator import generate_thumbnail, generate_proxy
from core.settings_manager import SettingsManager
from core.source_state import source_signature
from core.workflow_manager import OperationStatus, OperationType
from gui.main_window import MainWindow


class VisualWorker(QThread):
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    summary_signal = pyqtSignal(str, str)

    def __init__(self, files, project_path, mode="speed"):
        super().__init__()
        self.file_paths = files
        self.is_running = True
        self.errors = []

    def run(self):
        for path in self.file_paths:
            Database().save_tags(path, ["wedding"], "Synthetic wedding test")
            self.summary_signal.emit(path, "Synthetic wedding test")
        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False


class AudioWorker(VisualWorker):
    file_finished_signal = pyqtSignal(str)

    def run(self):
        for path in self.file_paths:
            Database().save_transcript(path, [{"start": 0, "end": 1, "text": "I do!"}],
                                       source_signature=source_signature(path))
            self.file_finished_signal.emit(path)
        self.progress_signal.emit(100)
        self.finished_signal.emit()


class BlockingWorker(VisualWorker):
    def run(self):
        while self.is_running:
            self.msleep(10)


def run():
    faulthandler.dump_traceback_later(90, exit=True)
    app = QApplication.instance() or QApplication([])
    exceptions = []
    def report_exception(kind, value, tb):
        exceptions.append(value)
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = report_exception
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        project = Path(directory)
        settings = SettingsManager(directory)
        settings.set("auto_index_on_change", False)
        settings.set("device", "cpu")
        settings.save()
        (project / "review.cyne").write_text(json.dumps({"files": []}), encoding="utf-8")
        sources = []
        print("Generating two synthetic clips with identical camera filenames...", flush=True)
        for camera, color in (("camera_a", "red"), ("camera_b", "blue")):
            folder = project / camera
            folder.mkdir()
            path = folder / "C0001.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            f"color={color}:s=320x180:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
                           check=True, capture_output=True, timeout=30,
                           creationflags=0x08000000 if os.name == "nt" else 0)
            sources.append(str(path))
        thumbnails = [generate_thumbnail(path, str(project / "thumbs")) for path in sources]
        proxies = [generate_proxy(path, str(project / "proxies"), resolution=180) for path in sources]
        assert all(thumbnails) and len(set(thumbnails)) == 2, thumbnails
        assert all(proxies) and len(set(proxies)) == 2, proxies
        print("FFmpeg thumbnails and proxies: passed", flush=True)

        from core.ai_models import AIBackend
        import torch
        with patch.object(AIBackend, "_detect_best_device", return_value=("cpu", torch.float32)):
            window = MainWindow(directory, "review")
        window.tree.add_files_flat(sources)
        db = window.db
        db.visuals.upsert(ids=["old-frame"], embeddings=[[1.0, 0.0, 0.0]],
                          metadatas=[{"source": sources[0], "timestamp": 10.0}])
        db.clear_visual_embeddings(sources[0])
        assert db.visuals.count() == 0
        db.transcripts.upsert(ids=["old-dialogue"], embeddings=[[1.0, 0.0, 0.0]],
                              metadatas=[{"source": sources[0], "text": "old vows"}])
        db.save_transcript(sources[0], [{"start": 0, "end": 1, "text": "new vows"}])
        assert db.transcripts.count() == 0
        print("App window and real database vector cleanup: passed", flush=True)

        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        window.workflow_manager.workflow_finished.connect(loop.quit)
        with patch("workers.indexer.IndexerWorker", VisualWorker), patch("workers.transcriber.TranscriberWorker", AudioWorker):
            for operation in (OperationType.INDEX_VISUALS, OperationType.TRANSCRIBE_AUDIO):
                window.workflow_manager.add_operation(operation, sources, smart_filter=False)
            timer.start(15000)
            window.start_workflow()
            loop.exec()
        print("Workflow state:", [(op.op_type.value, op.status.value, op.error_message)
                                  for op in window.workflow_manager.queue], flush=True)
        assert timer.isActive(), "Workflow did not finish within 15 seconds"
        timer.stop()
        assert not exceptions, exceptions
        assert window.worker is None
        assert all(op.status == OperationStatus.COMPLETED for op in window.workflow_manager.queue)
        assert all(db.get_video_metadata(path).get("transcript") for path in sources)
        for path in sources:
            item = window.tree.item_map[window.tree.norm(path)]
            assert item.text(8) == "--", item.text(8)
            assert item.text(9) == "Synthetic wedding test", item.text(9)
            assert item.text(5) == item.text(6) == "✅"
        # Exercise ownership of a real active background thread during close.
        background = BlockingWorker([], directory)
        window.background_indexer.current_worker = background
        window.background_indexer.is_indexing = True
        window.background_indexer.background_timer.start()
        background.start()
        assert background.isRunning()
        window.is_dirty = False
        window.close()
        assert not background.isRunning()
        assert window.background_indexer.current_worker is None
        assert not window.background_indexer.background_timer.isActive()
        db.close()
        app.processEvents()
        assert not exceptions, exceptions
        print("Two-stage workflow and background shutdown with real Qt threads: passed", flush=True)
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    run()
