"""Local JSON job commands. No HTTP listener or cloud media upload.

Run with the installed .venv from this checkout, or use cyne.command.
"""
import argparse
from contextlib import redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys

from core.jobs import JobConflict, JobStore
from core.processing_lock import ProcessingBusy
from core.workspace import GIB, STAGES, Workspace, WorkspaceError


def selected(args):
    files = list(args.file or [])
    if args.files_from:
        value = json.loads(Path(args.files_from).read_text())
        files.extend(value["files"] if isinstance(value, dict) else value)
    if not files or any(not isinstance(p, str) for p in files):
        raise ValueError("Provide --file paths or --files-from a JSON array/.cyne file")
    return files


def start_job(project, job_id):
    store = JobStore(project)
    status = store.status(job_id)
    if status["state"] in ("completed", "failed", "cancelled", "paused"):
        return {"job_id": job_id, "state": status["state"], "started": False}
    if status["lease_owner"] and (status["lease_until"] or 0) > store.clock():
        return {"job_id": job_id, "state": status["state"], "started": False, "reason": "live runner"}
    workspace = Workspace.load(project)
    folder = workspace.artifact_dir("logs", job_id)
    with (folder / "runner.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "cyne_cli", "--project", str(Path(project).resolve()),
                                    "run", job_id], cwd=Path(__file__).resolve().parent,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   start_new_session=(os.name != "nt"),
                                   creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0)
    return {"job_id": job_id, "pid": process.pid, "started": True, "log": str(folder/"runner.log")}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--project", required=True, help="Existing project directory (not the .cyne file)")
    sub = root.add_subparsers(dest="command", required=True)
    configure = sub.add_parser("configure")
    configure.add_argument("--media-root", action="append", required=True)
    configure.add_argument("--output", required=True)
    configure.add_argument("--model-cache", required=True)
    configure.add_argument("--reserve-gib", type=float, default=20)
    for name in ("preflight", "submit"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--file", action="append")
        cmd.add_argument("--files-from")
        cmd.add_argument("--stage", choices=STAGES, action="append", required=True)
        cmd.add_argument("--mode", choices=("speed", "accuracy"))
        cmd.add_argument("--whisper-model", choices=("base", "small", "medium", "large-v3"))
        cmd.add_argument("--memory-mib", type=int, dest="processing_memory_mib")
        cmd.add_argument("--speech-chunk-seconds", type=int)
        if name == "submit":
            cmd.add_argument("--request-key")
    sub.add_parser("list")
    workspace=sub.add_parser("workspace",help="Inspect and safely update pinned locations")
    changes=workspace.add_subparsers(dest="workspace_action",required=True)
    changes.add_parser("inspect")
    update=changes.add_parser("plan")
    update.add_argument("--relink",nargs=2,action="append",metavar=("ROOT_ID","EXISTING_FOLDER"))
    update.add_argument("--seal-root",action="append",default=[])
    update.add_argument("--add-media-root",action="append",default=[])
    update.add_argument("--output")
    update.add_argument("--model-cache")
    update.add_argument("--reserve-gib",type=float)
    for action in ("apply","status"):
        changes.add_parser(action).add_argument("change_id")
    retention = sub.add_parser("retention",help="Inspect/quarantine/restore/purge tracked derived generations")
    maintenance=retention.add_subparsers(dest="retention_action",required=True)
    inspect=maintenance.add_parser("plan")
    inspect.add_argument("--keep-previous",type=int,default=2)
    inspect.add_argument("--min-age-hours",type=float,default=24)
    for action in ("apply","status","restore","purge"):
        command=maintenance.add_parser(action);command.add_argument("run_id")
        if action=="restore": command.add_argument("--generation")
    for action in ("pin","unpin"):
        command=maintenance.add_parser(action);command.add_argument("generation")
        if action=="pin": command.add_argument("--reason",required=True)
    for name in ("status", "events", "run", "start", "pause", "resume", "cancel", "retry-failed"):
        cmd = sub.add_parser(name)
        cmd.add_argument("job_id")
        if name == "events":
            cmd.add_argument("--after", type=int, default=0)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "configure":
            workspace = Workspace.configure(args.project, args.media_root, args.output, args.model_cache,
                                            reserve_bytes=int(args.reserve_gib * GIB))
            result = workspace.data
        elif args.command in ("preflight", "submit"):
            settings = {k: getattr(args, k) for k in ("mode", "whisper_model", "processing_memory_mib", "speech_chunk_seconds") if getattr(args, k) is not None}
            if args.command == "preflight":
                workspace = Workspace.load(args.project)
                from core.settings_manager import SettingsManager
                snapshot = SettingsManager(args.project).to_dict()
                snapshot.update(settings)
                result = workspace.preflight(selected(args), args.stage, snapshot)
            else:
                result = {"job_id": JobStore(args.project).submit(selected(args), args.stage, settings, args.request_key)}
        elif args.command == "workspace":
            from core import workspace_changes
            if args.workspace_action=="inspect": result=workspace_changes.inspect(args.project)
            elif args.workspace_action=="plan":
                relinks=dict(args.relink or [])
                if len(relinks)!=len(args.relink or []): raise ValueError("Select each root ID once")
                result=workspace_changes.plan(args.project,relinks=relinks,output=args.output,model_cache=args.model_cache,
                    reserve_bytes=None if args.reserve_gib is None else int(args.reserve_gib*GIB),
                    add_media_roots=args.add_media_root,seal_roots=args.seal_root)
            elif args.workspace_action=="apply": result=workspace_changes.apply(args.project,args.change_id)
            else: result=workspace_changes.status(args.project,args.change_id)
        elif args.command == "retention":
            from core import retention
            from core.database import Database
            db=Database()
            with redirect_stdout(sys.stderr):
                db.initialize(args.project)
                try:
                    if args.retention_action=="plan": result=retention.plan(db,args.keep_previous,args.min_age_hours)
                    elif args.retention_action=="apply": result=retention.apply(db,args.run_id)
                    elif args.retention_action=="status": result=retention.status(db,args.run_id)
                    elif args.retention_action=="restore": result=retention.restore(db,args.run_id,args.generation)
                    elif args.retention_action=="purge": result=retention.purge(db,args.run_id)
                    elif args.retention_action=="pin": retention.pin(db,args.generation,args.reason);result={"pinned":args.generation}
                    else: retention.unpin(db,args.generation);result={"unpinned":args.generation}
                finally: db.close()
        else:
            store = JobStore(args.project)
            if args.command == "list":
                result = store.list_jobs()
            elif args.command == "status":
                result = store.status(args.job_id)
            elif args.command == "events":
                result = store.events(args.job_id, args.after)
            elif args.command == "run":
                from core.job_runner import JobRunner
                with redirect_stdout(sys.stderr):
                    result = JobRunner(args.project).run(args.job_id)
            elif args.command == "start":
                result = start_job(args.project, args.job_id)
            else:
                store.control(args.job_id, args.command.replace("-", "_"))
                result = start_job(args.project, args.job_id) if args.command in ("resume", "retry-failed") else store.status(args.job_id)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2 if isinstance(result, dict) and (result.get("ok") is False or result.get("state") in ("failed", "waiting_capacity", "waiting_media", "waiting_resource", "interrupted")) else 0
    except Exception as exc:
        print(json.dumps({"error": {"code": getattr(exc, "code", type(exc).__name__), "message": str(exc)}}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
