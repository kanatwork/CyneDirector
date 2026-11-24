"""Reproducible synthetic buffer growth, actual PCM/Whisper, retention query costs."""
import argparse
import contextlib
import gc
import hashlib
import io
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from unittest.mock import patch


def sample_worker(frames,dense=False):
    from tests.test_safe_reprocessing import WorkerTimingTests
    from core.memory_budget import MemoryPolicy
    fixture=WorkerTimingTests('test_actual_worker_records_uneven_cuts_and_caption_frame_times')
    fixture.setUp()
    class Image:
        live=peak=0
        def __init__(self,size):
            self.data=bytearray(size*size*3)
            Image.live+=1;Image.peak=max(Image.peak,Image.live)
        def __del__(self): Image.live-=1
    class Signal:
        def emit(self,*args): pass
    try:
        cv=fixture.fake_cv();capture=fixture.capture;get=capture.get
        capture.get=lambda prop:frames if prop=='count' else get(prop)
        worker,config=fixture.harness(cv)
        fixture.db._local.memory_policy=MemoryPolicy(64)
        worker.calculate_histogram=(lambda frame:frame//2) if dense else (lambda frame:0)
        worker._resize_for_ai=lambda image,size:Image(size)
        batches=[]
        worker.process_batch=lambda images,*args:batches.append(len(images)) if len(batches)<64 else None
        for name in ('log_signal','progress_signal','summary_signal'): setattr(worker,name,Signal())
        before=fixture.db.get_video_metadata(fixture.path)
        gc.collect();tracemalloc.start();started=time.perf_counter()
        with patch.dict(sys.modules,{'config':config}),contextlib.redirect_stdout(io.StringIO()): worker._run_indexing()
        _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform!='darwin': rss*=1024
        report={'sampled_frames':frames,'simulated_hours':frames/2/3600,'dense_cuts':dense,
                'policy_mib':64,'python_peak_bytes':peak,'process_peak_rss_bytes':rss,
                'peak_live_resized_images':Image.peak,'maximum_frame_batch':max(batches or [0]),
                'memory_stats':worker.memory_stats,'errors':worker.errors,
                'stage_published':not worker.errors,'elapsed_seconds':time.perf_counter()-started}
        assert report['maximum_frame_batch']<=16
        assert report['peak_live_resized_images']<=23,report
        if dense:
            assert worker.errors and 'record count' in worker.errors[0],worker.errors
            assert fixture.db.get_video_metadata(fixture.path)==before
        else: assert not worker.errors,worker.errors
        return report
    finally: fixture.doCleanups()


def actual_pcm_windows(base):
    from core.bounded_speech import decode_window
    import wave,array
    source=base/'offset-audio.mkv'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=160x90:r=25:d=6',
        '-itsoffset','1.5','-f','lavfi','-i','sine=frequency=1000:duration=4.5','-map','0:v','-map','1:a',
        '-c:v','libx264','-c:a','pcm_s16le','-t','6',str(source)],check=True,timeout=30)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    first,later=base/'first.wav',base/'later.wav'
    a=decode_window(source,first,0,4,lambda:True);b=decode_window(source,later,2,2,lambda:True)
    with wave.open(str(first),'rb') as audio:
        samples=array.array('h',audio.readframes(audio.getnframes()))
    with wave.open(str(later),'rb') as audio:
        second=array.array('h',audio.readframes(audio.getnframes()))
    assert max(abs(v) for v in samples[:16000])==0,'Source audio offset must retain leading silence'
    assert statistics.mean(abs(v) for v in samples[26000:27000])>100
    assert statistics.mean(abs(v) for v in second[:16000])>100
    assert a<=4*32000+64 and b<=2*32000+64
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    return {'leading_silence_preserved':True,'later_window_correct':True,'pcm_bytes':[a,b],'source_hash_unchanged':True}


def actual_whisper_windows(base,cache):
    from core.bounded_speech import bounded_transcribe
    from core.memory_budget import MemoryPolicy
    from faster_whisper import WhisperModel
    source=base/'wedding.aiff'
    sentence='On our wedding day, I promise to stand by your side.'
    subprocess.run(['say','-o',str(source),sentence],check=True,timeout=30)
    model=WhisperModel('small',device='cpu',compute_type='int8',download_root=str(cache/'hub'),local_files_only=True)
    segments,info=bounded_transcribe(model,source,None,'synthetic',MemoryPolicy(speech_seconds=2),
        {'beam_size':5,'vad_filter':True},temporary_parent=base)
    segments=list(segments);text=' '.join(s.text for s in segments)
    assert text==sentence,text
    assert info.bounded_stats['chunks']>=2
    assert all(0<=s.start<s.end<=info.duration for s in segments)
    return {'text':text,'stats':info.bounded_stats,'segments':[{'start':s.start,'end':s.end,'text':s.text} for s in segments]}


def retention_cost():
    from tests.test_memory_retention import RetentionFixture
    from core import retention
    fixture=RetentionFixture();fixture.setUp()
    try:
        for vector in ([1.,0.,0.],[1.,0.,0.],[.9,.1,0.],[0.,1.,0.]): fixture.publish(rows=300,artifact=True,vector=vector)
        db=fixture.db;raw=db.visuals.raw
        class Observed:
            widths=[]
            def __getattr__(self,name): return getattr(raw,name)
            def query(self,**kwargs): self.widths.append(kwargs['n_results']);return raw.query(**kwargs)
        observed=Observed();db.visuals.raw=observed
        def measure():
            times=[];observed.widths.clear()
            for i in range(12):
                start=time.perf_counter();result=db.visuals.query(query_embeddings=[[1.,0.,0.]],n_results=8,include=['metadatas','distances'])
                times.append((time.perf_counter()-start)*1000)
                assert len(result['ids'][0])==8
                assert all(m['generation']==db.get_video_metadata(fixture.path)['visual_generation'] for m in result['metadatas'][0])
            return {'median_ms':statistics.median(times),'p95_ms':sorted(times)[-1],
                    'max_candidates':max(observed.widths),'diagnostics':db.visuals.last_query_diagnostics,
                    'raw_vectors':raw.count(),'visible_vectors':db.visuals.count()}
        before=measure();plan=fixture.plan();retention.apply(db,plan['run_id'],now=fixture.now);after=measure()
        assert before['visible_vectors']==after['visible_vectors']==300
        assert after['raw_vectors']==600 and before['raw_vectors']==1200
        assert after['diagnostics'].get('scanned_rows',0)<before['diagnostics']['scanned_rows']
        retention.restore(db,plan['run_id'])
        assert raw.count()==1200
        return {'before':before,'after':after,'restored_raw_vectors':raw.count(),
                'note':'Logical vector removal; SQLite/HNSW file shrink is not guaranteed'}
    finally: fixture.doCleanups()


def run():
    parser=argparse.ArgumentParser();parser.add_argument('--frames',type=int);parser.add_argument('--dense',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.frames:
        with contextlib.redirect_stdout(sys.stderr): result=sample_worker(args.frames,args.dense)
        print(json.dumps(result));return
    output=root/'.cache/memory-retention-verification';output.mkdir(parents=True,exist_ok=True)
    profiles=[]
    for frames,dense in ((5000,False),(50000,False),(50000,True)):
        command=[sys.executable,'-m','tests.memory_retention_benchmark','--frames',str(frames)]
        if dense: command.append('--dense')
        process=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=90)
        assert process.returncode==0,process.stdout+process.stderr
        profiles.append(json.loads(process.stdout))
    assert profiles[1]['python_peak_bytes']<profiles[0]['python_peak_bytes']+8*1024**2
    assert profiles[1]['process_peak_rss_bytes']<profiles[0]['process_peak_rss_bytes']+64*1024**2
    with tempfile.TemporaryDirectory(prefix='cyne-bounded-measure-') as tmp:
        base=Path(tmp)
        pcm=actual_pcm_windows(base)
        speech=actual_whisper_windows(base,root/'.cache/huggingface')
        cost=retention_cost()
    report={'profiles':profiles,'actual_pcm':pcm,'actual_whisper':speech,'retention_query_cost':cost,
            'fixtures':'Generated/simulated only; no actual wedding/SSD/long-model quality acceptance'}
    (output/'benchmark.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':run()
