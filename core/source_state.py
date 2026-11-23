"""Track the source version independently for each processing stage."""
import os


def source_signature(path):
    try:
        stat = os.stat(path)
        return [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return None


def needs_processing(path, metadata, stage):
    signature = source_signature(path)
    # Legacy shared last_scanned cannot establish which stage processed a file.
    # Reprocess once to establish an independent version for that stage.
    return signature is None or signature != metadata.get(f"{stage}_source_signature")
