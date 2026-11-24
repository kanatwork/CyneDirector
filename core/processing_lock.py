"""One local processing owner, shared by GUI workers and detached job runners."""
import os
from pathlib import Path
import tempfile
import threading

_guard = threading.RLock()
_owner = None
_depth = 0
_handle = None


class ProcessingBusy(RuntimeError):
    pass


class ProjectSession:
    """An embedded Chroma project has one process owner, including GUI reads."""
    def __init__(self, path):
        self.handle = open(path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.write(b"0"); self.handle.flush(); self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise ProcessingBusy("Project is open in another CyneDirector process; close it before a CLI inference run") from exc

    def close(self):
        self.handle.close()


class ProcessingLock:
    def __enter__(self):
        global _owner, _depth, _handle
        with _guard:
            owner = (os.getpid(), threading.get_ident())
            if _owner == owner:
                _depth += 1
                return self
            if _owner is not None:
                raise ProcessingBusy("Another local processing worker is active")
            suffix = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
            lock_root = Path(tempfile.gettempdir()) if os.name == "nt" else Path("/tmp")
            handle = open(lock_root / f"cynedirector-inference-{suffix}.lock", "a+b")
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0); handle.write(b"0"); handle.flush(); handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                raise ProcessingBusy("Another CyneDirector process owns inference") from exc
            _owner, _depth, _handle = owner, 1, handle
        return self

    def __exit__(self, *args):
        global _owner, _depth, _handle
        with _guard:
            _depth -= 1
            if _depth == 0:
                _handle.close()  # OS releases the lock on normal exit or process death.
                _owner, _handle = None, None
