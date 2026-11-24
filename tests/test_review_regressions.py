"""Regression checks without model downloads or a desktop session.

Run separately from smoke_search (which installs global import stubs):
    python -m unittest tests.test_review_regressions -v

GUI control-flow checks compile the actual methods and replace widgets/signals
with small doubles; they do not validate Qt rendering or thread scheduling.
"""
import ast
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative_path, stubs=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs or {}):
        spec.loader.exec_module(module)
    return module


class Signal:
    def __init__(self, *args):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


qt_core = types.ModuleType("PyQt6.QtCore")
qt_core.QObject = object
qt_core.pyqtSignal = Signal
db_stub = types.ModuleType("core.database")
db_stub.Database = Mock
workflow = load_module("review_workflow", "core/workflow_manager.py", {
    "PyQt6": types.ModuleType("PyQt6"), "PyQt6.QtCore": qt_core,
    "core.database": db_stub,
})


def gui_methods(*names):
    source = ast.parse((ROOT / "gui/main_window.py").read_text(encoding="utf-8"))
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef)
               and node.name == "MainWindow")
    functions = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"os": os, "COLORS": {"success": "green", "error": "red"},
                 "OperationType": workflow.OperationType}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROOT / "gui/main_window.py"), "exec"), namespace)
    return type("WindowHarness", (), {name: namespace[name] for name in names})


class SubtitleTests(unittest.TestCase):
    def export(self, text, start=0.0, end=20.0, sentence_mode=True):
        from core.srt_exporter import SRTExporter
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "vows.srt"
            self.assertTrue(SRTExporter.export_transcript_to_srt(
                [{"start": start, "end": end, "text": text}], str(output), sentence_mode))
            return [block.splitlines() for block in output.read_text(encoding="utf-8").strip().split("\n\n")]

    def test_long_vow_preserves_every_word(self):
        text = " ".join(f"promise{n}" for n in range(80))
        blocks = self.export(text)
        self.assertEqual(" ".join(line for block in blocks for line in block[2:]), text)
        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(len(block[2:]) <= 2 for block in blocks))
        self.assertTrue(all(len(line) <= 42 for block in blocks for line in block[2:]))

    def test_short_cue_keeps_its_end_time(self):
        blocks = self.export("I do.", 3.0, 3.2)
        self.assertEqual(blocks[0][1], "00:00:03,000 --> 00:00:03,200")

    def test_sentence_splits_remain_inside_source_segment(self):
        from core.translator import split_segments_into_sentences
        segments = split_segments_into_sentences([{"start": 1.0, "end": 1.3, "text": "Yes. I do."}])
        self.assertTrue(all(1.0 <= seg["start"] < seg["end"] <= 1.3 for seg in segments))

    def test_rounding_carries_into_next_second(self):
        from core.srt_exporter import SRTExporter
        self.assertEqual(SRTExporter.format_timestamp(59.9999), "00:01:00,000")

    def test_long_unbroken_text_is_preserved(self):
        text = "अ" * 220
        blocks = self.export(text)
        self.assertEqual("".join(line for block in blocks for line in block[2:]), text)

    def test_questions_keep_their_punctuation(self):
        from core.translator import split_into_sentences
        self.assertEqual(split_into_sentences("will you? I will!"), ["will you?", "I will!"])

    def test_same_camera_names_export_distinct_files(self):
        from core.srt_exporter import SRTExporter
        transcripts = {"camera_a/C0001.mp4": [{"start": 0, "end": 1, "text": "Bride"}],
                       "camera_b/C0001.mp4": [{"start": 0, "end": 1, "text": "Groom"}]}
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(all(SRTExporter.export_multiple_transcripts(transcripts, directory).values()))
            files = list(Path(directory).glob("*.srt"))
            self.assertEqual(len(files), 2)
            contents = " ".join(p.read_text(encoding="utf-8") for p in files)
            self.assertIn("Bride", contents)
            self.assertIn("Groom", contents)


class CacheNamesAndSettingsTests(unittest.TestCase):
    def test_clip_supports_tensor_and_transformers_five_outputs(self):
        from core.clip_features import as_clip_tensor
        tensor = object()
        self.assertIs(as_clip_tensor(tensor), tensor)
        self.assertIs(as_clip_tensor(types.SimpleNamespace(pooler_output=tensor)), tensor)
        self.assertIs(as_clip_tensor(("hidden state", tensor)), tensor)

    def test_proxies_distinguish_camera_folders_and_extensions(self):
        from core.proxy_generator import _safe_stem
        names = [_safe_stem(path) for path in ["camera_a/C0001.mp4", "camera_b/C0001.mp4", "camera_a/C0001.mov"]]
        self.assertEqual(len(set(names)), 3)
        self.assertEqual(names[0], _safe_stem("camera_a/./C0001.mp4"))

    def test_valid_json_with_wrong_shape_falls_back_to_defaults(self):
        from core.settings_manager import DEFAULTS, SettingsManager
        for value in ("[]", "null", "42", '"settings"'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                db_dir = Path(directory) / "_cyne_db"
                db_dir.mkdir()
                (db_dir / "settings.json").write_text(value, encoding="utf-8")
                self.assertEqual(SettingsManager(directory).to_dict(), DEFAULTS)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / "C0001.mp4")
        Path(self.path).write_bytes(b"footage")
        self.manager = workflow.WorkflowManager(self.directory.name)
        # Signals in this harness need instance isolation, as Qt provides.
        for name in ("operation_started", "operation_finished", "workflow_started", "workflow_finished",
                     "workflow_paused", "workflow_resumed"):
            setattr(self.manager, name, Signal())

    def test_visual_scan_cannot_hide_outdated_transcript(self):
        from core.source_state import source_signature
        meta = {"tags": ["wedding"], "transcript": [{"text": "old vows"}],
                "last_scanned": os.path.getmtime(self.path),
                "visual_source_signature": source_signature(self.path)}
        self.manager.db.get_video_metadata.return_value = meta
        needed = self.manager.get_files_needing_operations([self.path])
        self.assertEqual(needed[workflow.OperationType.INDEX_VISUALS], [])
        self.assertEqual(needed[workflow.OperationType.TRANSCRIBE_AUDIO], [self.path])

    def test_transcription_then_translation_can_be_queued_for_new_clip(self):
        self.manager.db.get_video_metadata.return_value = {}
        self.assertTrue(self.manager.add_operation(workflow.OperationType.TRANSCRIBE_AUDIO, [self.path]))
        needed = self.manager.get_files_needing_operations([self.path])
        self.assertEqual(needed[workflow.OperationType.TRANSLATE_AUDIO], [self.path])

    def test_changed_file_size_is_detected_with_unchanged_mtime(self):
        from core.source_state import source_signature, needs_processing
        signature = source_signature(self.path)
        Path(self.path).write_bytes(b"replacement footage")
        os.utime(self.path, ns=(signature[0], signature[0]))
        self.assertTrue(needs_processing(self.path, {"visual_source_signature": signature}, "visual"))

    def test_resume_after_current_job_finishes_starts_next_job(self):
        self.manager.add_operation(workflow.OperationType.INDEX_VISUALS, [self.path], smart_filter=False)
        self.manager.add_operation(workflow.OperationType.TRANSCRIBE_AUDIO, [self.path], smart_filter=False)
        self.manager.start_workflow()
        self.manager.pause_workflow()
        self.manager.on_operation_finished(workflow.OperationType.INDEX_VISUALS, True)
        self.assertIsNone(self.manager.current_operation)
        self.manager.resume_workflow()
        self.assertEqual(self.manager.current_operation.op_type, workflow.OperationType.TRANSCRIBE_AUDIO)


class WorkerHandoffTests(unittest.TestCase):
    def test_watcher_cannot_import_generated_workspace_proxy_as_original(self):
        from core.workspace import Workspace
        cls = gui_methods("_watcher_accepts_source", "_on_watched_new_file", "_on_watched_file_modified")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project, media, output, models = [root/name for name in ("project","originals","output","models")]
            for path in (project,media,output,models): path.mkdir()
            Workspace.configure(project,[media],output,models,1024)
            original=media/"original.mp4"; original.write_bytes(b"original")
            generated=output/"preview.mp4"; generated.write_bytes(b"proxy")
            window=cls(); window.project_path=str(project)
            window.tree=Mock(); window.background_indexer=Mock(); window.mark_dirty=Mock()
            self.assertTrue(window._watcher_accepts_source(str(original)))
            window._on_watched_new_file(str(generated))
            window._on_watched_file_modified(str(generated))
            window.tree.add_files_flat.assert_not_called()
            window.background_indexer.add_file.assert_not_called()
            window.mark_dirty.assert_not_called()

    def test_settings_cannot_mutate_running_job_snapshot(self):
        cls = gui_methods("show_settings")
        window = cls()
        window.worker = object()
        window.background_indexer = types.SimpleNamespace(is_indexing=False)
        window.workflow_manager = types.SimpleNamespace(is_running=False)
        window.toast_manager = Mock()
        window.show_settings()
        window.toast_manager.show_toast.assert_called_once()

    def make_window(self):
        cls = gui_methods("worker_finished", "on_translation_file_finished")
        window = cls()
        window.worker = Mock(is_running=True, errors=[], file_paths=["vows.mp4"])
        window.lock_buttons = Mock()
        window.progress_bar = Mock()
        window.status_label = Mock()
        window.status_label.text.return_value = "Transcription Complete."
        window.status_icon = Mock()
        window.mark_dirty = Mock()
        window.search_tab = Mock()
        window.update_preview_panel = Mock()
        window.workflow_manager = Mock()
        return window

    def test_next_worker_survives_completion_callback(self):
        window = self.make_window()
        old_worker = window.worker
        next_worker = Mock(is_running=True)
        next_worker.isRunning.return_value = False
        window.workflow_manager.on_operation_finished.side_effect = lambda *args: setattr(window, "worker", next_worker)
        window.worker_finished()
        self.assertIs(window.worker, next_worker)
        old_worker.deleteLater.assert_called_once()
        next_worker.wait.assert_not_called()

    def test_failure_is_reported_even_after_final_completion_log(self):
        window = self.make_window()
        window.worker.errors = ["Could not transcribe groom speech"]
        window.worker_finished()
        self.assertFalse(window.workflow_manager.on_operation_finished.call_args.args[1])

    def test_cancelled_translation_does_not_start_another_file(self):
        window = self.make_window()
        window.worker.is_running = False
        window.translation_files = ["bride.mp4", "groom.mp4"]
        window.current_translation_index = 0
        window.translation_errors = []
        window.worker_finished = Mock()
        window.update_progress = Mock()
        window._process_next_translation_file = Mock()
        window.on_translation_file_finished(False, "Cancelled")
        window._process_next_translation_file.assert_not_called()
        window.worker_finished.assert_called_once()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module("review_database", "core/database.py", {"chromadb": types.ModuleType("chromadb")})
        self.directory = tempfile.TemporaryDirectory()
        self.db = self.module.Database()
        self.db.sqlite_path = str(Path(self.directory.name) / "metadata.db")
        self.db._init_sqlite()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.db.close)

    def test_retranscription_invalidates_old_translation(self):
        from core.source_state import source_signature
        path = str(Path(self.directory.name) / "vows.mp4")
        Path(path).write_bytes(b"source")
        signature = source_signature(path)
        self.db.transcripts = Mock()
        self.db.update_metadata_key(path, "transcript_translated", [{"text": "old translation"}])
        self.db.update_metadata_key(path, "translation_timestamp", 100)
        self.db.save_transcript(path, [{"start": 0, "end": 1, "text": "new vows"}], source_signature=signature)
        meta = self.db.get_video_metadata(path)
        self.assertNotIn("transcript_translated", meta)
        self.assertNotIn("translation_timestamp", meta)
        self.assertEqual(meta["transcript_source_signature"], signature)
        self.assertTrue(meta["transcript_generation"])
        self.db.transcripts.delete.assert_not_called()

    def test_write_failure_reaches_caller(self):
        connection = Mock()
        connection.execute.side_effect = RuntimeError("Disk full")
        with patch.object(self.db, "_get_conn", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "Disk full"):
                self.db._save_data("vows.mp4", {"tags": ["bride"]})
        connection.rollback.assert_called_once()

    def test_read_failure_cannot_overwrite_existing_metadata(self):
        with patch.object(self.db, "_get_conn", side_effect=RuntimeError("Database unavailable")):
            with self.assertRaisesRegex(RuntimeError, "Database unavailable"):
                self.db.update_metadata_key("vows.mp4", "tags", ["bride"])

    def test_clearing_metadata_tombstones_search_vectors(self):
        self.db.visuals = Mock()
        self.db.temporal_sequences = Mock()
        self.db.transcripts = Mock()
        self.db.clear_metadata_keys("vows.mp4", ["tags", "transcript"])
        for name in ("visuals", "temporal_sequences", "transcripts"):
            getattr(self.db, name).delete.assert_not_called()
        meta = self.db.get_video_metadata("vows.mp4")
        self.assertTrue(meta["visual_generation"])
        self.assertTrue(meta["transcript_generation"])


if __name__ == "__main__":
    unittest.main()
