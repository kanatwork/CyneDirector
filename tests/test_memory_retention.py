"""Bounds and reversible retention with synthetic data, actual SQLite/Chroma."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from core.memory_budget import MemoryPolicy, MemoryBudgetExceeded, RecordBuffer, Tail, ThreeFrameSet
from core import retention
from core.source_state import source_signature
from core.workspace import Workspace, artifact_directory


class MemoryTests(unittest.TestCase):
    def test_policy_rejects_unbounded_invalid_values(self):
        for value in (0,63,1025,True,"256"):
            with self.subTest(value=value),self.assertRaises(ValueError): MemoryPolicy(value)
        for value in (0,301,True):
            with self.assertRaises(ValueError): MemoryPolicy(speech_seconds=value)

    def test_decode_dimensions_are_checked(self):
        MemoryPolicy().dimensions(3840,2160)
        for width,height in ((0,1080),(7680,4320)):
            with self.assertRaises(MemoryBudgetExceeded): MemoryPolicy().dimensions(width,height)

    def test_preflight_reports_bounded_pcm_and_rejects_oversized_video_only_for_visuals(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths=[Path(tmp)/name for name in ('project','media','output','models')]
            for path in paths: path.mkdir()
            source=paths[1]/'8k.mp4';source.write_bytes(b'synthetic')
            workspace=Workspace.configure(paths[0],[paths[1]],paths[2],paths[3],0)
            metadata={'duration':10*3600,'streams':[{'codec_type':'video','width':7680,'height':4320},{'codec_type':'audio'}]}
            settings={'processing_memory_mib':64,'speech_chunk_seconds':180}
            report=workspace.preflight([str(source)],['index_visuals','transcribe_audio'],settings,probe_fn=lambda p:metadata)
            self.assertEqual(report['errors'][0]['stages'],['index_visuals'])
            self.assertEqual(report['memory_policy']['frame_batch'],16)
            self.assertEqual(report['temporary_pcm_bytes'],184*32000+4096)
            report=workspace.preflight([str(source)],['transcribe_audio'],settings,probe_fn=lambda p:metadata)
            self.assertEqual(report['errors'],[])

    def test_guard_reports_media_budget_failure_instead_of_waiting_for_capacity(self):
        from core.processing import processing_guard
        from core.workspace import WorkspaceError
        workspace=types.SimpleNamespace(preflight=lambda *a:{'ok':False,'errors':[{'error':'Decoded frame exceeds pixel budget'}]})
        config=types.SimpleNamespace(_settings=types.SimpleNamespace(to_dict=lambda:{}))
        with patch.dict(sys.modules,{'config':config}),patch('core.processing.Workspace.load',return_value=workspace):
            with self.assertRaises(WorkspaceError) as caught:
                with processing_guard('unused',['unused'],['index_visuals']): self.fail('Budget failure must not start processing')
            self.assertEqual(caught.exception.code,'unsupported_media')

    def test_record_limits_fail_without_silently_dropping_prior_records(self):
        records=RecordBuffer(2,1000)
        records.append({"text":"first"});records.append({"text":"second"})
        with self.assertRaises(MemoryBudgetExceeded): records.append({"text":"third"})
        self.assertEqual([r["text"] for r in records],["first","second"])

    def test_record_byte_limit_and_large_model_record(self):
        records=RecordBuffer(100,32)
        with self.assertRaises(MemoryBudgetExceeded): records.append({"text":"a"*100})
        with self.assertRaises(MemoryBudgetExceeded): RecordBuffer(100,10**9).append({"text":"a"*65537})
        self.assertEqual(records,[])

    def test_occurrences_and_keyframes_do_not_grow_with_clip_length(self):
        frames=ThreeFrameSet();tail=Tail(5)
        for i in range(100000): frames.add(i);tail.append(i)
        self.assertEqual(len(frames),3)
        self.assertEqual(tail,list(range(99995,100000)))

    def test_metadata_size_and_structure_are_bounded(self):
        policy=MemoryPolicy(64)
        with self.assertRaises(MemoryBudgetExceeded): policy.validate({"text":"x"*(policy.metadata_bytes+1)})
        with self.assertRaises(MemoryBudgetExceeded): policy.validate([None]*(policy.max_nodes+1))
        nested=[]
        for _ in range(30): nested=[nested]
        with self.assertRaises(MemoryBudgetExceeded): policy.validate(nested)


class SpeechTests(unittest.TestCase):
    def test_cancel_terminates_owned_decoder_process(self):
        from core.bounded_speech import decode_window
        original=subprocess.Popen;children=[]
        def sleeper(*args,**kwargs):
            child=original([sys.executable,'-c','import time; time.sleep(60)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            children.append(child);return child
        with tempfile.TemporaryDirectory() as tmp,patch('core.bounded_speech.subprocess.Popen',side_effect=sleeper):
            try:
                with self.assertRaisesRegex(RuntimeError,'cancelled'):
                    decode_window('unused',Path(tmp)/'audio.wav',0,10,lambda:False)
                self.assertIsNotNone(children[0].poll())
            finally:
                for child in children:
                    if child.poll() is None: child.kill();child.wait()

    def fixture(self, duration, records):
        from core.bounded_speech import bounded_transcribe
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        calls=[]; windows={}
        def decode(source,target,start,length,allowed):
            calls.append((start,length));windows[str(target)]=start
            return int(length*32000)
        class Model:
            def transcribe(self,path,**kwargs):
                offset=windows[path]
                result=[]
                for begin,end,text in records:
                    if begin>=offset and end<=offset+6:
                        word=types.SimpleNamespace(start=begin-offset,end=end-offset,word=text)
                        result.append(types.SimpleNamespace(start=begin-offset,end=end-offset,text=text,words=[word]))
                return iter(result),types.SimpleNamespace(language="en")
        result,info=bounded_transcribe(Model(),"unused",None,"generation",MemoryPolicy(speech_seconds=2),{},
            probe_fn=lambda p:{"duration":duration,"streams":[{"codec_type":"audio"}]},decode_fn=decode,temporary_parent=tmp.name)
        return result,info,calls,tmp.name

    def test_window_timestamps_and_word_ownership_are_not_equal_splits(self):
        records=[(.2,.7," first"),(1.8,2.2," crossing"),(3.1,3.7," last")]
        segments,info,calls,tmp=self.fixture(4,records)
        output=list(segments)
        self.assertEqual([(s.start,s.end,s.text) for s in output],[(.2,.7,"first"),(1.8,2.2,"crossing"),(3.1,3.7,"last")])
        self.assertEqual(info.bounded_stats["chunks"],2)
        self.assertTrue(all(duration<=6 for _,duration in calls))
        self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_close_releases_current_pcm_directory(self):
        segments,info,calls,tmp=self.fixture(4,[(.1,.3," hi"),(2.2,2.5," there")])
        next(segments);segments.close()
        self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_silence_is_complete_without_retaining_chunk_history(self):
        segments,info,calls,tmp=self.fixture(100,[])
        self.assertEqual(list(segments),[])
        self.assertEqual(info.bounded_stats["chunks"],50)
        self.assertLessEqual(info.bounded_stats["max_pcm_bytes"],6*32000)
        self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_invalid_crossing_without_words_fails_closed(self):
        from core.bounded_speech import bounded_transcribe
        with tempfile.TemporaryDirectory() as tmp:
            model=types.SimpleNamespace(transcribe=lambda *a,**kw:([types.SimpleNamespace(start=1.8,end=2.2,text="crossing",words=None)],types.SimpleNamespace(language="en")))
            with self.assertRaisesRegex(ValueError,"word timestamps"):
                bounded_transcribe(model,"unused",None,"generation",MemoryPolicy(speech_seconds=2),{},
                    probe_fn=lambda p:{"duration":4,"streams":[{"codec_type":"audio"}]},decode_fn=lambda *a:128000,temporary_parent=tmp)
            self.assertEqual(list(Path(tmp).iterdir()),[])


class RetentionFixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="cyne-retention-");self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.project,self.media,self.output,self.models=[self.root/p for p in ("project","originals","generated","models")]
        for p in (self.project,self.media,self.output,self.models): p.mkdir()
        self.source=self.media/"C0001.mp4";self.source.write_bytes(b"synthetic original preserved")
        self.project_file=self.project/"wedding.cyne";self.project_file.write_bytes(b'{"files":[],"custom":"keep"}')
        self.workspace=Workspace.configure(self.project,[self.media],self.output,self.models,64*1024**2)
        from core.database import Database
        self.db=Database();self.db.initialize(str(self.project));self.addCleanup(self.db.close)
        self.path=str(self.source);self.signature=source_signature(self.path)
        self.db.update_metadata_key(self.path,"editor_note","preserve unknown fields")
        self.now=time.time()+3*86400

    def publish(self, rows=1, artifact=False, fail=False, vector=None):
        generation=None
        try:
            with self.db.reprocess(self.path,"visual",self.signature) as staged:
                generation=staged.generation
                staged.add_visual_embeddings(self.path,[vector or [.1,.2,.3]]*rows,[float(i) for i in range(rows)])
                staged.save_tags(self.path,["new"],"generation "+generation)
                if artifact:
                    folder=artifact_directory(str(self.project),"proxies",generation)
                    from core.proxy_generator import _safe_stem
                    target=Path(folder)/(_safe_stem(self.path)+"_proxy.mp4")
                    target.write_bytes(("derived "+generation).encode())
                    staged.update_metadata_key(self.path,"proxy_path",str(target))
                if fail: raise RuntimeError("injected failed replacement")
        except RuntimeError:
            if not fail: raise
        return generation

    def generations(self,rows=1,artifact=False):
        return [self.publish(rows,artifact) for _ in range(4)]

    def plan(self,**kwargs):
        return retention.plan(self.db,keep_previous=1,min_age_hours=24,now=self.now,**kwargs)


class RetentionTests(RetentionFixture):
    def test_dry_run_preserves_originals_project_and_every_vector(self):
        generations=self.generations(artifact=True)
        before=self.db.visuals.raw.count()
        original=self.source.read_bytes();project=self.project_file.read_bytes()
        plan=self.plan()
        self.assertTrue(plan["dry_run"])
        self.assertEqual({c["generation"] for c in plan["candidates"]},set(generations[:2]))
        self.assertEqual(self.db.visuals.raw.count(),before)
        self.assertEqual(self.source.read_bytes(),original);self.assertEqual(self.project_file.read_bytes(),project)

    def test_quarantine_preserves_active_previous_and_legacy_then_restore(self):
        self.db.visuals.raw.upsert(ids=["legacy"],embeddings=[[.3,.2,.1]],metadatas=[{"source":self.path}])
        generations=self.generations(rows=3,artifact=True)
        plan=self.plan(); result=retention.apply(self.db,plan["run_id"],now=self.now)
        self.assertTrue(all(i["state"]=="quarantined" for i in result["items"]))
        self.assertEqual(self.db.visuals.raw.count(),7)  # current + previous + legacy
        self.assertEqual(self.db.visuals.count(),3)
        self.assertEqual(self.db.get_video_metadata(self.path)["visual_generation"],generations[-1])
        self.assertTrue(self.db.visuals.raw.get(ids=["legacy"])["ids"])
        restored=retention.restore(self.db,plan["run_id"],generations[0])
        self.assertEqual(self.db.visuals.raw.count(),10)
        self.assertEqual(self.db.visuals.count(),3)  # no rollback of current metadata
        self.assertTrue(self.db._get_conn().execute("SELECT 1 FROM generation_pins WHERE generation=?",(generations[0],)).fetchone())
        self.assertEqual(self.db.get_video_metadata(self.path)["editor_note"],"preserve unknown fields")

    def test_unknown_pre_catalog_generations_are_never_candidates(self):
        self.db.visuals.raw.upsert(ids=["old:one"],embeddings=[[.3,.2,.1]],metadatas=[{"source":self.path,"generation":"old"}])
        self.generations()
        plan=self.plan();retention.apply(self.db,plan["run_id"],now=self.now)
        self.assertEqual(self.db.visuals.raw.get(ids=["old:one"])["ids"],["old:one"])

    def test_restore_preserves_mixed_document_and_no_document_rows(self):
        with self.db.reprocess(self.path,'visual',self.signature) as staged:
            generation=staged.generation
            staged.visuals.upsert(ids=['with-text'],embeddings=[[.1,.2,.3]],metadatas=[{'timestamp':0.}],documents=['original vows'])
            staged.visuals.upsert(ids=['without-text'],embeddings=[[.1,.2,.3]],metadatas=[{'timestamp':1.}])
        for _ in range(3): self.publish()
        ids=[generation+':with-text',generation+':without-text']
        before=self.db.visuals.raw.get(ids=ids,include=['embeddings','metadatas','documents'])
        plan=self.plan();retention.apply(self.db,plan['run_id'],now=self.now)
        self.assertEqual(self.db.visuals.raw.get(ids=ids)['ids'],[])
        retention.restore(self.db,plan['run_id'])
        after=self.db.visuals.raw.get(ids=ids,include=['embeddings','metadatas','documents'])
        def records(result):
            return {row_id:(list(result['embeddings'][i]),result['metadatas'][i],result['documents'][i]) for i,row_id in enumerate(result['ids'])}
        self.assertEqual(records(after),records(before))

    def test_pinned_and_unfinished_writer_are_protected(self):
        generations=self.generations()
        retention.pin(self.db,generations[0],"reviewed selects")
        with self.db.reprocess(self.path,"visual",self.signature) as staged:
            protected=self.plan()
            self.assertNotIn(staged.generation,{c["generation"] for c in protected["candidates"]})
            self.assertIn(staged.generation,{k["generation"] for k in protected["protected"]})
            self.assertNotIn(generations[0],{c["generation"] for c in protected["candidates"]})

    def test_grace_period_and_minimum_history_are_enforced(self):
        self.generations()
        plan=retention.plan(self.db,now=time.time())
        self.assertEqual(plan["candidates"],[])
        for keep,age in ((0,0),(1,-1),(1,float("nan"))):
            with self.assertRaises(ValueError): retention.plan(self.db,keep,age)

    def test_new_publication_invalidates_saved_plan_without_deleting(self):
        self.generations();plan=self.plan();self.publish()
        before=self.db.visuals.raw.count()
        with self.assertRaisesRegex(RuntimeError,"stale"): retention.apply(self.db,plan["run_id"],now=self.now)
        self.assertEqual(self.db.visuals.raw.count(),before)

    def test_legacy_or_unknown_files_in_generation_directory_are_untouched(self):
        generations=self.generations(artifact=True)
        # An unregistered note beside a tracked derivative is never recursively removed.
        known=self.db._get_conn().execute("SELECT path FROM generation_artifacts WHERE generation=?",(generations[0],)).fetchone()[0]
        extra=Path(known).parent/"editor-notes.txt";extra.write_text("keep me")
        plan=self.plan();retention.apply(self.db,plan["run_id"],now=self.now)
        retention.purge(self.db,plan["run_id"],now=self.now+8*86400)
        self.assertEqual(extra.read_text(),"keep me")

    def test_archive_failure_never_deletes_live_vectors(self):
        self.generations();plan=self.plan();before=self.db.visuals.raw.count()
        with patch('core.retention.zlib.compress',side_effect=OSError("archive disk full")):
            with self.assertRaisesRegex(OSError,"disk full"): retention.apply(self.db,plan["run_id"],now=self.now)
        self.assertEqual(self.db.visuals.raw.count(),before)

    def test_partial_vector_deletion_is_recoverable_and_retryable(self):
        generations=self.generations(rows=130)
        plan=self.plan();raw=self.db.visuals.raw;original=raw.delete;calls=0
        def fail(ids):
            nonlocal calls
            calls+=1
            if calls==2: raise RuntimeError("delete interrupted")
            return original(ids=ids)
        class Faulty:
            def __getattr__(self,name): return getattr(raw,name)
            def delete(self,ids): return fail(ids)
        with patch.object(self.db.visuals,'raw',Faulty()):
            with self.assertRaisesRegex(RuntimeError,"interrupted"): retention.apply(self.db,plan["run_id"],now=self.now)
        self.assertEqual(self.db.visuals.count(),130)
        retention.apply(self.db,plan["run_id"],now=self.now)
        self.assertEqual(raw.count(),260)
        retention.restore(self.db,plan["run_id"],generations[0])
        self.assertEqual(raw.count(),390)

    def test_file_move_failure_leaves_verified_recovery_archive(self):
        generations=self.generations(artifact=True);plan=self.plan()
        with patch('core.retention.os.replace',side_effect=OSError("move interrupted")):
            with self.assertRaisesRegex(OSError,"interrupted"): retention.apply(self.db,plan["run_id"],now=self.now)
        retention.restore(self.db,plan["run_id"])
        self.assertEqual(self.db.visuals.raw.count(),4)

    def test_purge_requires_cooling_period_and_rechecks_pins(self):
        generations=self.generations(artifact=True);plan=self.plan()
        retention.apply(self.db,plan["run_id"],now=self.now)
        with self.assertRaisesRegex(RuntimeError,"cooling"): retention.purge(self.db,plan["run_id"],now=self.now+86400)
        retention.pin(self.db,generations[0],"keep export")
        with self.assertRaisesRegex(RuntimeError,"pinned"): retention.purge(self.db,plan["run_id"],now=self.now+8*86400)
        retention.unpin(self.db,generations[0])
        result=retention.purge(self.db,plan["run_id"],now=self.now+8*86400)
        self.assertTrue(all(i["state"]=="purged" for i in result["items"]))
        with self.assertRaisesRegex(RuntimeError,"Purged"): retention.restore(self.db,plan["run_id"])

    def test_corrupted_archive_is_not_restored_or_used_for_deletion(self):
        self.generations();plan=self.plan();retention.apply(self.db,plan["run_id"],now=self.now)
        self.db._get_conn().execute("UPDATE retention_vectors SET payload=? WHERE run_id=?",(b"corrupt",plan["run_id"]));self.db._get_conn().commit()
        with self.assertRaises(Exception): retention.restore(self.db,plan["run_id"])
        self.assertEqual(self.db.visuals.count(),1)

    def test_symlink_artifact_is_preserved_and_generation_not_selected(self):
        generations=self.generations(artifact=True)
        old=self.db._get_conn().execute("SELECT path FROM generation_artifacts WHERE generation=?",(generations[0],)).fetchone()[0]
        Path(old).unlink();Path(old).symlink_to(self.source)
        plan=self.plan()
        self.assertNotIn(generations[0],{c["generation"] for c in plan["candidates"]})
        self.assertEqual(self.source.read_bytes(),b"synthetic original preserved")

    def test_active_reader_finishes_before_retention_can_delete(self):
        self.generations();plan=self.plan();entered=threading.Event();release=threading.Event();deleted=threading.Event()
        raw=self.db.visuals.raw;get=raw.get;delete=raw.delete;read_result=[];errors=[]
        def blocking_get(*args,**kwargs):
            entered.set();release.wait(5);return get(*args,**kwargs)
        def mark_delete(*args,**kwargs): deleted.set();return delete(*args,**kwargs)
        def reader():
            try: read_result.append(self.db.visuals.get(include=["metadatas"]))
            except Exception as exc: errors.append(exc)
        def cleanup():
            try: retention.apply(self.db,plan["run_id"],now=self.now)
            except Exception as exc: errors.append(exc)
        class Observed:
            def __getattr__(self,name): return getattr(raw,name)
            def get(self,*args,**kwargs): return blocking_get(*args,**kwargs)
            def delete(self,*args,**kwargs): return mark_delete(*args,**kwargs)
        with patch.object(self.db.visuals,'raw',Observed()):
            first=threading.Thread(target=reader);first.start();self.assertTrue(entered.wait(5))
            second=threading.Thread(target=cleanup);second.start();time.sleep(.05)
            self.assertFalse(deleted.is_set());release.set()
            first.join(10);second.join(10)
            self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual(len(read_result[0]["ids"]),1)

    def test_over_budget_stage_does_not_replace_legacy_metadata(self):
        before=self.db.get_video_metadata(self.path)
        with self.assertRaises(MemoryBudgetExceeded):
            with self.db.reprocess(self.path,"visual",self.signature) as staged:
                staged.update_metadata_key(self.path,"oversized","x"*(MemoryPolicy().metadata_bytes+1))
        self.assertEqual(self.db.get_video_metadata(self.path),before)

    def test_existing_oversized_project_remains_readable_but_not_reprocessed(self):
        self.db.update_metadata_key(self.path,"custom_notes","x"*(MemoryPolicy().metadata_bytes+1))
        with self.assertRaises(MemoryBudgetExceeded): self.db.reprocess(self.path,"visual",self.signature)
        self.assertEqual(len(self.db.get_video_metadata(self.path)["custom_notes"]),MemoryPolicy().metadata_bytes+1)

    def test_staged_writer_cannot_mutate_a_published_generation(self):
        with self.db.reprocess(self.path,"visual",self.signature) as staged:
            staged.add_visual_embeddings(self.path,[[.1,.2,.3]],[0.])
        with self.assertRaisesRegex(RuntimeError,"live context"):
            staged.add_visual_embeddings(self.path,[[.1,.2,.3]],[1.])
        self.assertEqual(self.db.visuals.count(),1)

    def test_unfinished_job_result_pins_its_generation(self):
        from core.jobs import JobStore
        generations=self.generations()
        store=JobStore(self.project);job=store.submit([self.path],["index_visuals"])
        store.claim(job,"owner");item=store.status(job)["items"][0]
        store.begin_item(job,item["id"],"owner")
        store.finish_item(job,item["id"],"owner","completed",result={"generation":generations[0]})
        store.control(job,"pause");store.release(job,"owner","paused")
        self.assertNotIn(generations[0],{c["generation"] for c in self.plan()["candidates"]})

    def test_missing_archive_row_blocks_restore(self):
        self.generations(rows=3);plan=self.plan();retention.apply(self.db,plan["run_id"],now=self.now)
        conn=self.db._get_conn()
        conn.execute("DELETE FROM retention_vectors WHERE rowid=(SELECT min(rowid) FROM retention_vectors WHERE run_id=?)",(plan["run_id"],));conn.commit()
        with self.assertRaisesRegex(RuntimeError,"manifest"):
            retention.restore(self.db,plan["run_id"])
        self.assertEqual(self.db.visuals.count(),3)

    def test_unavailable_collection_cannot_be_silently_collected(self):
        self.generations();old=self.db.temporal_sequences
        self.db.temporal_sequences=None
        try:
            plan=self.plan()
            self.assertEqual(plan["candidates"],[])
            self.assertTrue(any("unavailable" in p["reason"] for p in plan["protected"]))
        finally: self.db.temporal_sequences=old

    def test_registered_artifact_reference_from_other_metadata_is_protected(self):
        generations=self.generations(artifact=True)
        path=self.db._get_conn().execute("SELECT path FROM generation_artifacts WHERE generation=?",(generations[0],)).fetchone()[0]
        self.db.update_metadata_key("offline-other-camera.mp4","thumbnail_path",path)
        self.assertNotIn(generations[0],{c["generation"] for c in self.plan()["candidates"]})

    def test_unicode_metadata_budget_matches_published_encoding(self):
        with self.db.reprocess(self.path,"transcript",self.signature) as staged:
            staged.save_transcript(self.path,[{"start":0.,"end":1.,"text":"வணக்கம் "*2000}])
        value=self.db.get_bounded_video_metadata(self.path,MemoryPolicy())
        self.assertEqual(value["transcript"][0]["text"],"வணக்கம் "*2000)

    def test_bounded_query_fallback_preserves_recall_filters_and_distance(self):
        self.generations(rows=100)
        raw=self.db.visuals.raw
        class BrokenANN:
            def __getattr__(self,name): return getattr(raw,name)
            def query(self,**kwargs): raise RuntimeError("Cannot return the results in a contigious 2D array")
        with patch.object(self.db.visuals,'raw',BrokenANN()):
            result=self.db.visuals.query(query_embeddings=[[.1,.2,.3],[1.,0.,0.]],n_results=8,
                where={"source":self.path},include=["metadatas","distances"])
            self.assertEqual([len(batch) for batch in result["ids"]],[8,8])
            self.assertTrue(all(abs(d)<1e-6 for d in result["distances"][0]))
            self.assertTrue(all(m["generation"]==self.db.get_video_metadata(self.path)["visual_generation"] for batch in result["metadatas"] for m in batch))
            self.assertEqual(self.db.visuals.last_query_diagnostics["mode"],"paged_exact")
            self.assertEqual(self.db.visuals.last_query_diagnostics["retained_results"],16)

    def test_exact_query_and_count_use_bounded_pages(self):
        self.generations(rows=100)
        raw=self.db.visuals.raw;pages=[]
        class Observed:
            def __getattr__(self,name): return getattr(raw,name)
            def get(self,**kwargs): pages.append(kwargs.get("limit"));return raw.get(**kwargs)
            def query(self,**kwargs): raise RuntimeError("contiguous")
        with patch.object(self.db.visuals,'raw',Observed()):
            self.assertEqual(self.db.visuals.count(),100)
            self.db.visuals.query(query_embeddings=[[.1,.2,.3]],n_results=8)
        self.assertTrue(pages)
        self.assertTrue(all(p==64 for p in pages))

    def test_exact_query_rejects_unbounded_or_nonfinite_requests(self):
        self.generations(rows=100)
        raw=self.db.visuals.raw
        class BrokenANN:
            def __getattr__(self,name): return getattr(raw,name)
            def query(self,**kwargs): raise RuntimeError("contiguous")
        with patch.object(self.db.visuals,'raw',BrokenANN()):
            with self.assertRaises(ValueError): self.db.visuals.query(query_embeddings=[[.1,.2,.3]],n_results=2049)
            with self.assertRaises(ValueError): self.db.visuals.query(query_embeddings=[[float('nan'),.2,.3]],n_results=2)

    def test_future_generation_schema_is_rejected(self):
        self.db._get_conn().execute("UPDATE generation_schema SET version=99");self.db._get_conn().commit()
        before=self.db.get_video_metadata(self.path)
        with self.assertRaisesRegex(RuntimeError,"Unsupported"): retention.initialize(self.db)
        self.assertEqual(self.db.get_video_metadata(self.path),before)


class RetentionProcessTests(unittest.TestCase):
    def test_process_death_mid_delete_can_resume_and_restore(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='cyne-gc-kill-') as tmp:
            base=Path(tmp);project,media,output,models=[base/p for p in ('project','media','output','models')]
            for p in (project,media,output,models): p.mkdir()
            source=media/'C0001.mp4';source.write_bytes(b'preserved synthetic original')
            (project/'wedding.cyne').write_bytes(b'{"files":[],"keep":"project"}')
            Workspace.configure(project,[media],output,models,64*1024**2)
            marker=base/'during-delete.json'
            code='''
from pathlib import Path
import json,sys,time
from core.database import Database
from core.source_state import source_signature
from core import retention
db=Database();db.initialize(sys.argv[1]);source=sys.argv[2]
generations=[]
for n in range(4):
 with db.reprocess(source,'visual',source_signature(source)) as stage:
  generations.append(stage.generation)
  stage.add_visual_embeddings(source,[[.1,.2,.3]]*130,[float(i) for i in range(130)])
  stage.save_tags(source,['new'],'new')
plan=retention.plan(db,keep_previous=1,min_age_hours=0)
raw=db.visuals.raw
class Interrupted:
 def __getattr__(self,name): return getattr(raw,name)
 def delete(self,ids):
  raw.delete(ids=ids)
  Path(sys.argv[3]).write_text(json.dumps({'run_id':plan['run_id'],'generation':generations[0]}))
  time.sleep(60)
db.visuals.raw=Interrupted()
retention.apply(db,plan['run_id'])
'''
            child=subprocess.Popen([sys.executable,'-c',code,str(project),str(source),str(marker)],cwd=root,
                                   stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+20
                while not marker.exists() and child.poll() is None and time.monotonic()<deadline: time.sleep(.02)
                self.assertTrue(marker.exists(),child.stderr.read() if child.poll() is not None else 'child timeout')
                details=json.loads(marker.read_text());child.kill();child.wait(timeout=5)
            finally:
                if child.poll() is None: child.kill();child.wait()
                child.stderr.close()
            command=[sys.executable,'-m','cyne_cli','--project',str(project),'retention']
            applied=subprocess.run(command+['apply',details['run_id']],cwd=root,capture_output=True,text=True,timeout=30)
            self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr)
            self.assertTrue(all(i['state']=='quarantined' for i in json.loads(applied.stdout)['items']))
            restored=subprocess.run(command+['restore',details['run_id'],'--generation',details['generation']],cwd=root,capture_output=True,text=True,timeout=30)
            self.assertEqual(restored.returncode,0,restored.stdout+restored.stderr)
            self.assertEqual(source.read_bytes(),b'preserved synthetic original')
            self.assertEqual((project/'wedding.cyne').read_bytes(),b'{"files":[],"keep":"project"}')


if __name__=='__main__': unittest.main()
