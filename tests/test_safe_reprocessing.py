"""Storage publication/recovery tests, plus source-extracted worker timing tests.

Run separately from smoke_search. Optional real Chroma tests run when installed.
No AI models or wedding footage are used.
"""
import ast
import contextlib
import copy
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

from core.generations import PublishedCollection, ReprocessingAborted
from core.scene_timing import sampled_time, scene_segments
from core.source_state import source_signature

ROOT = Path(__file__).resolve().parents[1]


class Collection:
    def __init__(self):
        self.records = {}
        self.fail = False

    def upsert(self, ids, embeddings, metadatas, **kw):
        for key, vector, meta in zip(ids, embeddings, metadatas):
            self.records[key] = (vector, copy.deepcopy(meta))
            if self.fail:
                raise RuntimeError('Vector disk full after partial write')

    def count(self):
        return len(self.records)

    def get(self, include=None, where=None, **kwargs):
        pairs = [(k, v) for k, v in self.records.items() if not where or all(v[1].get(a) == b for a,b in where.items())]
        offset=kwargs.get('offset',0);limit=kwargs.get('limit')
        pairs=pairs[offset:] if limit is None else pairs[offset:offset+limit]
        result = {'ids': [p[0] for p in pairs]}
        for name in include or []:
            result[name] = [v[1] if name == 'metadatas' else v[0] if name == 'embeddings' else None for _, v in pairs]
        return result

    def query(self, n_results=10, include=None, **kwargs):
        result = self.get(include=[k for k in include if k != 'distances'], where=kwargs.get('where'))
        result = {k: [v[:n_results]] for k, v in result.items()}
        if 'distances' in include:
            result['distances'] = [[0.1] * len(result['ids'][0])]
        return result


def database_module(chroma=None):
    spec = importlib.util.spec_from_file_location('safe_database', ROOT/'core/database.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'chromadb': chroma or types.ModuleType('chromadb')}):
        spec.loader.exec_module(module)
    return module


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name)/'Camera A'/'C0001.MP4')
        Path(self.path).parent.mkdir()
        Path(self.path).write_bytes(b'original footage')
        self.sig = source_signature(self.path)
        self.module = database_module()
        self.db = self.module.Database()
        self.db.sqlite_path = str(Path(self.temp.name)/'metadata.db')
        self.db._init_sqlite()
        self.addCleanup(self.db.close)
        for name,stage in [('visuals','visual'),('temporal_sequences','visual'),('transcripts','transcript')]:
            setattr(self.db, name, PublishedCollection(Collection(), self.db, stage))
        self.db.save_tags(self.path, ['old wedding'], 'original summary')
        self.db.visuals.upsert(ids=['legacy'], embeddings=[[1.,0.]], metadatas=[{'source': self.path, 'timestamp': 1.}])
        self.before = self.db.get_video_metadata(self.path)

    def stage(self, **kwargs):
        return self.db.reprocess(self.path, 'visual', self.sig, **kwargs)

    def assert_old(self):
        self.assertEqual(self.db.get_video_metadata(self.path), self.before)
        self.assertEqual(self.db.visuals.get()['ids'], ['legacy'])

    def test_staged_vectors_hidden_and_success_publishes_metadata_together(self):
        with self.stage() as staged:
            staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
            staged.save_tags(self.path, ['new wedding'], 'new summary')
            self.assert_old()
        self.assertEqual(self.db.get_video_metadata(self.path)['tags'], ['new wedding'])
        self.assertEqual(self.db.visuals.get()['metadatas'][0]['timestamp'], 8.)
        self.assertIn('legacy', self.db.visuals.raw.records)  # retained for earlier readers

    def test_exception_retains_legacy_project_and_index(self):
        with self.assertRaisesRegex(RuntimeError, 'inference'):
            with self.stage() as staged:
                staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
                staged.save_tags(self.path, ['partial'], 'partial')
                raise RuntimeError('inference failed')
        self.assert_old()

    def test_cancellation_retains_previous_generation(self):
        with self.assertRaises(ReprocessingAborted):
            with self.stage(allowed=lambda: False) as staged:
                staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
        self.assert_old()

    def test_partial_vector_failure_never_becomes_searchable(self):
        self.db.visuals.raw.fail = True
        with self.assertRaises(RuntimeError):
            with self.stage() as staged:
                staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
        self.assert_old()

    def test_temporal_write_failure_aborts_publication(self):
        self.db.temporal_sequences.raw.fail = True
        with self.assertRaises(RuntimeError):
            with self.stage() as staged:
                staged.save_tags(self.path, ['partial'], 'partial')
                staged.add_temporal_sequence(self.path, [0.,1.], 2., 8.)
        self.assert_old()

    def test_actual_sqlite_commit_failure_keeps_previous_index(self):
        self.db._get_conn().execute("CREATE TRIGGER reject_update BEFORE UPDATE ON video_metadata BEGIN SELECT RAISE(ABORT, 'disk full'); END")
        with self.assertRaises(Exception):
            with self.stage() as staged:
                staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
                staged.save_tags(self.path, ['new'], 'new')
        self.assert_old()

    def test_missing_or_modified_source_cannot_publish(self):
        for missing in [False, True]:
            with self.subTest(missing=missing), self.assertRaises(ReprocessingAborted):
                with self.stage() as staged:
                    staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
                    if missing:
                        Path(self.path).unlink()
                    else:
                        Path(self.path).write_bytes(b'changed source')
            self.assert_old()

    def test_concurrent_stage_cannot_overwrite_first_publication(self):
        first, second = self.stage(), self.stage()
        first.__enter__(); second.__enter__()
        first.save_tags(self.path, ['first'], 'first')
        first.__exit__(None,None,None)
        with self.assertRaises(ReprocessingAborted):
            second.__exit__(None,None,None)
        self.assertEqual(self.db.get_video_metadata(self.path)['tags'], ['first'])

    def test_reopen_hides_abandoned_vectors_without_migration(self):
        abandoned = self.stage()
        abandoned.__enter__()
        abandoned.add_visual_embeddings(self.path, [[0.,1.]], [8.])
        # Simulated process death before __exit__: no compensating cleanup.
        self.db.close()
        self.db._local = threading.local()
        self.assert_old()

    def test_query_widens_past_inactive_nearest_neighbors(self):
        with self.stage() as staged:
            staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
        result = self.db.visuals.query(query_embeddings=[[1.,0.]], n_results=1, include=['distances'])
        self.assertEqual(len(result['ids'][0]), 1)
        self.assertNotEqual(result['ids'][0], ['legacy'])
        self.assertNotIn('metadatas', result)
        self.assertEqual(len(result['distances'][0]), 1)

    def test_clear_is_a_recoverable_metadata_tombstone(self):
        self.db.clear_metadata_keys(self.path, ['tags'])
        self.assertEqual(self.db.visuals.count(), 0)
        self.assertIn('legacy', self.db.visuals.raw.records)

    def test_reader_snapshot_and_unknown_metadata_survive_publication(self):
        self.db.update_metadata_key(self.path, 'custom_editor_note', {'keep': True})
        snapshot = self.db.visuals._snapshot()
        with self.stage() as staged:
            staged.add_visual_embeddings(self.path, [[0.,1.]], [8.])
        self.assertEqual(self.db.get_video_metadata(self.path)['custom_editor_note'], {'keep':True})
        with patch.object(self.db.visuals, '_snapshot', return_value=snapshot):
            self.assertEqual(self.db.visuals.query(query_embeddings=[[1.,0.]], n_results=1)['ids'], [['legacy']])

    def test_failed_transcript_replacement_retains_text_translation_and_vectors(self):
        self.db.update_metadata_key(self.path, 'transcript', [{'text': 'old vows'}])
        self.db.update_metadata_key(self.path, 'transcript_translated', [{'text': 'old translation'}])
        self.db.transcripts.upsert(ids=['old-dialogue'], embeddings=[[1.,0.]], metadatas=[{'source':self.path}])
        with self.assertRaises(RuntimeError):
            with self.db.reprocess(self.path, 'transcript', self.sig) as staged:
                staged.save_transcript(self.path, [{'text':'new vows'}])
                staged.transcripts.upsert(ids=['new'], embeddings=[[0.,1.]], metadatas=[{'text':'new vows'}])
                raise RuntimeError('embedding failed')
        self.assertEqual(self.db.get_video_metadata(self.path)['transcript'], [{'text':'old vows'}])
        self.assertIn('transcript_translated', self.db.get_video_metadata(self.path))
        self.assertEqual(self.db.transcripts.get()['ids'], ['old-dialogue'])

    def test_successful_transcript_invalidates_old_translation_and_vectors_logically(self):
        self.db.update_metadata_key(self.path,'transcript_translated',[{'text':'old translation'}])
        self.db.transcripts.upsert(ids=['old-dialogue'],embeddings=[[1.,0.]],metadatas=[{'source':self.path}])
        self.db.save_transcript(self.path,[{'text':'new vows'}],self.sig)
        self.assertNotIn('transcript_translated',self.db.get_video_metadata(self.path))
        self.assertEqual(self.db.transcripts.count(),0)
        self.assertIn('old-dialogue',self.db.transcripts.raw.records)


class TimingTests(unittest.TestCase):
    def test_uneven_intervals_and_representative_frames(self):
        scenes=[{'start':0,'end':2,'frame_time':1.5,'frame_num':3},
                {'start':2,'end':8,'frame_time':6.5,'cut_lower_bound':1.5},
                {'start':8,'frame_time':9,'cut_lower_bound':7.5}]
        segments=scene_segments(scenes,10,.5)
        self.assertEqual([s['duration'] for s in segments],[2,6,2])
        self.assertEqual(segments[1]['representative_timestamp'],6.5)
        self.assertEqual(segments[2]['cut_lower_bound'],7.5)
        self.assertEqual(segments[2]['precision'],'sampled')

    def test_decoder_pts_preferred_for_variable_frame_times(self):
        self.assertEqual(sampled_time(100,25,4250,4.),(4.25,'decoder_pts'))

    def test_unavailable_pts_fallback_is_labelled(self):
        self.assertEqual(sampled_time(100,25,0,3.5),(4.,'estimated_cfr'))

    def test_invalid_or_non_monotonic_times_rejected(self):
        with self.assertRaises(ValueError): sampled_time(1,0,float('nan'))
        with self.assertRaises(ValueError): sampled_time(1,25,0,5.)
        with self.assertRaises(ValueError): scene_segments([{'start':8,'end':2}],10,.5)


class RealChromaTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('chromadb'), 'Install Chroma in isolated test environment')
    def test_real_persistent_store_publication_failure_reopen_and_query(self):
        import chromadb
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'C0001.mp4'); Path(path).write_bytes(b'fixture')
            module=database_module(chromadb); db=module.Database(); db.initialize(tmp)
            try:
                sig=source_signature(path)
                db.save_tags(path,['old'],'old')
                db.visuals.upsert(ids=['old'],embeddings=[[1.,0.,0.]],metadatas=[{'source':path,'timestamp':0.}])
                with self.assertRaises(RuntimeError):
                    with db.reprocess(path,'visual',sig) as staged:
                        staged.add_visual_embeddings(path,[[0.,1.,0.]],[3.])
                        raise RuntimeError('power interruption')
                db.close(); db.initialize(tmp)
                self.assertEqual(db.visuals.query(query_embeddings=[[0.,1.,0.]],n_results=1)['ids'],[['old']])
                with db.reprocess(path,'visual',sig) as staged:
                    staged.add_visual_embeddings(path,[[0.,1.,0.]],[3.])
                    staged.save_tags(path,['new'],'new')
                self.assertEqual(db.visuals.count(),1)
                self.assertEqual(db.visuals.query(query_embeddings=[[1.,0.,0.]],n_results=1)['metadatas'][0][0]['timestamp'],3.)
                db.close(); db.initialize(tmp)
                self.assertEqual(db.get_video_metadata(path)['tags'],['new'])
                self.assertEqual(db.visuals.get()['metadatas'][0]['timestamp'],3.)
            finally:
                db.close()



class WorkerTimingTests(unittest.TestCase):
    setUp = PublicationTests.setUp

    def harness(self, cv):
        from collections import defaultdict
        class Signal:
            def __init__(self): self.events=[]
            def emit(self,*args): self.events.append(args)
        class Inputs(dict):
            def to(self,*args): return self
        class CaptionProcessor:
            def __call__(self,**kw): return Inputs()
            def batch_decode(self,*args,**kw): return ['a photo of wedding guests celebrating']
        class Logger:
            def __getattr__(self,name): return lambda *a,**kw: None
        processor=CaptionProcessor()
        ai=types.SimpleNamespace(device='cpu',load_clip=lambda:(None,None),
            load_blip=lambda:(types.SimpleNamespace(generate=lambda **kw: []),processor),
            load_yolo=lambda: None,unload_models=lambda **kw:None)
        tree=ast.parse((ROOT/'workers/indexer.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='IndexerWorker')
        names=['_run_indexing','_index_file','_flush_db_batch','calculate_histogram']
        funcs=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
        ns=dict(os=os,time=time,cv2=cv,np=types.SimpleNamespace(isfinite=math.isfinite),
            Image=types.SimpleNamespace(fromarray=lambda frame:object()),
            torch=types.SimpleNamespace(no_grad=contextlib.nullcontext),defaultdict=defaultdict,
            logger=Logger(),source_signature=source_signature,sampled_time=sampled_time,
            make_scene_segments=scene_segments,AIBackend=lambda:ai,Database=lambda path:self.db,
            get_tag_bank=lambda:[],log_memory_usage=lambda *args:None)
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'workers/indexer.py','exec'),ns)
        worker=type('Worker',(),{name:ns[name] for name in names})()
        worker.file_paths=[self.path]; worker.project_path=self.temp.name
        worker.mode='speed'; worker.is_running=True; worker.errors=[]
        worker.batch_size=128; worker.max_interval=5.; worker.min_interval=1.
        worker.blur_threshold=50.; worker.scene_threshold=.6
        worker.min_frames_for_tag=1; worker.tag_threshold_percent=.2
        for name in ['progress_signal','log_signal','summary_signal']: setattr(worker,name,Signal())
        worker.calculate_sharpness=lambda frame:100.
        worker._resize_for_ai=lambda image,size:image
        def process(images,timestamps,ai,db,path,*args):
            db.add_visual_embeddings(path,[[0.,1.] for _ in timestamps],timestamps)
        worker.process_batch=process
        config=types.ModuleType('config'); config.USE_BLIP2=False; config.get_setting=lambda *args:False
        return worker,config

    def fake_cv(self, cancel=None, fail_at=None):
        owner=self
        class Capture:
            def __init__(self): self.position=0; self.last=0; self.released=False
            def isOpened(self): return True
            def set(self,prop,value): self.position=value; return True
            def get(self,prop):
                return {'fps':2.,'count':20,'msec':self.last*500.,'frames':self.last+1}[prop]
            def read(self):
                self.last=self.position
                if cancel: cancel(self.last)
                if self.last==fail_at: return False,None
                return True,self.last
            def release(self): self.released=True
        cap=Capture(); self.capture=cap
        cv=types.SimpleNamespace(VideoCapture=lambda path:cap,CAP_PROP_FPS='fps',CAP_PROP_FRAME_COUNT='count',
            CAP_PROP_POS_FRAMES='frames',CAP_PROP_POS_MSEC='msec',COLOR_BGR2RGB='rgb',
            HISTCMP_CORREL='hist',cvtColor=lambda frame,kind:frame,
            compareHist=lambda a,b,kind:1. if a==b else 0.)
        return cv

    def run_fake(self, cancel=None, fail_at=None):
        worker,config=self.harness(self.fake_cv(cancel,fail_at))
        worker.calculate_histogram=lambda frame:0 if frame<4 else 1 if frame<16 else 2
        with patch.dict(sys.modules,{'config':config}),contextlib.redirect_stdout(io.StringIO()):
            worker._run_indexing()
        return worker

    def test_actual_worker_records_uneven_cuts_and_caption_frame_times(self):
        self.db.update_metadata_key(self.path, 'proxy_path', 'old-source-proxy.mp4')
        worker=self.run_fake()
        self.assertEqual(worker.errors,[])
        meta=self.db.get_video_metadata(self.path)
        self.assertEqual([s['end'] for s in meta['scene_segments']],[2.,8.,10.])
        self.assertEqual([s['representative_timestamp'] for s in meta['scene_segments']],[0.,2.,8.])
        self.assertEqual([d['timestamp'] for d in meta['scene_descriptions']],[0.,2.,8.])
        self.assertNotIn('proxy_path', meta)
        self.assertTrue(self.capture.released)
        self.assertEqual(len(worker.summary_signal.events),1)

    def test_decode_failure_keeps_old_index_and_emits_no_success(self):
        worker=self.run_fake(fail_at=3)
        self.assertTrue(worker.errors)
        PublicationTests.assert_old(self)
        self.assertEqual(worker.summary_signal.events,[])
        self.assertNotIn((100,),worker.progress_signal.events)
        self.assertTrue(self.capture.released)

    def test_objects_use_representative_frame_time_not_scene_start(self):
        cv = self.fake_cv()
        cv.compareHist = lambda a,b,kind: .7 if a[1] == b[1] else 0.
        worker,config = self.harness(cv)
        worker.calculate_histogram = lambda frame: (frame, 0 if frame<4 else 1 if frame<16 else 2)
        worker.calculate_sharpness = lambda frame: 1000. if frame == 6 else 100.
        box = types.SimpleNamespace(conf=[.9], cls=[0], xyxyn=[types.SimpleNamespace(tolist=lambda: [0.,0.,1.,1.])])
        prediction = types.SimpleNamespace(boxes=[box], names={0:'person'})
        ai = worker._run_indexing.__func__.__globals__['AIBackend']()
        ai.load_yolo = lambda: (lambda *args, **kwargs: [prediction])
        with patch.dict(sys.modules, {'config':config}), contextlib.redirect_stdout(io.StringIO()):
            worker._run_indexing()
        self.assertEqual(worker.errors, [])
        meta = self.db.get_video_metadata(self.path)
        self.assertEqual(meta['scene_segments'][1]['start'], 2.)
        self.assertEqual(meta['objects_yolo'][1]['timestamp'], 3.)
        self.assertEqual(meta['scene_descriptions'][1]['timestamp'], 3.)

    def test_requested_proxy_failure_keeps_existing_metadata_and_vectors(self):
        worker,config=self.harness(self.fake_cv())
        worker.calculate_histogram=lambda frame:0
        config.get_setting=lambda key,*args:key=='generate_proxies'
        worker._index_file.__func__.__globals__['generate_proxy']=lambda *args,**kwargs:None
        with patch.dict(sys.modules,{'config':config}), \
             patch('core.workspace.artifact_directory', return_value=self.temp.name), \
             contextlib.redirect_stdout(io.StringIO()): worker._run_indexing()
        self.assertTrue(worker.errors)
        self.assertIn('Requested proxy failed', worker.errors[0])
        PublicationTests.assert_old(self)
        self.assertEqual(worker.summary_signal.events,[])

    def test_cancelled_worker_does_not_publish_or_emit_100(self):
        worker,config=self.harness(self.fake_cv())
        worker.calculate_histogram=lambda frame:0
        original_read=self.capture.read
        def read():
            result=original_read()
            if self.capture.last==3: worker.is_running=False
            return result
        self.capture.read=read
        with patch.dict(sys.modules,{'config':config}),contextlib.redirect_stdout(io.StringIO()): worker._run_indexing()
        PublicationTests.assert_old(self)
        self.assertEqual(worker.summary_signal.events,[])
        self.assertNotIn((100,),worker.progress_signal.events)
        self.assertTrue(self.capture.released)

    @unittest.skipUnless(importlib.util.find_spec('cv2'), 'Install OpenCV for real generated-video check')
    def test_real_mac_decoder_uneven_video_scene_times(self):
        import cv2
        import numpy as np
        self.path=str(Path(self.temp.name)/'uneven.avi')
        writer=cv2.VideoWriter(self.path,cv2.VideoWriter_fourcc(*'MJPG'),2.,(32,32))
        self.assertTrue(writer.isOpened())
        for i in range(20):
            color=(0,0,255) if i<4 else (0,255,0) if i<16 else (255,0,0)
            frame=np.zeros((32,32,3),dtype=np.uint8); frame[:]=color; writer.write(frame)
        writer.release()
        worker,config=self.harness(cv2)
        with patch.dict(sys.modules,{'config':config}),contextlib.redirect_stdout(io.StringIO()): worker._run_indexing()
        self.assertEqual(worker.errors,[])
        meta=self.db.get_video_metadata(self.path)
        self.assertEqual([s['end'] for s in meta['scene_segments']],[2.,8.,10.])
        self.assertEqual(meta['source_timing']['timestamp_methods'],['decoder_pts'])



class TranscriptionPublicationTests(unittest.TestCase):
    setUp = PublicationTests.setUp

    def harness(self, mode='speed'):
        from core.source_state import needs_processing
        class Signal:
            def __init__(self): self.events=[]
            def emit(self,*args): self.events.append(args)
        class Logger:
            def __getattr__(self,name): return lambda *a,**kw:None
        model=types.SimpleNamespace(transcribe=lambda *a,**kw: (
            [types.SimpleNamespace(start=0.,end=1.,text='I promise always.')],types.SimpleNamespace(language='en')))
        def unavailable(): raise RuntimeError('CLIP inference unavailable')
        ai=types.SimpleNamespace(load_whisper=lambda:model,get_whisper_params=lambda mode:('small','cpu','int8'),
            clip_model=None,clip_processor=None,load_clip=unavailable,unload_models=lambda:None)
        source=ast.parse((ROOT/'workers/transcriber.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='TranscriberWorker')
        names=['_run_transcription','_transcribe_file']
        functions=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
        ns=dict(os=os,time=time,AIBackend=lambda:ai,Database=lambda path:self.db,
                source_signature=source_signature,needs_processing=needs_processing,get_whisper_language_hint=lambda:None)
        exec(compile(ast.Module(body=functions,type_ignores=[]),'workers/transcriber.py','exec'),ns)
        worker=type('Worker',(),{name:ns[name] for name in names})()
        worker.mode=mode; worker.file_paths=[self.path]; worker.project_path=self.temp.name
        worker.is_running=True; worker.errors=[]
        for name in ['log_signal','progress_signal','file_finished_signal']: setattr(worker,name,Signal())
        whisper=types.ModuleType('faster_whisper'); whisper.WhisperModel=lambda *args,**kw:model
        def bounded(model,path,project,generation,policy,kwargs,allowed):
            segments,info=model.transcribe(path,**kwargs)
            info.languages={info.language}; info.bounded_stats={}
            def streamed():
                yield from segments
            return streamed(),info
        patcher=patch('core.bounded_speech.bounded_transcribe',side_effect=bounded)
        patcher.start(); self.addCleanup(patcher.stop)
        return worker,model,whisper

    def test_speech_success_publishes_transcript_then_success_signal(self):
        worker,model,whisper=self.harness()
        with patch.dict(sys.modules,{'faster_whisper':whisper}): worker._run_transcription()
        self.assertEqual(worker.errors,[])
        meta=self.db.get_video_metadata(self.path)
        self.assertEqual(meta['transcript'][0]['text'],'I promise always.')
        self.assertEqual(meta['transcript_embeddings_status'],'not_requested')
        self.assertEqual(worker.file_finished_signal.events,[(self.path,)])

    def test_embedding_failure_preserves_previous_transcript_and_vectors(self):
        self.db.update_metadata_key(self.path,'transcript',[{'text':'old vows'}])
        self.db.transcripts.upsert(ids=['old'],embeddings=[[1.,0.]],metadatas=[{'source':self.path}])
        before=self.db.get_video_metadata(self.path)
        worker,model,whisper=self.harness(mode='accuracy')
        worker._run_transcription()
        self.assertTrue(worker.errors)
        self.assertEqual(self.db.get_video_metadata(self.path),before)
        self.assertEqual(self.db.transcripts.get()['ids'],['old'])
        self.assertEqual(worker.file_finished_signal.events,[])

    def test_cancelled_speech_does_not_replace_previous_transcript(self):
        self.db.update_metadata_key(self.path,'transcript',[{'text':'old vows'}])
        before=self.db.get_video_metadata(self.path)
        worker,model,whisper=self.harness()
        def segments():
            worker.is_running=False
            yield types.SimpleNamespace(start=0.,end=1.,text='partial')
        model.transcribe=lambda *a,**kw:(segments(),types.SimpleNamespace(language='en'))
        with patch.dict(sys.modules,{'faster_whisper':whisper}): worker._run_transcription()
        self.assertEqual(self.db.get_video_metadata(self.path),before)
        self.assertEqual(worker.file_finished_signal.events,[])
        self.assertNotIn((100,),worker.progress_signal.events)


if __name__ == '__main__':
    unittest.main()
