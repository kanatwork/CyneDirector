"""Real SQLite/filesystem/process regression checks; no footage/models required."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from core.jobs import JobConflict, JobStore
from core.job_runner import JobRunner
from core.processing_lock import ProcessingBusy, ProcessingLock
from core.workspace import Workspace, WorkspaceError

ROOT = Path(__file__).resolve().parents[1]
META = {"duration": 10, "streams": [{"codec_type": "video", "codec_name": "h264", "r_frame_rate": "25/1", "width":320, "height":180}]}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cyne-jobs-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project, self.media, self.output, self.models = [self.root/name for name in ("project", "originals", "workspace", "models")]
        for path in (self.project, self.media, self.output, self.models):
            path.mkdir()
        self.source = self.media / "C0001.mp4"
        self.source.write_bytes(b"synthetic-original-content")
        self.workspace = Workspace.configure(self.project, [self.media], self.output, self.models, reserve_bytes=1024)
        self.store = JobStore(self.project)

    def submit(self, files=None, stages=None, **kwargs):
        return self.store.submit(files or [str(self.source)], stages or ["inventory"], **kwargs)

    def preflight(self, files, stages, settings):
        return self.workspace.preflight(files, stages, settings, probe_fn=lambda p: META)

    def runner(self, processor=None, **kwargs):
        return JobRunner(self.project, processor_factory=processor or CountingProcessor,
                         preflight=self.preflight, **kwargs)


class CountingProcessor:
    calls = []
    callback = None
    def __init__(self, project, workspace, settings):
        self.workspace = workspace
    def reconcile(self, item):
        return None
    def execute(self, item, allowed, log):
        self.calls.append(item["id"])
        if type(self).callback:
            type(self).callback(item)
        if not allowed():
            raise RuntimeError("Publication prevented")
        return {"duration": 10}


class WorkspaceTests(Fixture):
    def test_source_and_project_bytes_unchanged_by_configuration_preflight_and_inventory(self):
        project_file = self.project / "wedding.cyne"
        project_file.write_bytes(b'{"files":[],"custom":"preserve"}')
        before = {p: p.read_bytes() for p in (self.source, project_file)}
        self.preflight([str(self.source)], ["inventory"], {})
        self.runner().run(self.submit())
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(list(self.media.iterdir()), [self.source])

    def test_media_and_write_roots_must_be_disjoint(self):
        data = json.loads(json.dumps(self.workspace.data))
        data["destinations"]["output"] = data["media_roots"][0]
        with self.assertRaisesRegex(WorkspaceError, "Separate original"):
            Workspace(self.project, data)

    def test_symlink_escape_source_and_artifact_rejected(self):
        outside = self.root/"outside.mp4"; outside.write_bytes(b"no")
        (self.media/"alias.mp4").symlink_to(outside)
        with self.assertRaises(WorkspaceError):
            self.workspace.asset(self.media/"alias.mp4")
        (self.output/("cyne-"+self.workspace.data["id"])).symlink_to(self.media, target_is_directory=True)
        with self.assertRaises(WorkspaceError):
            self.workspace.artifact_dir("thumbnails", "generation")

    def test_same_filesystem_budgets_are_added_and_reserve_counted_once(self):
        report = self.preflight([str(self.source)], ["index_visuals", "transcribe_audio"], {"generate_proxies": True})
        self.assertEqual(len(report["volumes"]), 1)
        volume = report["volumes"][0]
        self.assertEqual(volume["required_bytes"], volume["estimated_additional_bytes"]+1024)
        self.assertGreater(volume["estimated_additional_bytes"], report["assets"][0]["estimated_output_bytes"]*2)
        low = self.workspace.preflight([str(self.source)], ["inventory"], {}, probe_fn=lambda p: META,
            disk_usage=lambda p: shutil._ntuple_diskusage(100, 99, 1))
        self.assertFalse(low["ok"])

    def test_missing_output_is_not_recreated_or_redirected(self):
        offline = self.output.with_name("unmounted")
        self.output.rename(offline)
        with self.assertRaises(WorkspaceError) as raised:
            Workspace.load(self.project)
        self.assertEqual(raised.exception.code, "waiting_media")
        self.assertFalse(self.output.exists())
        offline.rename(self.output)
        Workspace.load(self.project)

    def test_replaced_directory_same_path_is_rejected(self):
        self.output.rename(self.output.with_name("old"))
        self.output.mkdir()
        with self.assertRaises(WorkspaceError):
            Workspace.load(self.project)

    def test_configuration_is_additive_and_exclusive(self):
        original = Workspace.path(self.project).read_bytes()
        with self.assertRaises(WorkspaceError):
            Workspace.configure(self.project, [self.media], self.output, self.models)
        self.assertEqual(Workspace.path(self.project).read_bytes(), original)

    def test_unknown_project_status_does_not_create_database_folder(self):
        unknown=self.root/"unconfigured"; unknown.mkdir()
        with self.assertRaises(WorkspaceError): JobStore(unknown)
        self.assertFalse((unknown/"_cyne_db").exists())

    def test_ledger_symlink_cannot_overwrite_original(self):
        before=self.source.read_bytes()
        self.store.path.rename(self.store.path.with_suffix(".old"))
        self.store.path.symlink_to(self.source)
        with self.assertRaises(WorkspaceError): JobStore(self.project)
        self.assertEqual(self.source.read_bytes(),before)

    def test_invalid_reserve_and_unknown_version_fail_closed(self):
        for update in ({"reserve_bytes": -1}, {"reserve_bytes": "20"}, {"version": 99}):
            with self.subTest(update=update), self.assertRaises(WorkspaceError):
                Workspace(self.project, dict(self.workspace.data, **update))

    def test_default_twenty_gib_reserve_blocks_nineteen_gib_filesystem(self):
        from core.workspace import GIB
        workspace=Workspace(self.project,dict(self.workspace.data,reserve_bytes=20*GIB))
        report=workspace.preflight([str(self.source)],["inventory"],{},probe_fn=lambda p:META,
            disk_usage=lambda p:shutil._ntuple_diskusage(40*GIB,21*GIB,19*GIB))
        self.assertFalse(report["ok"])
        self.assertEqual(report["volumes"][0]["reserve_bytes"],20*GIB)

    @unittest.skipUnless(os.mkdir in os.supports_dir_fd,"Descriptor-relative mkdir required")
    def test_output_disappearing_during_creation_never_recreates_mount_path(self):
        original_mkdir=os.mkdir
        moved=False
        def mkdir(path,*args,**kwargs):
            nonlocal moved
            if kwargs.get("dir_fd") is not None and not moved:
                moved=True; self.output.rename(self.output.with_name("ejected-output"))
            return original_mkdir(path,*args,**kwargs)
        with patch("os.mkdir",mkdir),self.assertRaises(WorkspaceError):
            self.workspace.artifact_dir("proxies","generation")
        self.assertFalse(self.output.exists())

    def test_derivative_helpers_do_not_recreate_missing_managed_output(self):
        from core.proxy_generator import generate_proxy,generate_thumbnail
        missing=self.output/"missing-generation"
        self.assertIsNone(generate_proxy(str(self.source),str(missing),create_directory=False))
        self.assertIsNone(generate_thumbnail(str(self.source),str(missing),create_directory=False))
        self.assertFalse(missing.exists())


class LedgerTests(Fixture):
    def setUp(self):
        super().setUp()
        CountingProcessor.calls, CountingProcessor.callback = [], None

    def test_idempotent_submit_reopens_as_same_job_and_settings_are_snapshotted(self):
        self.assertEqual(self.submit(), JobStore(self.project).submit([str(self.source)], ["inventory"]))
        job = self.submit(settings={"whisper_model": "small", "deepl_api_key": "do-not-store"})
        status = self.store.status(job)
        self.assertEqual(status["payload"]["settings"]["whisper_model"], "small")
        self.assertNotIn("deepl_api_key", status["payload"]["settings"])
        self.assertIn("generate_thumbnails", status["payload"]["settings"])

    def test_request_key_conflict_does_not_change_original_job(self):
        job = self.submit(request_key="phone-repeat")
        with self.assertRaises(JobConflict):
            self.submit(stages=["index_visuals"], request_key="phone-repeat")
        self.assertEqual(self.store.status(job)["state"], "pending")

    def test_explicit_new_analysis_keeps_completed_job_history(self):
        old=self.submit(request_key="first-analysis")
        self.assertEqual(self.runner().run(old)["state"],"completed")
        new=self.submit(request_key="forced-new-analysis")
        self.assertNotEqual(old,new)
        self.assertEqual(self.runner().run(new)["state"],"completed")
        self.assertEqual(self.store.status(old)["items"][0]["attempts"],1)

    def test_concurrent_duplicate_submissions_commit_once(self):
        ids, errors = [], []
        def submit():
            try: ids.append(self.submit())
            except Exception as exc: errors.append(exc)
        threads = [threading.Thread(target=submit) for _ in range(4)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.store.list_jobs()), 1)

    def test_live_lease_and_stale_owner_fencing(self):
        job = self.submit()
        self.assertTrue(self.store.claim(job, "runner-one"))
        with self.assertRaises(JobConflict): self.store.claim(job, "runner-two")
        item = self.store.status(job)["items"][0]
        with self.assertRaises(JobConflict): self.store.begin_item(job, item["id"], "stale")

    def test_pause_survives_reopen_and_resume_skips_completed_file(self):
        second = self.media/"C0002.mp4"; second.write_bytes(b"second")
        job = self.submit(files=[str(self.source),str(second)])
        CountingProcessor.callback = lambda item: self.store.control(job, "pause")
        first = self.runner().run(job)
        self.assertEqual(first["state"], "paused")
        self.assertEqual(first["counts"], {"completed": 1, "pending": 1})
        CountingProcessor.callback = None
        self.store.control(job, "resume")
        finished = self.runner().run(job)
        self.assertEqual(finished["state"], "completed")
        self.assertEqual([i["attempts"] for i in finished["items"]], [1,1])

    def test_cancel_during_stage_prevents_success_and_retry_is_explicit(self):
        job = self.submit()
        CountingProcessor.callback = lambda item: self.store.control(job, "cancel")
        result = self.runner().run(job)
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(result["counts"], {"cancelled":1})
        CountingProcessor.callback = None
        self.store.control(job, "retry_failed")
        self.assertEqual(self.runner().run(job)["state"], "completed")

    def test_low_capacity_wait_preserves_pending_and_no_processor_called(self):
        job = self.submit()
        result = JobRunner(self.project, processor_factory=CountingProcessor,
                           preflight=lambda *args: {"ok": False}).run(job)
        self.assertEqual(result["state"], "waiting_capacity")
        self.assertEqual(result["counts"], {"pending":1})
        self.assertEqual(CountingProcessor.calls, [])
        self.assertEqual(self.runner().run(job)["state"], "completed")

    def test_offline_drive_wait_does_not_create_replacement_then_recovers(self):
        job = self.submit()
        self.media.rename(self.media.with_name("offline"))
        self.assertEqual(self.runner().run(job)["state"], "waiting_media")
        self.assertEqual(self.store.status(job)["counts"], {"pending":1})
        self.assertFalse(self.media.exists())
        self.media.with_name("offline").rename(self.media)
        self.assertEqual(self.runner().run(job)["state"], "completed")

    def test_changed_source_fails_without_running_processor(self):
        job = self.submit()
        self.source.write_bytes(b"changed source revision")
        result = self.runner().run(job)
        self.assertEqual(result["state"], "failed")
        self.assertIn("source_changed", result["items"][0]["error"])
        self.assertEqual(CountingProcessor.calls, [])

    def test_failed_item_retries_without_repeating_completed_stage(self):
        job = self.submit(stages=["inventory", "index_visuals"])
        def fail_visual(item):
            if item["stage"]=="index_visuals": raise RuntimeError("injected model failure")
        CountingProcessor.callback = fail_visual
        result = self.runner().run(job)
        self.assertEqual(result["counts"], {"completed":1,"failed":1})
        CountingProcessor.callback = None
        self.store.control(job,"retry_failed")
        result = self.runner().run(job)
        self.assertEqual(result["state"], "completed")
        self.assertEqual([i["attempts"] for i in result["items"]], [1,2])

    def test_event_cursor_is_monotonic_and_incremental(self):
        job = self.submit()
        before = self.store.events(job)
        self.runner().run(job)
        after = self.store.events(job, before[-1]["cursor"])
        self.assertTrue(after)
        self.assertTrue(all(e["cursor"]>before[-1]["cursor"] for e in after))
        self.assertEqual(sorted(e["cursor"] for e in after), [e["cursor"] for e in after])

    def test_model_lock_is_released_on_process_death_and_prevents_second_owner(self):
        code = "from core.processing_lock import ProcessingLock; import time; lock=ProcessingLock(); lock.__enter__(); print('locked',flush=True); time.sleep(60)"
        child = subprocess.Popen([sys.executable,"-c",code],cwd=ROOT,stdout=subprocess.PIPE,text=True)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        self.assertEqual(child.stdout.readline().strip(), "locked")
        with self.assertRaises(ProcessingBusy):
            with ProcessingLock(): pass
        child.kill(); child.wait(timeout=5); child.stdout.close()
        with ProcessingLock(): pass

    def test_actual_kill_and_restart_retries_only_uncommitted_item(self):
        second=self.media/"C0002.mp4"; second.write_bytes(b"second")
        job=self.submit(files=[str(self.source),str(second)])
        marker=self.root/"in-stage"
        code='''
import sys,time
from pathlib import Path
from core.job_runner import JobRunner
class Processor:
 def __init__(self,*args): pass
 def reconcile(self,item): return None
 def execute(self,item,allowed,log):
  if item['path'].endswith('C0002.mp4'):
   Path(sys.argv[3]).write_text('running'); time.sleep(60)
  return {'duration':10}
JobRunner(sys.argv[1],processor_factory=Processor,preflight=lambda *args:{'ok':True},heartbeat_interval=.05,lease_seconds=.3).run(sys.argv[2])
'''
        child=subprocess.Popen([sys.executable,"-c",code,str(self.project),job,str(marker)],cwd=ROOT,stderr=subprocess.PIPE,text=True)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        deadline=time.monotonic()+10
        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:
            time.sleep(.02)
        self.assertTrue(marker.exists(), child.stderr.read() if child.poll() is not None else "child timeout")
        child.kill(); child.wait(timeout=5); child.stderr.close()
        time.sleep(.4)
        result=self.runner().run(job)
        self.assertEqual(result["state"],"completed")
        self.assertEqual([i["attempts"] for i in result["items"]],[1,2])
        self.assertTrue(any(e["kind"]=="interrupted" for e in self.store.events(job)))

    def test_stage_specific_scope_never_reprocesses_unselected_file(self):
        second=self.media/"C0002.mp4"; second.write_bytes(b"second")
        job=self.store.submit([str(self.source),str(second)],["inventory","index_visuals"],
            tasks={"inventory":[str(self.source),str(second)],"index_visuals":[str(second)]})
        items=self.store.status(job)["items"]
        self.assertEqual(len(items),3)
        self.assertFalse(any(i["stage"]=="index_visuals" and i["path"]==str(self.source) for i in items))

    def test_mid_stage_drive_loss_defers_item_then_resumes(self):
        job=self.submit()
        CountingProcessor.callback=lambda item:self.output.rename(self.output.with_name("offline-output"))
        result=self.runner().run(job)
        self.assertEqual(result["state"],"waiting_media")
        self.assertEqual(result["counts"],{"pending":1})
        self.output.with_name("offline-output").rename(self.output)
        CountingProcessor.callback=None
        self.assertEqual(self.runner().run(job)["state"],"completed")

    def test_heartbeat_is_live_during_long_item(self):
        job=self.submit()
        def wait(item):
            first=self.store.status(job)["heartbeat"]
            time.sleep(.4)
            last=self.store.status(job)
            self.assertGreater(last["heartbeat"],first)
            self.assertTrue(last["runner_live"])
        CountingProcessor.callback=wait
        result=self.runner(heartbeat_interval=.05,lease_seconds=.3).run(job)
        self.assertEqual(result["state"],"completed")

    def test_corrupt_input_fails_individually_and_other_source_completes(self):
        good=self.media/"C0002.mp4"; good.write_bytes(b"good")
        job=self.submit(files=[str(self.source),str(good)])
        def probe(path):
            if Path(path)==self.source.resolve(): raise WorkspaceError("unsupported_media","corrupt input")
            return META
        result=JobRunner(self.project,processor_factory=CountingProcessor,
            preflight=lambda files,stages,settings:self.workspace.preflight(files,stages,settings,probe_fn=probe)).run(job)
        self.assertEqual(result["counts"],{"failed":1,"completed":1})

    def test_project_session_prevents_cross_process_chroma_access(self):
        from core.processing_lock import ProjectSession
        path=self.project/"data-session.lock"
        session=ProjectSession(path)
        self.addCleanup(session.close)
        code="from core.processing_lock import ProjectSession,ProcessingBusy; import sys;\ntry: ProjectSession(sys.argv[1])\nexcept ProcessingBusy: sys.exit(12)\n"
        result=subprocess.run([sys.executable,"-c",code,str(path)],cwd=ROOT,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,12,result.stderr)

    def test_future_ledger_schema_is_rejected_without_rewriting_jobs(self):
        import sqlite3
        job=self.submit()
        with sqlite3.connect(self.store.path) as db:
            payload=db.execute("SELECT payload FROM jobs WHERE id=?",(job,)).fetchone()[0]
            db.execute("PRAGMA user_version=99")
        with self.assertRaises(JobConflict): JobStore(self.project)
        with sqlite3.connect(self.store.path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0],99)
            self.assertEqual(db.execute("SELECT payload FROM jobs WHERE id=?",(job,)).fetchone()[0],payload)

    @unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required")
    def test_detached_cli_inventory_survives_launcher_exit_and_returns_json(self):
        source=self.media/"real.mp4"
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","color=red:s=160x90:d=0.5","-c:v","libx264",str(source)],check=True,capture_output=True,timeout=15)
        job=self.submit(files=[str(source)])
        command=[sys.executable,"-m","cyne_cli","--project",str(self.project)]
        launched=subprocess.run(command+["start",job],cwd=ROOT,text=True,capture_output=True,timeout=15)
        self.assertEqual(launched.returncode,0,launched.stdout+launched.stderr)
        self.assertTrue(json.loads(launched.stdout)["started"])
        deadline=time.monotonic()+15
        while time.monotonic()<deadline and self.store.status(job)["state"] in ("pending","running"):
            time.sleep(.1)
        result=subprocess.run(command+["status",job],cwd=ROOT,text=True,capture_output=True,timeout=10)
        status=json.loads(result.stdout)
        self.assertEqual(status["state"],"completed",status)
        self.assertEqual(status["counts"],{"completed":1})


class CheckpointTests(Fixture):
    def setUp(self):
        super().setUp()
        from core.database import Database
        self.db=Database(); self.db.initialize(str(self.project))
        self.addCleanup(self.db.close)

    def test_publish_then_ledger_crash_reconciles_without_running_inference(self):
        from core.processing import AppProcessor
        from core.source_state import source_signature
        job=self.submit(stages=["index_visuals"])
        status=self.store.status(job); item=status["items"][0]
        processor=AppProcessor(self.project,self.workspace,status["payload"]["settings"])
        self.store.claim(job,"dead-runner")
        self.store.begin_item(job,item["id"],"dead-runner")
        with self.db.publication_context(processor.checkpoint(item),lambda:True):
            with self.db.reprocess(item["path"],"visual",source_signature(item["path"])) as staged:
                staged.save_tags(item["path"],["published"],"published before crash")
        with self.store.connection() as db:
            db.execute("UPDATE jobs SET lease_until=0 WHERE id=?",(job,))
        class ReconcileOnly(AppProcessor):
            def execute(self,*args): raise AssertionError("Published work must not run again")
        result=self.runner(ReconcileOnly).run(job)
        self.assertEqual(result["state"],"completed")
        self.assertTrue(result["items"][0]["result"]["reconciled"])
        self.assertEqual(self.db.get_video_metadata(item["path"])["tags"],["published"])

    def test_failed_publication_cannot_commit_checkpoint(self):
        from core.source_state import source_signature
        path=str(self.source)
        self.db.save_tags(path,["old"],"keep")
        with self.assertRaises(RuntimeError),self.db.publication_context({"item_id":"never-committed"},lambda:True):
            with self.db.reprocess(path,"visual",source_signature(path)) as staged:
                staged.save_tags(path,["new"],"discard"); raise RuntimeError("failed inference")
        metadata=self.db.get_video_metadata(path)
        self.assertEqual(metadata["tags"],["old"])
        self.assertNotIn("visual_job_checkpoint",metadata)

    def test_clearing_or_superseding_generation_invalidates_job_checkpoint(self):
        from core.processing import AppProcessor
        from core.source_state import source_signature
        job=self.submit(stages=["index_visuals"]); item=self.store.status(job)["items"][0]
        processor=AppProcessor(self.project,self.workspace,self.store.status(job)["payload"]["settings"])
        with self.db.publication_context(processor.checkpoint(item),lambda:True):
            with self.db.reprocess(item["path"],"visual",source_signature(item["path"])) as stage:
                stage.save_tags(item["path"],["new"],"new")
        self.assertIsNotNone(processor.reconcile(item))
        self.db.clear_visual_embeddings(item["path"])
        self.assertIsNone(processor.reconcile(item))

    def test_legacy_path_alias_is_preserved_without_duplicate_asset(self):
        alias=self.root/"camera-alias"; alias.symlink_to(self.media,target_is_directory=True)
        original_key=str(alias/self.source.name)
        self.db.update_metadata_key(original_key,"editor_note","keep")
        job=self.submit(files=[str(self.source),original_key])
        status=self.store.status(job)
        self.assertEqual(len(status["items"]),1)
        self.assertEqual(status["items"][0]["path"],original_key)

    def test_source_change_before_worker_snapshot_cannot_publish_new_revision(self):
        from core.source_state import source_signature
        from core.generations import ReprocessingAborted
        path=str(self.source)
        old=source_signature(path)
        self.db.save_tags(path,["old"],"keep")
        self.source.write_bytes(b"changed before worker decode")
        with self.assertRaises(ReprocessingAborted),self.db.publication_context({"item_id":"old-job"},lambda:source_signature(path)==old):
            with self.db.reprocess(path,"visual",source_signature(path)) as stage:
                stage.save_tags(path,["new"],"discard")
        self.assertEqual(self.db.get_video_metadata(path)["tags"],["old"])


if __name__ == "__main__":
    unittest.main()
