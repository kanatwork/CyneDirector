"""Track the source version independently for each processing stage."""
import os
from contextlib import contextmanager
from contextvars import ContextVar

_workspace = ContextVar("cyne_source_workspace",default=None)


@contextmanager
def source_locations(workspace):
    token=_workspace.set(workspace)
    try: yield
    finally: _workspace.reset(token)


def media_path(path,project=None):
    """Resolve IO only; stored source keys never change with an SSD mount."""
    workspace=_workspace.get()
    if project is not None:
        from core.workspace import Workspace
        if Workspace.path(project).exists(): workspace=Workspace.load(project,check=False)
    return workspace.resolve_source(path) if workspace else os.fspath(path)


def media_available(path,project=None):
    try: return os.path.isfile(media_path(path,project))
    except (OSError,RuntimeError): return False


def source_signature(path):
    try:
        stat = os.stat(media_path(path))
        return [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return None


def needs_processing(path, metadata, stage):
    signature = source_signature(path)
    # Legacy shared last_scanned cannot establish which stage processed a file.
    # Reprocess once to establish an independent version for that stage.
    return signature is None or signature != metadata.get(f"{stage}_source_signature")
