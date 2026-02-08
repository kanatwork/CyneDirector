# [FILE: workers/file_watcher.py]
# Monitors the project directory for new or modified video files using watchdog.
# Emits Qt signals so the GUI can queue auto-indexing.

import os
import time
import threading
from PyQt6.QtCore import QThread, pyqtSignal
from core.logger import get_logger

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.avi', '.mxf', '.webm'}
DEBOUNCE_SECONDS = 2.0


class FileWatcherWorker(QThread):
    """Watches a project directory for new/modified video files.

    Uses ``watchdog`` for efficient filesystem monitoring.  A 2-second debounce
    timer prevents duplicate signals caused by partial file copies (the OS may
    fire several events while a large file is still being written).
    """

    new_file_signal = pyqtSignal(str)       # absolute path of a new video
    file_modified_signal = pyqtSignal(str)   # absolute path of a modified video

    def __init__(self, watch_path: str):
        super().__init__()
        self.watch_path = watch_path
        self.is_running = True

        # Debounce state: path → timestamp of last event
        self._pending: dict[str, float] = {}
        self._pending_lock = threading.Lock()

    # ── QThread entry ────────────────────────────────────────────────

    def run(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
        except ImportError:
            logger.warning("watchdog is not installed — file watcher disabled")
            return

        worker = self  # closure reference

        class _Handler(FileSystemEventHandler):
            """Forwards relevant filesystem events into the debounce buffer."""

            def on_created(self, event):
                if not event.is_directory:
                    worker._enqueue(event.src_path, is_new=True)

            def on_modified(self, event):
                if not event.is_directory:
                    worker._enqueue(event.src_path, is_new=False)

        observer = Observer()
        observer.schedule(_Handler(), self.watch_path, recursive=True)
        observer.start()
        logger.info(f"File watcher started on {self.watch_path}")

        try:
            while self.is_running:
                self._flush_pending()
                self.msleep(500)  # check every 500 ms
        finally:
            observer.stop()
            observer.join(timeout=3)
            logger.info("File watcher stopped")

    # ── Internal helpers ─────────────────────────────────────────────

    def _is_relevant(self, path: str) -> bool:
        """Return True if *path* is a video file we care about."""
        # Ignore hidden files / dirs
        parts = os.path.normpath(path).split(os.sep)
        for part in parts:
            if part.startswith('.'):
                return False

        # Ignore anything inside _cyne_db/
        if '_cyne_db' in parts:
            return False

        _, ext = os.path.splitext(path)
        return ext.lower() in VIDEO_EXTENSIONS

    def _enqueue(self, path: str, is_new: bool):
        """Record an event; the debounce timer will emit later."""
        if not self._is_relevant(path):
            return
        with self._pending_lock:
            # Store (timestamp, is_new). A 'new' flag beats a 'modified'
            # flag for the same path so we prefer new_file_signal.
            existing = self._pending.get(path)
            if existing is not None:
                _, was_new = existing
                is_new = is_new or was_new  # keep the "new" flag if set
            self._pending[path] = (time.monotonic(), is_new)

    def _flush_pending(self):
        """Emit signals for events whose debounce window has elapsed."""
        now = time.monotonic()
        to_emit: list[tuple[str, bool]] = []

        with self._pending_lock:
            expired_keys = [
                p for p, (ts, _) in self._pending.items()
                if now - ts >= DEBOUNCE_SECONDS
            ]
            for key in expired_keys:
                ts, is_new = self._pending.pop(key)
                to_emit.append((key, is_new))

        for path, is_new in to_emit:
            abs_path = os.path.normpath(os.path.abspath(path))
            if not os.path.isfile(abs_path):
                continue  # file was deleted before debounce elapsed
            if is_new:
                logger.debug(f"File watcher: new file {abs_path}")
                self.new_file_signal.emit(abs_path)
            else:
                logger.debug(f"File watcher: modified file {abs_path}")
                self.file_modified_signal.emit(abs_path)

    # ── Shutdown ─────────────────────────────────────────────────────

    def stop(self):
        self.is_running = False
