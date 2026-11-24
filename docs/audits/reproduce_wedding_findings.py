"""Historical probes for 112388b; NOT a health check of revised source.

Run from any directory: python3 docs/audits/reproduce_wedding_findings.py
Uses actual function bodies extracted from the checkout, with synthetic inputs
and in-memory collaborators. No models, encoders, footage, or app data are used.
Exit 0 means probes executed; consult each finding_observed field for defects.
After fixes, convert the relevant probes into normal regression tests.
"""

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
from collections import defaultdict
from enum import Enum
from types import SimpleNamespace
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class Signal:
    def __init__(self, *args):
        self.callbacks = []
        self.events = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        self.events.append(args)
        for callback in self.callbacks:
            callback(*args)


class Null:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


def node(path, name, cls=None):
    tree = ast.parse((ROOT / path).read_text())
    scope = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls) if cls else tree
    return next(n for n in scope.body if getattr(n, "name", None) == name)


def method(path, cls, name, namespace=None):
    namespace = dict(namespace or {})
    code = ast.Module(body=[node(path, name, cls)], type_ignores=[])
    exec(compile(code, path, "exec"), namespace)
    return namespace[name]


def manager():
    path = "core/workflow_manager.py"
    tree = ast.parse((ROOT / path).read_text())
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    ns = dict(QObject=object, pyqtSignal=Signal, Enum=Enum, List=List,
              Dict=Dict, Optional=Optional,
              Database=lambda: SimpleNamespace(project_path="synthetic"))
    exec(compile(ast.Module(body=classes, type_ignores=[]), path, "exec"), ns)
    return ns["WorkflowManager"]("synthetic"), ns["OperationType"]


def probe_proxy_collision():
    safe_stem = method("core/proxy_generator.py", None, "_safe_stem", dict(Path=Path, re=re))
    names = [safe_stem(p) + "_proxy.mp4" for p in ["/Camera_A/C0001.MP4", "/Camera_B/C0001.MP4"]]
    return dict(id="F01", finding_observed=names[0] == names[1], generated_names=names)


def probe_worker_handoff():
    wm, op = manager()
    running_worker = SimpleNamespace(isRunning=lambda: True, wait=Null().wait)
    label = SimpleNamespace(text=lambda: "Completed: first clip", setText=Null().setText)
    window = SimpleNamespace(worker=SimpleNamespace(isRunning=lambda: False),
                             workflow_manager=wm, status_label=label,
                             status_icon=Null(), progress_bar=Null(),
                             lock_buttons=Null().lock_buttons, mark_dirty=Null().mark_dirty,
                             get_files_to_process=lambda: [], update_preview_panel=Null().update_preview_panel)
    started = []

    def start(kind, paths):
        started.append(kind.value)
        if len(started) == 2:
            window.worker = running_worker

    wm.operation_started.connect(start)
    wm.add_operation(op.INDEX_VISUALS, ["first"], smart_filter=False)
    wm.add_operation(op.TRANSCRIBE_AUDIO, ["first"], smart_filter=False)
    wm.start_workflow()
    finish = method("gui/main_window.py", "MainWindow", "worker_finished", dict(COLORS={"success": "green", "error": "red"}))
    finish(window)
    return dict(id="F02", finding_observed=wm.current_operation is not None and window.worker is None,
                operations_started=started, next_operation_status=wm.current_operation.status.value,
                active_worker_reference_cleared=window.worker is None)


def probe_pause_boundary():
    wm, op = manager()
    wm.add_operation(op.INDEX_VISUALS, ["first"], smart_filter=False)
    wm.add_operation(op.TRANSCRIBE_AUDIO, ["first"], smart_filter=False)
    wm.start_workflow()
    wm.pause_workflow()
    wm.on_operation_finished(op.INDEX_VISUALS, True)
    wm.resume_workflow()
    pending = sum(x.status.value == "pending" for x in wm.queue)
    return dict(id="F03", finding_observed=wm.is_running and wm.current_operation is None and pending > 0,
                workflow_running=wm.is_running, current_operation_missing=wm.current_operation is None,
                pending_operations=pending)


def probe_stage_freshness():
    wm, op = manager()
    with tempfile.TemporaryDirectory(prefix="cyne-stage-probe-") as tmp:
        clip = Path(tmp) / "modified.MP4"
        clip.touch()
        # Existing transcript belongs to an earlier file version; visuals just
        # completed and overwrote the one shared last_scanned field.
        meta = {"tags": ["new visuals"], "transcript": [{"text": "old speech"}],
                "last_scanned": clip.stat().st_mtime}
        wm.db = SimpleNamespace(get_video_metadata=lambda path: meta)
        scheduled = wm._filter_files_needing_operation(op.TRANSCRIBE_AUDIO, [str(clip)])
        return dict(id="F04", finding_observed=not scheduled,
                    stale_transcript_scheduled_after_visual_refresh=bool(scheduled))


def probe_lost_writes():
    class FailingCollection:
        def upsert(self, **kwargs):
            raise sqlite3.OperationalError("synthetic disk full")

    add = method("core/database.py", "Database", "add_visual_embeddings", dict(logger=Null()))
    db = SimpleNamespace(visuals=FailingCollection())
    db.add_visual_embeddings = lambda *args: add(db, *args)
    worker = SimpleNamespace(db_write_batch=[([1.0], 3.0)])
    flush = method("workers/indexer.py", "IndexerWorker", "_flush_db_batch")
    flush(worker, db, "synthetic.MP4")
    return dict(id="F05", finding_observed=not worker.db_write_batch,
                failed_upsert_propagated=False, buffered_records_after_failure=len(worker.db_write_batch))


def probe_settings_root():
    tree = ast.parse((ROOT / "core/settings_manager.py").read_text())
    ns = dict(json=json, logging=SimpleNamespace(getLogger=lambda name: Null()), os=os, __name__="audit_settings")
    selected = [n for n in tree.body if isinstance(n, (ast.Assign, ast.ClassDef))]
    exec(compile(ast.Module(body=selected, type_ignores=[]), "core/settings_manager.py", "exec"), ns)
    with tempfile.TemporaryDirectory(prefix="cyne-settings-probe-") as tmp:
        dbdir = Path(tmp) / "_cyne_db"
        dbdir.mkdir()
        (dbdir / "settings.json").write_text("[]")
        try:
            ns["SettingsManager"](tmp)
        except TypeError as exc:
            return dict(id="F08", finding_observed=True, exception=type(exc).__name__, message=str(exc))
    return dict(id="F08", finding_observed=False)


def probe_cancelled_index():
    metadata = {}
    worker = SimpleNamespace(file_paths=["synthetic.MP4"], project_path="synthetic", mode="speed", is_running=True,
                             max_interval=15, min_frames_for_tag=1, tag_threshold_percent=0.2,
                             progress_signal=Signal(), log_signal=Signal(), summary_signal=Signal(),
                             finished_signal=Signal(), db_write_batch=[])

    class Capture:
        def isOpened(self):
            return True

        def get(self, prop):
            return 24 if prop == "fps" else 100

        def read(self):
            # Simulate cancellation at a decode boundary.
            worker.is_running = False
            return False, None

        def set(self, *args):
            pass

        def release(self):
            pass

    ai = SimpleNamespace(load_clip=lambda: (None, None), load_blip=lambda: (None, None),
                         load_yolo=lambda: None, unload_models=Null().unload_models)
    db = SimpleNamespace(update_metadata_key=lambda path, key, value: metadata.update({key: value}),
                         save_tags=lambda path, tags, summary: metadata.update(tags=tags))
    config_stub = types.ModuleType("config")
    config_stub.USE_BLIP2 = False
    config_stub.get_setting = lambda *args: False
    prior_config = sys.modules.get("config")
    sys.modules["config"] = config_stub
    try:
        run = method("workers/indexer.py", "IndexerWorker", "run", dict(
            logger=Null(), AIBackend=lambda: ai, Database=lambda path: db,
            get_tag_bank=lambda: [], log_memory_usage=lambda *args: None,
            os=os, time=time, defaultdict=defaultdict,
            cv2=SimpleNamespace(VideoCapture=lambda path: Capture(), CAP_PROP_FPS="fps", CAP_PROP_FRAME_COUNT="frames", CAP_PROP_POS_FRAMES="position")))
        run(worker)
    finally:
        if prior_config is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = prior_config
    return dict(id="F07", finding_observed=not worker.is_running and "last_scanned" in metadata,
                cancellation_requested=not worker.is_running,
                last_scanned_written_after_cancellation="last_scanned" in metadata,
                final_progress=worker.progress_signal.events[-1][0])


def probe_duration_and_cache():
    path = "core/search_engine.py"
    names = ["_parse_query_operators", "_apply_query_filters", "search", "build_index", "_index_single_file"]
    cls = ast.ClassDef(name="Engine", bases=[], keywords=[], body=[node(path, name, "SearchEngine") for name in names], decorator_list=[])
    ns = dict(os=os, json=json, time=time, logger=Null())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), path, "exec"), ns)
    eng = ns["Engine"]()
    eng.cache = {}
    eng.result_cache = {"vows": [{"path": "old.MP4", "score": 90, "match_type": "VISUAL", "context": "vows"}]}
    eng.result_cache_timestamps = {"vows": time.time()}
    eng.result_cache_ttl = 300
    eng.db = SimpleNamespace(get_video_metadata=lambda path: {"tags": ["new"]})
    with contextlib.redirect_stdout(io.StringIO()):
        eng.build_index(["new.MP4"])
    stale = eng.search("vows")
    parsed = eng._parse_query_operators("vows duration:30-60")
    wrong_duration = [{"path": "long.MP4", "duration": 3600, "score": 90}]
    kept = eng._apply_query_filters(wrong_duration, parsed)
    return dict(id="F09", finding_observed=bool(kept) and stale["cached"],
                out_of_range_duration_retained=bool(kept),
                result_cache_retained_after_metadata_refresh=stale["cached"])


def probe_scene_bounds():
    run = node("workers/indexer.py", "run", "IndexerWorker")
    outer = next(n for n in run.body if isinstance(n, ast.For))
    scene_if = next(n for n in outer.body if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "detected_scenes")
    ns = dict(scene_segments=[], detected_scenes=[{"score": 1}, {"score": 1}],
              total_frames=2400, fps=24, self=SimpleNamespace(mode="speed"), clip_model=None,
              db=SimpleNamespace(save_scene_segments=Null().save_scene_segments), video_path="synthetic.MP4")
    exec(compile(ast.Module(body=[scene_if], type_ignores=[]), "workers/indexer.py", "exec"), ns)
    stored = [s["end"] for s in ns["scene_segments"]]
    return dict(id="F06", finding_observed=stored == [50.0, 100.0],
                description="Any two scenes in a 100-second clip are assigned equal halves, independent of the actual cut.",
                stored_scene_ends_seconds=stored)


if __name__ == "__main__":
    current = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if current != "112388b25d7265ebb85d50ecf97604b920e9ca1b":
        raise SystemExit("Historical probes require baseline 112388b. For efd0930 run the search and review regression suites separately; see the reassessment.")
    probes = [probe_proxy_collision, probe_worker_handoff, probe_pause_boundary,
              probe_stage_freshness, probe_lost_writes, probe_scene_bounds, probe_cancelled_index,
              probe_settings_root, probe_duration_and_cache]
    print(json.dumps({"scope": "isolated source-level probes with synthetic collaborators; no real media or Qt runtime",
                      "results": [probe() for probe in probes]}, indent=2))
