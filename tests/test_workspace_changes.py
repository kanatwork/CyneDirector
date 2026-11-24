"""Real location/configuration preservation tests; disposable media only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from core import workspace_changes as changes,retention
from core.jobs import JobStore
from core.job_runner import JobRunner
from core.processing_lock import ProcessingBusy,ProcessingLock
from core.source_state import media_path,source_locations,source_signature
from core.workspace import Workspace,WorkspaceError
from tests.test_memory_retention import RetentionFixture


class ChangeTests(RetentionFixture):
    def setUp(self):
        super().setUp()
        self.project_file.write_text(json.dumps({'files':[self.path],'custom':{'editor':'keep'}}))
        self.store=JobStore(self.project)
        self.job=self.store.submit([self.path],['inventory'])
        self.root_id=self.workspace.data['media_roots'][0]['id']
        self.config_before=Workspace.path(self.project).read_bytes()
        self.payload_before=self.store.status(self.job)['payload']
        self.project_before=self.project_file.read_bytes()

    def moved(self):
        target=self.root/'SSD new mount';self.media.rename(target);return target

    def apply_relink(self,target):
        plan=changes.plan(self.project,relinks={self.root_id:str(target)})
        return changes.apply(self.project,plan['id'])

    def test_same_directory_relink_preserves_all_persistent_source_keys(self):
        self.publish(rows=3,artifact=True)
        meta=self.db.get_video_metadata(self.path);raw=self.db.visuals.raw.get(include=['metadatas'])
        target=self.moved();plan=changes.plan(self.project,relinks={self.root_id:str(target)})
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)
        result=changes.apply(self.project,plan['id']);self.assertEqual(result['state'],'applied')
        current=Workspace.load(self.project)
        self.assertEqual(current.data['id'],self.workspace.data['id'])
        self.assertEqual(current.data['media_roots'][0]['id'],self.root_id)
        self.assertEqual(current.resolve_source(self.path),str((target/self.source.name).resolve()))
        self.assertEqual(current.source_key(target/self.source.name),self.path)
        self.assertEqual(self.db.get_video_metadata(str(target/self.source.name)),meta)
        self.assertEqual(self.db.visuals.raw.get(include=['metadatas']),raw)
        self.assertEqual(self.store.status(self.job)['payload'],self.payload_before)
        self.assertEqual(self.project_file.read_bytes(),self.project_before)
        self.assertFalse(self.media.exists())

    def test_resubmission_after_relink_is_idempotent_and_keeps_asset_id(self):
        before=self.store.status(self.job);target=self.moved();self.apply_relink(target)
        job=self.store.submit([str(target/self.source.name)],['inventory'])
        self.assertEqual(job,self.job)
        after=self.store.status(job)
        self.assertEqual(after['items'][0]['asset_id'],before['items'][0]['asset_id'])
        self.assertEqual(after['items'][0]['path'],self.path)
        self.assertEqual(after['items'][0]['resolved_path'],str((target/self.source.name).resolve()))

    def test_duplicate_basenames_and_multiple_roots_stay_distinct(self):
        other=self.root/'other camera';other.mkdir();(other/self.source.name).write_bytes(b'other original')
        changes.apply(self.project,changes.plan(self.project,add_media_roots=[other])['id'])
        job=self.store.submit([self.path,str(other/self.source.name)],['inventory'])
        before=self.store.status(job);target=self.moved();self.apply_relink(target)
        after=self.store.status(job)
        self.assertEqual(len({i['asset_id'] for i in after['items']}),2)
        self.assertEqual([i['asset_id'] for i in before['items']],[i['asset_id'] for i in after['items']])
        self.assertNotEqual(after['items'][0]['resolved_path'],after['items'][1]['resolved_path'])

    def test_same_names_size_and_mtime_on_wrong_drive_are_rejected(self):
        target=self.root/'wrong SSD';shutil.copytree(self.media,target,copy_function=shutil.copy2)
        path=target/self.source.name;stat=path.stat();content=path.read_bytes()
        path.write_bytes(b'x'*len(content));os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.assertRaisesRegex(WorkspaceError,'Content verification failed'):
            changes.plan(self.project,relinks={self.root_id:target})
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)

    def test_offline_unsealed_replacement_is_rejected(self):
        target=self.root/'copied';shutil.copytree(self.media,target,copy_function=shutil.copy2);self.moved()
        with self.assertRaisesRegex(WorkspaceError,'no sealed hash'):
            changes.plan(self.project,relinks={self.root_id:target})

    def test_sealed_copy_can_be_verified_when_original_root_is_offline(self):
        seal=changes.plan(self.project,seal_roots=[self.root_id]);changes.apply(self.project,seal['id'])
        target=self.root/'verified copy';shutil.copytree(self.media,target,copy_function=shutil.copy2);self.moved()
        self.apply_relink(target)
        self.assertEqual(Workspace.load(self.project).resolve_source(self.path),str((target/self.source.name).resolve()))
        self.assertEqual(self.project_file.read_bytes(),self.project_before)

    def test_changed_copy_revision_is_rejected_even_with_same_content(self):
        target=self.root/'copy';shutil.copytree(self.media,target,copy_function=shutil.copy2)
        path=target/self.source.name;stat=path.stat();os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns+10**9))
        with self.assertRaisesRegex(WorkspaceError,'size/mtime differs'): changes.plan(self.project,relinks={self.root_id:target})

    def test_changed_target_after_plan_leaves_configuration_unchanged(self):
        target=self.moved();plan=changes.plan(self.project,relinks={self.root_id:target})
        (target/self.source.name).write_bytes(b'changed revision')
        with self.assertRaisesRegex(WorkspaceError,'changed since inspection'): changes.apply(self.project,plan['id'])
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)

    def test_replaced_target_directory_after_plan_is_rejected(self):
        target=self.moved();plan=changes.plan(self.project,relinks={self.root_id:target})
        target.rename(self.root/'actual SSD');target.mkdir()
        with self.assertRaises(WorkspaceError): changes.apply(self.project,plan['id'])
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)

    def test_stale_configuration_and_new_source_references_reject_plan(self):
        first=changes.plan(self.project,reserve_bytes=1024);second=changes.plan(self.project,reserve_bytes=2048)
        changes.apply(self.project,first['id'])
        with self.assertRaisesRegex(WorkspaceError,'fresh update plan'): changes.apply(self.project,second['id'])
        third=changes.plan(self.project,reserve_bytes=4096)
        other=self.media/'new.mp4';other.write_bytes(b'new');self.store.submit([str(other)],['inventory'])
        with self.assertRaisesRegex(WorkspaceError,'source references changed'): changes.apply(self.project,third['id'])

    def test_same_basename_missing_relative_path_is_not_substituted(self):
        folder=self.media/'camera A';folder.mkdir();nested=folder/self.source.name;nested.write_bytes(b'camera A')
        self.store.submit([str(nested)],['inventory']);target=self.root/'wrong layout';target.mkdir()
        shutil.copy2(self.source,target/self.source.name)
        with self.assertRaises(WorkspaceError): changes.plan(self.project,relinks={self.root_id:target})

    def test_symlink_escape_target_is_rejected(self):
        target=self.root/'copy';target.mkdir();(target/self.source.name).symlink_to(self.source)
        with self.assertRaisesRegex(WorkspaceError,'escapes'): changes.plan(self.project,relinks={self.root_id:target})

    def test_overlap_and_output_inside_original_alias_are_rejected(self):
        nested=self.media/'outputs';nested.mkdir()
        with self.assertRaises(WorkspaceError): changes.plan(self.project,output=nested)
        with self.assertRaises(WorkspaceError): changes.plan(self.project,add_media_roots=[self.media/'..'])

    def test_unknown_roots_and_noop_or_invalid_reserve_are_rejected(self):
        for kwargs in ({'relinks':{'unknown':self.media}},{'reserve_bytes':-1},{'reserve_bytes':True},{'output':''},{'model_cache':'  '},{'add_media_roots':['']},{}):
            with self.subTest(kwargs=kwargs),self.assertRaises((WorkspaceError,ValueError)): changes.plan(self.project,**kwargs)

    def test_output_model_and_reserve_updates_leave_existing_artifacts_and_jobs(self):
        self.publish(artifact=True);meta=self.db.get_video_metadata(self.path);old=Path(meta['proxy_path']);content=old.read_bytes()
        output=self.root/'new output';models=self.root/'new models';output.mkdir();models.mkdir()
        plan=changes.plan(self.project,output=output,model_cache=models,reserve_bytes=123456)
        changes.apply(self.project,plan['id']);workspace=Workspace.load(self.project)
        self.assertEqual(workspace.reserve,123456)
        self.assertEqual(old.read_bytes(),content);self.assertEqual(self.db.get_video_metadata(self.path),meta)
        self.assertEqual(self.store.status(self.job)['payload'],self.payload_before)
        generation=self.publish(artifact=True)
        self.assertIn(output.resolve(),Path(self.db.get_video_metadata(self.path)['proxy_path']).parents)
        self.assertTrue(old.is_file());self.assertEqual(workspace.output_for(old)['path'],str(self.output.resolve()))

    def test_historical_output_quarantine_restores_after_configuration_update(self):
        self.generations(rows=3,artifact=True);plan=self.plan();retention.apply(self.db,plan['run_id'],now=self.now)
        output=self.root/'next output';output.mkdir();changes.apply(self.project,changes.plan(self.project,output=output)['id'])
        retention.restore(self.db,plan['run_id'])
        self.assertEqual(self.db.visuals.raw.count(),12)
        self.assertTrue(all(Path(r[0]).is_file() for r in self.db._get_conn().execute('SELECT path FROM generation_artifacts')))

    def test_new_retention_plan_can_handle_old_and_new_output_roots(self):
        self.generations(rows=3,artifact=True)
        output=self.root/'next output';output.mkdir();changes.apply(self.project,changes.plan(self.project,output=output)['id'])
        self.generations(rows=3,artifact=True)
        plan=self.plan();retention.apply(self.db,plan['run_id'],now=self.now);retention.restore(self.db,plan['run_id'])
        self.assertEqual(self.db.visuals.raw.count(),24)

    def test_workspace_change_invalidates_unapplied_retention_plan(self):
        self.generations();plan=self.plan();changes.apply(self.project,changes.plan(self.project,reserve_bytes=4096)['id'])
        with self.assertRaisesRegex(RuntimeError,'stale'): retention.apply(self.db,plan['run_id'],now=self.now)

    def test_offline_historical_output_does_not_block_new_processing(self):
        self.publish(artifact=True);output=self.root/'next output';output.mkdir()
        changes.apply(self.project,changes.plan(self.project,output=output)['id']);self.output.rename(self.root/'offline output')
        workspace=Workspace.load(self.project)
        self.assertTrue(workspace.artifact_dir('temporary','abc').is_dir())
        self.assertEqual(self.db.get_video_metadata(self.path)['editor_note'],'preserve unknown fields')

    def test_atomic_replace_failure_preserves_configuration_and_retry_is_idempotent(self):
        plan=changes.plan(self.project,reserve_bytes=4096)
        with patch('core.workspace_changes.os.replace',side_effect=OSError('injected disk full')):
            with self.assertRaises(OSError): changes.apply(self.project,plan['id'])
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)
        self.assertEqual(changes.apply(self.project,plan['id'])['state'],'applied')
        self.assertEqual(changes.apply(self.project,plan['id'])['state'],'applied')

    def test_corrupt_journal_and_cancelled_plan_cannot_change_configuration(self):
        plan=changes.plan(self.project,reserve_bytes=4096);path=Workspace.path(self.project).parent/'workspace-changes'/(plan['id']+'.json')
        data=json.loads(path.read_text());data['checks'].append({'bad':'record'});path.write_text(json.dumps(data))
        with self.assertRaisesRegex(WorkspaceError,'checksum'): changes.apply(self.project,plan['id'])
        with self.assertRaisesRegex(WorkspaceError,'cancelled'): changes.plan(self.project,seal_roots=[self.root_id],allowed=lambda:False)
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)

    def test_processing_owner_blocks_update(self):
        errors=[];ready=threading.Event();release=threading.Event()
        def own():
            with ProcessingLock(): ready.set();release.wait(5)
        thread=threading.Thread(target=own);thread.start();self.assertTrue(ready.wait(2))
        try:
            with self.assertRaises(ProcessingBusy): changes.plan(self.project,reserve_bytes=4096)
        finally: release.set();thread.join()

    def test_submission_waits_for_atomic_configuration_commit(self):
        plan=changes.plan(self.project,reserve_bytes=4096)
        original=changes._atomic;entered=threading.Event();finished=threading.Event();errors=[];threads=[]
        def submit():
            entered.set()
            try: self.assertEqual(self.store.submit([self.path],['inventory']),self.job)
            except Exception as exc: errors.append(exc)
            finally: finished.set()
        def commit(path,data):
            thread=threading.Thread(target=submit);threads.append(thread);thread.start();self.assertTrue(entered.wait(2))
            self.assertFalse(finished.wait(.1))
            return original(path,data)
        with patch('core.workspace_changes._atomic',side_effect=commit): changes.apply(self.project,plan['id'])
        for thread in threads: thread.join(5)
        self.assertTrue(finished.is_set());self.assertEqual(errors,[])

    def test_old_alias_never_reads_a_replacement_file_at_old_mount(self):
        target=self.moved();self.apply_relink(target);self.media.mkdir();self.source.write_bytes(b'wrong file at old mount')
        with source_locations(Workspace.load(self.project)):
            self.assertEqual(Path(media_path(self.path)).read_bytes(),b'synthetic original preserved')
            self.assertEqual(source_signature(self.path),self.store.status(self.job)['items'][0]['signature'])

    def test_relinked_stage_writes_original_metadata_and_vector_source(self):
        target=self.moved();self.apply_relink(target);physical=str(target/self.source.name)
        with self.db.reprocess(physical,'visual',source_signature(physical)) as stage:
            stage.save_tags(physical,['wedding'],'preserved key');stage.add_visual_embeddings(physical,[[.1,.2,.3]],[1.])
        rows=self.db._get_conn().execute('SELECT video_path FROM video_metadata').fetchall()
        self.assertEqual([r[0] for r in rows],[self.path])
        self.assertEqual(self.db.visuals.get(include=['metadatas'])['metadatas'][0]['source'],self.path)

    def test_paused_job_resumes_after_relink_without_repeating_completed_stage(self):
        job=self.store.submit([self.path],['inventory','index_visuals']);store=self.store;calls=[]
        class Processor:
            def __init__(self,*args): pass
            def reconcile(self,item): return None
            def execute(self,item,allowed,log):
                calls.append(item['stage'])
                if len(calls)==1: store.control(job,'pause')
                return {'duration':1}
        def preflight(files,stages,settings):
            return Workspace.load(self.project).preflight(files,stages,settings,probe_fn=lambda p:{'duration':1,'streams':[{'codec_type':'video','width':32,'height':32}]})
        first=JobRunner(self.project,processor_factory=Processor,preflight=preflight).run(job)
        self.assertEqual(first['state'],'paused');self.assertEqual([i['attempts'] for i in first['items']],[1,0])
        target=self.moved();self.apply_relink(target);store.control(job,'resume')
        final=JobRunner(self.project,processor_factory=Processor,preflight=preflight).run(job)
        self.assertEqual(final['state'],'completed');self.assertEqual([i['attempts'] for i in final['items']],[1,1])
        self.assertEqual(calls,['inventory','index_visuals'])

    def test_published_checkpoint_reconciles_after_relink_without_inference(self):
        from core.processing import AppProcessor
        job=self.store.submit([self.path],['index_visuals']);item=self.store.status(job)['items'][0]
        payload=self.store.status(job)['payload'];processor=AppProcessor(self.project,self.workspace,payload['settings'])
        with self.db.publication_context(processor.checkpoint(item),lambda:True):
            with self.db.reprocess(self.path,'visual',self.signature) as stage:
                stage.add_visual_embeddings(self.path,[[.1,.2,.3]],[0.]);stage.update_metadata_key(self.path,'duration',1)
        target=self.moved();self.apply_relink(target)
        processor=AppProcessor(self.project,Workspace.load(self.project),payload['settings'])
        with patch.object(AppProcessor,'execute',side_effect=AssertionError('Inference must not repeat')):
            result=JobRunner(self.project,preflight=lambda *args:{'ok':True,'errors':[]}).run(job)
        self.assertEqual(result['state'],'completed',result)
        self.assertTrue(result['items'][0]['result']['reconciled'])

    def test_direct_transcript_save_resolves_logical_key_after_relink(self):
        target=self.moved();self.apply_relink(target)
        self.db.save_transcript(self.path,[{'start':0.,'end':1.,'text':'I do'}])
        self.assertEqual(self.db.get_video_metadata(str(target/self.source.name))['transcript'][0]['text'],'I do')

    def test_removed_legacy_symlink_alias_still_resolves_to_registered_source(self):
        alias=self.root/'legacy shortcut';alias.symlink_to(self.media,target_is_directory=True)
        legacy=str(alias/self.source.name)
        self.project_file.write_text(json.dumps({'files':[legacy],'custom':'keep'}))
        target=self.moved();self.apply_relink(target);alias.unlink()
        self.assertEqual(Workspace.load(self.project).resolve_source(legacy),str((target/self.source.name).resolve()))
        self.assertEqual(self.db.source_key(legacy),self.path)

    def test_within_root_symlink_uses_same_relative_identity_as_real_source(self):
        alias=self.media/'shortcut.mp4';alias.symlink_to(self.source)
        one=self.workspace.asset(str(alias));two=self.workspace.asset(self.path)
        self.assertEqual((one['root_id'],one['relative_path']),(two['root_id'],two['relative_path']))
        self.assertEqual(self.store.submit([str(alias)],['inventory']),self.job)

    def test_ambiguous_existing_metadata_rows_are_never_silently_merged(self):
        canonical=str(self.source.resolve())
        self.assertNotEqual(canonical,self.path)
        self.db._get_conn().execute('INSERT INTO video_metadata VALUES(?,?,?)',(canonical,0,'{"custom":"different existing record"}'));self.db._get_conn().commit()
        with self.assertRaisesRegex(WorkspaceError,'Multiple existing keys'): changes.plan(self.project,reserve_bytes=4096)
        self.assertEqual(self.db._get_conn().execute('SELECT COUNT(*) FROM video_metadata').fetchone()[0],2)
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)

    def test_cancelled_apply_and_symlinked_journal_leave_configuration_intact(self):
        plan=changes.plan(self.project,reserve_bytes=4096)
        with self.assertRaisesRegex(WorkspaceError,'cancelled'): changes.apply(self.project,plan['id'],allowed=lambda:False)
        path=Workspace.path(self.project).parent/'workspace-changes'/(plan['id']+'.json')
        copy=self.root/'journal-copy';path.rename(copy);path.symlink_to(copy)
        with self.assertRaisesRegex(WorkspaceError,'Unsafe change journal'): changes.apply(self.project,plan['id'])
        self.assertEqual(Workspace.path(self.project).read_bytes(),self.config_before)


class ProcessTests(RetentionFixture):
    def crash(self,after):
        plan=changes.plan(self.project,reserve_bytes=4096)
        before=Workspace.path(self.project).read_bytes();marker=self.root/'commit-marker'
        code='''import os,sys,time
from core import workspace_changes as changes
original=changes._atomic
def commit(path,data):
    if sys.argv[4]=='after': original(path,data)
    open(sys.argv[3],'w').write('ready')
    time.sleep(60)
changes._atomic=commit
changes.apply(sys.argv[1],sys.argv[2])
'''
        child=subprocess.Popen([sys.executable,'-c',code,str(self.project),plan['id'],str(marker),'after' if after else 'before'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+15
            while not marker.exists() and child.poll() is None and time.monotonic()<deadline: time.sleep(.05)
            self.assertTrue(marker.exists(),child.stderr.read().decode() if child.poll() is not None else 'marker timed out')
            child.kill();child.wait(timeout=10)
        finally:
            if child.poll() is None: child.kill();child.wait()
            child.stderr.close()
        report=changes.status(self.project,plan['id'])
        self.assertEqual(report['state'],'applied' if after else 'planned')
        if not after: self.assertEqual(Workspace.path(self.project).read_bytes(),before)
        result=subprocess.run([sys.executable,'-m','cyne_cli','--project',str(self.project),'workspace','apply',plan['id']],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)['state'],'applied')
        self.assertEqual(Workspace.load(self.project).reserve,4096)
        self.assertEqual(self.source.read_bytes(),b'synthetic original preserved')

    def test_process_death_before_replace_preserves_old_configuration_and_retries(self): self.crash(False)
    def test_process_death_after_replace_reports_complete_without_rewriting_data(self): self.crash(True)


if __name__=='__main__': unittest.main()
