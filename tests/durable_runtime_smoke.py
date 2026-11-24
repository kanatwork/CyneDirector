"""Real cached inference + durable ledger + workspace derivatives, synthetic only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import sys

from core.jobs import JobStore
from core.job_runner import JobRunner
from core.workspace import GIB, Workspace


def run():
    root = Path(__file__).resolve().parents[1]
    output = root/".cache/durable-verification"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cyne-real-job-") as tmp:
        base = Path(tmp)
        project, media, workspace = [base/name for name in ("project","originals","generated")]
        for path in (project,media,workspace): path.mkdir()
        project_file = project/"sample.cyne"
        project_file.write_text('{"files": [], "custom_editor_state": "keep this"}')
        source = media/"C0001.mp4"
        speech = base/"speech.aiff"
        subprocess.run(["say","-o",str(speech),"On our wedding day, I promise to stand by your side."],check=True,timeout=60)
        subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","testsrc2=s=320x180:r=25:d=4",
                        "-i",str(speech),"-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-shortest",str(source)],check=True,timeout=60)
        before = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,project_file)}
        # Bounded verification reserve, explicitly NOT the production default.
        selected = Workspace.configure(project,[media],workspace,root/".cache/huggingface",reserve_bytes=64*1024**2)
        default_preflight=Workspace(project,dict(selected.data,reserve_bytes=20*GIB)).preflight([str(source)],["inventory"],{})
        # Seed and exit before the CLI opens embedded Chroma in a fresh process.
        seed="""from core.database import Database
import sys
db=Database(); db.initialize(sys.argv[1])
db.update_metadata_key(sys.argv[2],'editor_note','retain this existing field')
db.visuals.upsert(ids=['legacy-vector'],embeddings=[[1.]+[0.]*767],metadatas=[{'source':sys.argv[2],'timestamp':0.}])
db.close()
"""
        subprocess.run([sys.executable,"-c",seed,str(project),str(source)],check=True,cwd=root,timeout=30)
        store=JobStore(project)
        settings={"device":"mps","mode":"accuracy","whisper_model":"small","blip_variant":"blip-large",
                  "generate_thumbnails":True,"generate_proxies":True,"batch_size":8}
        job=store.submit([str(source)],["inventory","index_visuals","transcribe_audio"],settings,request_key="real-synthetic-pilot")
        assert store.submit([str(source)],["inventory","index_visuals","transcribe_audio"],settings,request_key="real-synthetic-pilot")==job
        original_payload=store.status(job)["payload"]
        # Simulate the same SSD directory appearing at a different mount path.
        # The app only updates configuration; the fixture performs the rename.
        relocated=base/"SSD new location";media.rename(relocated)
        new_output=base/"new generated";new_output.mkdir()
        root_id=selected.data["media_roots"][0]["id"]
        def cli(*arguments):
            process=subprocess.run([sys.executable,"-m","cyne_cli","--project",str(project),*arguments],capture_output=True,text=True,cwd=root,timeout=30)
            assert process.returncode==0,(process.stdout,process.stderr)
            return json.loads(process.stdout)
        change=cli("workspace","plan","--relink",root_id,str(relocated),"--output",str(new_output))
        assert cli("workspace","apply",change["id"])["state"]=="applied"
        assert cli("workspace","apply",change["id"])["state"]=="applied"
        assert store.status(job)["payload"]==original_payload
        assert store.submit([str(relocated/source.name)],["inventory","index_visuals","transcribe_audio"],settings,request_key="real-synthetic-pilot")==job
        executed=subprocess.run([sys.executable,"-m","cyne_cli","--project",str(project),"run",job],
                                capture_output=True,text=True,cwd=root,timeout=180)
        (output/"cli-stderr.log").write_text(executed.stderr)
        assert executed.returncode==0,(executed.stdout,executed.stderr[-3000:])
        result=json.loads(executed.stdout)
        (output/"job.json").write_text(json.dumps(result,indent=2)+"\n")
        assert result["state"]=="completed",result
        assert result["counts"]=={"completed":3},result["counts"]
        assert [i["attempts"] for i in result["items"]]==[1,1,1]
        from core.database import Database
        db=Database(); db.initialize(str(project))
        metadata=db.get_video_metadata(str(source))
        assert metadata["editor_note"]=="retain this existing field"
        assert metadata["visual_job_checkpoint"]["item_id"]==result["items"][1]["id"]
        assert metadata["transcript_job_checkpoint"]["item_id"]==result["items"][2]["id"]
        assert metadata["transcript_embeddings_status"]=="complete"
        assert metadata["visual_processing_memory"]["peak_frame_batch"]<=32
        assert metadata["speech_processing_memory"]["chunks"]==1
        assert metadata["speech_processing_memory"]["max_pcm_bytes"]<=184*32000+64
        transcript=" ".join(s["text"] for s in metadata["transcript"])
        assert "wedding" in transcript.lower(),transcript
        for key in ("thumbnail_path","proxy_path"):
            path=Path(metadata[key]); assert path.is_file() and new_output.resolve() in path.parents,(key,path)
        assert db.visuals.raw.get(ids=["legacy-vector"])["ids"]==["legacy-vector"]
        assert "legacy-vector" not in db.visuals.get(include=["metadatas"])["ids"]
        assert before=={str(source):hashlib.sha256((relocated/source.name).read_bytes()).hexdigest(),
                        str(project_file):hashlib.sha256(project_file.read_bytes()).hexdigest()}
        assert not media.exists()
        assert {r[0] for r in db._get_conn().execute("SELECT video_path FROM video_metadata")}=={str(source)}
        # Completed runs are idempotent and never launch model work again.
        rerun=JobRunner(project).run(job)
        assert [i["attempts"] for i in rerun["items"]]==[1,1,1]
        report={"state":result["state"],"counts":result["counts"],"transcript":transcript,
                "visual_generation":metadata["visual_generation"],"transcript_generation":metadata["transcript_generation"],
                "visual_vectors":db.visuals.count(),"transcript_vectors":db.transcripts.count(),
                "visual_processing_memory":metadata["visual_processing_memory"],
                "speech_processing_memory":metadata["speech_processing_memory"],
                "original_and_project_hashes_preserved":True,"legacy_field_and_vector_preserved":True,
                "derivatives_in_selected_workspace":True,"test_reserve_bytes":64*1024**2,
                "actual_cli_inference_stdout_is_json":True,
                "relinked_before_pending_job_resumed":True,"workspace_update_revision":Workspace.load(project).data["revision"],
                "job_payload_asset_identity_and_metadata_keys_preserved":True,
                "repeated_relink_apply_and_new_path_submit_are_idempotent":True,
                "production_default_preflight_ok":default_preflight["ok"],
                "production_default_capacity":default_preflight["volumes"],
                "events":len(store.events(job)),"attempts_after_repeat":[i["attempts"] for i in rerun["items"]]}
        (output/"result.json").write_text(json.dumps(report,indent=2)+"\n")
        db.close()
        print(json.dumps(report,indent=2),flush=True)


if __name__=="__main__": run()
