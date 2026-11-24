"""Actual worker methods with model doubles: bounded writes and complete metadata."""
import ast
from collections import defaultdict
import contextlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from core.memory_budget import MemoryPolicy, ThreeFrameSet


class WorkerMemoryTests(unittest.TestCase):
    def speech(self,mode='accuracy',count=1000):
        from tests import test_safe_reprocessing as safety
        fixture=safety.TranscriptionPublicationTests('test_speech_success_publishes_transcript_then_success_signal')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        worker,model,whisper=fixture.harness(mode)
        patcher=patch.dict(sys.modules,{'faster_whisper':whisper})
        patcher.start();self.addCleanup(patcher.stop)
        fixture.db._local.memory_policy=MemoryPolicy(64)
        def transcribe(*args,**kwargs):
            def records():
                for i in range(count):
                    yield types.SimpleNamespace(start=i*.1,end=i*.1+.05,text='I promise always.')
            return records(),types.SimpleNamespace(language='en')
        model.transcribe=transcribe
        return fixture,worker

    def test_speech_embeddings_are_written_in_batches_without_losing_segments(self):
        fixture,worker=self.speech()
        globals_=worker._transcribe_file.__func__.__globals__
        globals_['torch']=types.SimpleNamespace(no_grad=contextlib.nullcontext)
        globals_['as_clip_tensor']=lambda value:value
        class Inputs(dict):
            def to(self,*args): return self
        class Features:
            def __init__(self,n): self.n=n
            def norm(self,*args,**kwargs): return 1
            def __itruediv__(self,value): return self
            def cpu(self): return self
            def numpy(self): return self
            def tolist(self): return [[.1,.2] for _ in range(self.n)]
        ai=worker._run_transcription.__func__.__globals__['AIBackend']()
        ai.device='cpu';ai.clip_model=types.SimpleNamespace(get_text_features=lambda n:Features(n))
        ai.clip_processor=lambda text,**kwargs:Inputs(n=len(text))
        raw=fixture.db.transcripts.raw;upsert=raw.upsert;batches=[]
        def observe(**kwargs): batches.append(len(kwargs['ids']));return upsert(**kwargs)
        raw.upsert=observe
        worker._run_transcription()
        self.assertEqual(worker.errors,[])
        self.assertLessEqual(max(batches),32)
        self.assertEqual(sum(batches),1000)
        self.assertEqual(fixture.db.transcripts.count(),1000)
        self.assertEqual(len(fixture.db.get_video_metadata(fixture.path)['transcript']),1000)

    def test_dense_transcript_over_budget_keeps_prior_project_and_transcript(self):
        policy=MemoryPolicy(64)
        fixture,worker=self.speech('speed',policy.transcript_records+1)
        fixture.db.update_metadata_key(fixture.path,'transcript',[{'start':0.,'end':1.,'text':'old vows'}])
        before=fixture.db.get_video_metadata(fixture.path)
        worker._run_transcription()
        self.assertTrue(worker.errors)
        self.assertIn('record count',worker.errors[0])
        self.assertEqual(fixture.db.get_video_metadata(fixture.path),before)
        self.assertEqual(worker.file_finished_signal.events,[])

    def test_visual_vector_buffer_flushes_at_limit_not_after_batch_growth(self):
        import torch
        from core.clip_features import as_clip_tensor
        root=Path(__file__).resolve().parents[1]
        module=ast.parse((root/'workers/indexer.py').read_text())
        cls=next(node for node in module.body if isinstance(node,ast.ClassDef) and node.name=='IndexerWorker')
        funcs=[node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name in ('process_batch','_flush_db_batch')]
        namespace={'torch':torch,'as_clip_tensor':as_clip_tensor,'defaultdict':defaultdict}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'workers/indexer.py','exec'),namespace)
        worker=type('Worker',(),{name:namespace[name] for name in ('process_batch','_flush_db_batch')})()
        class Buffer(list):
            peak=0
            def append(self,item): super().append(item);self.peak=max(self.peak,len(self))
        worker.db_write_batch=Buffer([([.5]*4,float(i)) for i in range(63)])
        worker.db_write_batch_size=64;worker.errors=[]
        class Inputs(dict):
            def to(self,*args): return self
        processor=lambda images,**kwargs:Inputs(n=len(images))
        model=types.SimpleNamespace(get_image_features=lambda n:torch.ones((n,4)))
        ai=types.SimpleNamespace(device='cpu',tag_embeddings=torch.ones((20,4))*.5)
        batches=[];db=types.SimpleNamespace(add_visual_embeddings=lambda path,vectors,times:batches.append(len(vectors)))
        occurrences=defaultdict(ThreeFrameSet)
        worker.process_batch([None]*32,list(range(32)),ai,db,'synthetic',model,processor,
                             [f'person {i}' for i in range(20)],defaultdict(float),occurrences,0)
        worker._flush_db_batch(db,'synthetic')
        self.assertEqual(worker.errors,[])
        self.assertEqual(worker.db_write_batch.peak,64)
        self.assertEqual(batches,[64,31])
        self.assertTrue(all(len(frames)<=3 for frames in occurrences.values()))


if __name__=='__main__':unittest.main()
