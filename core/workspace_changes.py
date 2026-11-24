"""Reviewable, crash-atomic location updates. Never move or rewrite media/data."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid

from core.processing_lock import ProcessingLock
from core.workspace import Workspace,WorkspaceError,configuration_lock,identity,inside


def _safe_project(project):
    project=Path(project).resolve(strict=True)
    folder=project/"_cyne_db"
    if folder.is_symlink() or Workspace.path(project).is_symlink():
        raise WorkspaceError("unsafe_destination","Workspace configuration must stay inside its project database directory")
    return project


def _bytes(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _atomic(path,data):
    """One durable replacement; an interrupted update leaves old or new whole JSON."""
    path=Path(path)
    if path.is_symlink() or path.parent.resolve()!=path.parent:
        raise WorkspaceError("unsafe_destination","Configuration/journal cannot traverse symbolic links")
    fd,tmp=tempfile.mkstemp(prefix=".cyne-update-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(_bytes(data));handle.flush();os.fsync(handle.fileno())
        os.replace(tmp,path)
        if os.name!="nt":
            directory=os.open(path.parent,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
            try: os.fsync(directory)
            finally: os.close(directory)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def _known(workspace):
    """Only read legacy stores. No Chroma open or multi-store path migration."""
    sources={}
    def add(path,kind,signature=None):
        if not isinstance(path,str): raise WorkspaceError("configuration","Non-string project source path")
        try: root,relative=workspace.locate(path)
        except WorkspaceError as exc:
            if exc.code=="unsafe_source": return
            raise
        row=sources.setdefault((root["id"],relative),{"paths":{},"signatures":[]})
        row["paths"].setdefault(kind,[])
        if path not in row["paths"][kind]: row["paths"][kind].append(path)
        if signature and signature not in row["signatures"]: row["signatures"].append(signature)
    for root_id,bindings in workspace.data.get("source_bindings",{}).items():
        for relative,binding in bindings.items(): add(binding["key"],"binding",binding.get("signature"))
    ledger=workspace.project/"_cyne_db"/"jobs.sqlite3"
    if ledger.exists():
        with sqlite3.connect(ledger.as_uri()+"?mode=ro",uri=True) as db:
            for path,signature in db.execute("""SELECT a.original_path,i.signature FROM assets a
                  LEFT JOIN job_items i ON i.asset_id=a.id LEFT JOIN jobs j ON j.id=i.job_id ORDER BY j.created DESC"""):
                add(path,"job",json.loads(signature) if signature else None)
    metadata=workspace.project/"_cyne_db"/"metadata.db"
    if metadata.exists():
        with sqlite3.connect(metadata.as_uri()+"?mode=ro",uri=True) as db:
            for path,visual,speech in db.execute("""SELECT video_path,json_extract(json_data,'$.visual_source_signature'),
                    json_extract(json_data,'$.transcript_source_signature') FROM video_metadata ORDER BY video_path"""):
                add(path,"metadata",json.loads(visual or speech) if visual or speech else None)
    for project_file in sorted(workspace.project.glob("*.cyne")):
        data=json.loads(project_file.read_text())
        for path in data.get("files",[]): add(path,"project")
    return sources


def _inventory_digest(known):
    return hashlib.sha256(_bytes(sorted((r,p,v) for (r,p),v in known.items()))).hexdigest()


def _same(expected,actual):
    keys=("volume_uuid","inode") if "volume_uuid" in expected else ("device","inode")
    return all(actual.get(k)==expected.get(k) for k in keys)


def _hash_file(path,allowed=lambda:True):
    result=hashlib.sha256()
    with open(path,"rb") as handle:
        before=os.fstat(handle.fileno())
        for block in iter(lambda:handle.read(4*1024**2),b""):
            if not allowed(): raise WorkspaceError("cancelled","Workspace verification cancelled; configuration unchanged")
            result.update(block)
        after=os.fstat(handle.fileno())
    keys=lambda stat:(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns)
    if keys(before)!=keys(after): raise WorkspaceError("source_changed","Source changed while verifying content")
    return result.hexdigest()


def _validate_layout(workspace):
    roots=workspace.data["media_roots"]
    outputs=workspace.output_locations()
    destinations=list(workspace.data["destinations"].values())+outputs
    for root in roots:
        for alias in [root["path"]]+root.get("aliases",[]):
            for dest in destinations:
                if inside(Path(alias),Path(dest["path"])) or inside(Path(dest["path"]),Path(alias)):
                    raise WorkspaceError("unsafe_destination","Original media and current/historical write locations must stay separate")
    for i,root in enumerate(roots):
        for other in roots[i+1:]:
            for a in set([root["path"]]+root.get("aliases",[])):
                for b in set([other["path"]]+other.get("aliases",[])):
                    if inside(Path(a),Path(b)) or inside(Path(b),Path(a)):
                        raise WorkspaceError("configuration","Overlapping root paths/aliases would reassign source identities")


def inspect(project):
    project=_safe_project(project)
    workspace=Workspace.load(project,check=False)
    def state(location):
        try: workspace.check_location(location);return "online"
        except WorkspaceError as exc: return exc.code+": "+str(exc)
    return {"workspace_id":workspace.data["id"],"revision":workspace.data.get("revision",0),
            "config_sha256":_digest(Workspace.path(project)),"reserve_bytes":workspace.reserve,
            "media_roots":[dict(r,status=state(r)) for r in workspace.data["media_roots"]],
            "destinations":{k:dict(v,status=state(v)) for k,v in workspace.data["destinations"].items()},
            "output_history":[dict(v,status=state(v)) for v in workspace.data.get("output_history",[])]}


def plan(project,*,relinks=None,output=None,model_cache=None,reserve_bytes=None,add_media_roots=(),seal_roots=(),allowed=lambda:True):
    project=_safe_project(project)
    with ProcessingLock(),configuration_lock(project):
        old=Workspace.load(project,check=False);old.check_location(old.data["destinations"]["project"])
        known=_known(old);data=copy.deepcopy(old.data);checks=[];changes=[]
        roots={r["id"]:r for r in data["media_roots"]}
        relinks=relinks or {}
        if any(not str(value).strip() for value in list(relinks.values())+list(add_media_roots)+[v for v in (output,model_cache) if v is not None]):
            raise WorkspaceError("configuration","Choose explicit nonempty existing folders")
        if (set(relinks)|set(seal_roots))-set(roots): raise WorkspaceError("configuration","Unknown media root ID")
        bindings=data.setdefault("source_bindings",{})
        for root_id,root in roots.items():
            original=next(r for r in old.data["media_roots"] if r["id"]==root_id)
            root.setdefault("origin_path",root["path"])
            root["aliases"]=sorted(set(root.get("aliases",[])+[root["path"]]))
            if root_id in relinks:
                target=Path(relinks[root_id]).resolve(strict=True)
                if not target.is_dir(): raise WorkspaceError("configuration","Relink target must be an existing directory")
                root.update(path=str(target),identity=identity(target))
                root["aliases"]=sorted(set(root["aliases"]+[str(target)]))
            changed=root_id in relinks
            same=_same(original["identity"],root["identity"])
            entries=[(relative,row) for (rid,relative),row in known.items() if rid==root_id]
            if changed and not same and not entries:
                raise WorkspaceError("unverified_media","Different directory identity has no known sources to verify; add it as a new root instead")
            for relative,row in entries:
                if not allowed(): raise WorkspaceError("cancelled","Workspace verification cancelled")
                paths=row["paths"]
                if len(paths.get("metadata",[]))>1 or len(paths.get("job",[]))>1:
                    raise WorkspaceError("ambiguous_source",f"Multiple existing keys for {relative}; no automatic merging")
                key=next(paths[k][0] for k in ("job","metadata","binding","project") if paths.get(k))
                prior=bindings.setdefault(root_id,{}).get(relative,{})
                binding=dict(prior,key=key,aliases=sorted({p for values in paths.values() for p in values}))
                if changed or root_id in seal_roots:
                    candidate=Workspace(project,data,check=False).resolve_source(str(Path(root["path"])/relative))
                    stat=Path(candidate).stat();signature=[stat.st_mtime_ns,stat.st_size]
                    expected=prior.get("signature") or next(iter(row["signatures"]),None)
                    try:
                        source=old.resolve_source(key)
                    except (OSError,WorkspaceError): source=None
                    if source:
                        stat=Path(source).stat();expected=[stat.st_mtime_ns,stat.st_size]
                    if expected and expected!=signature:
                        raise WorkspaceError("source_changed",f"Source size/mtime differs: {relative}; preserve the original revision")
                    content_hash=None
                    if not same or root_id in seal_roots:
                        baseline=_hash_file(source,allowed) if source else prior.get("sha256")
                        if not baseline:
                            raise WorkspaceError("unverified_media",f"Offline source has no sealed hash: {relative}; reconnect the original root first")
                        content_hash=_hash_file(candidate,allowed)
                        if baseline!=content_hash: raise WorkspaceError("source_changed",f"Content verification failed: {relative}")
                    binding["signature"]=signature
                    if content_hash: binding["sha256"]=content_hash
                    checks.append({"path":candidate,"root_id":root_id,"relative_path":relative,"signature":signature,"sha256":content_hash,
                                   "baseline_path":source if not same else None})
                bindings[root_id][relative]=binding
            if changed:
                changes.append({"kind":"relink","root_id":root_id,"from":original["path"],"to":root["path"],
                                "verification":"same pinned directory" if same else "full SHA-256 of every known source","known_sources":len(entries)})
            if root_id in seal_roots: changes.append({"kind":"seal_root","root_id":root_id,"known_sources":len(entries)})
        for value in add_media_roots:
            path=Path(value).resolve(strict=True)
            if not path.is_dir(): raise WorkspaceError("configuration","Media root must be a directory")
            root={"id":uuid.uuid4().hex,"path":str(path),"identity":identity(path)}
            data["media_roots"].append(root);changes.append({"kind":"add_media_root",**root})
        for role,value in (("output",output),("models",model_cache)):
            if value is None: continue
            target=Path(value).resolve(strict=True)
            if not target.is_dir() or not os.access(target,os.W_OK): raise WorkspaceError("unwritable","Choose an existing writable destination")
            previous=data["destinations"][role];location={"path":str(target),"identity":identity(target)}
            if previous==location: continue
            if role=="output":
                history=data.setdefault("output_history",[])
                if any(v["path"]==location["path"] and v["identity"]!=location["identity"] for v in [previous]+history):
                    raise WorkspaceError("waiting_media","Output path is a different directory; choose a separate new location")
                if previous not in history: history.append(previous)
                data["output_history"]=[v for v in history if v!=location]
            data["destinations"][role]=location
            changes.append({"kind":role,"from":previous["path"],"to":str(target),"existing_data":"left in place"})
        if reserve_bytes is not None:
            if type(reserve_bytes) is not int or reserve_bytes<0: raise ValueError("Reserve must be a nonnegative integer")
            data["reserve_bytes"]=reserve_bytes;changes.append({"kind":"reserve_bytes","from":old.reserve,"to":reserve_bytes})
        if not changes: raise WorkspaceError("configuration","No workspace changes requested")
        data["revision"]=old.data.get("revision",0)+1
        proposed=Workspace(project,data,check=False);_validate_layout(proposed)
        if not allowed(): raise WorkspaceError("cancelled","Workspace verification cancelled")
        run_id=uuid.uuid4().hex;data["last_change_id"]=run_id
        report={"version":1,"id":run_id,"created":time.time(),"dry_run":True,
                "before_sha256":_digest(Workspace.path(project)),"inventory_sha256":_inventory_digest(known),
                "after_sha256":hashlib.sha256(_bytes(data)).hexdigest(),"changes":changes,"checks":checks,"proposed":data,
                "contract":"Atomic configuration replacement only; original media, .cyne, metadata, vectors, job payloads and existing derivatives are not rewritten"}
        report["plan_sha256"]=hashlib.sha256(_bytes(report)).hexdigest()
        folder=Workspace.path(project).parent/"workspace-changes"
        if folder.is_symlink(): raise WorkspaceError("unsafe_destination","Change journal cannot be a symlink")
        folder.mkdir(exist_ok=True);_atomic(folder/(run_id+".json"),report)
        return report


def status(project,run_id):
    project=_safe_project(project)
    if not isinstance(run_id,str) or len(run_id)!=32 or not run_id.isalnum(): raise ValueError("Invalid workspace change ID")
    path=Workspace.path(project).parent/"workspace-changes"/(run_id+".json")
    if path.is_symlink() or path.parent.resolve()!=path.parent: raise WorkspaceError("unsafe_destination","Unsafe change journal")
    report=json.loads(path.read_text())
    content=dict(report);checksum=content.pop("plan_sha256",None)
    if hashlib.sha256(_bytes(content)).hexdigest()!=checksum:
        raise WorkspaceError("configuration","Workspace change journal checksum failed")
    if report.get("version")!=1 or report.get("id")!=run_id or hashlib.sha256(_bytes(report["proposed"])).hexdigest()!=report["after_sha256"]:
        raise WorkspaceError("configuration","Invalid workspace change journal")
    current=_digest(Workspace.path(project))
    state="applied" if current==report["after_sha256"] else "planned" if current==report["before_sha256"] else "superseded"
    return dict(report,state=state,dry_run=state!="applied")


def apply(project,run_id,*,allowed=lambda:True):
    project=_safe_project(project)
    with ProcessingLock(),configuration_lock(project):
        report=status(project,run_id)
        if report["state"]=="applied": return report
        if report["state"]!="planned": raise WorkspaceError("stale_plan","Workspace changed; inspect a fresh update plan")
        old=Workspace.load(project,check=False)
        if _inventory_digest(_known(old))!=report["inventory_sha256"]:
            raise WorkspaceError("stale_plan","Project source references changed; inspect a fresh update plan")
        data=report["proposed"];workspace=Workspace(project,data,check=False);_validate_layout(workspace)
        workspace.check_location(data["destinations"]["project"])
        for change in report["changes"]:
            if change["kind"] in ("relink","add_media_root","seal_root"):
                root_id=change.get("root_id",change.get("id"))
                workspace.check_location(next(r for r in data["media_roots"] if r["id"]==root_id))
            elif change["kind"] in ("output","models"): workspace.check_location(data["destinations"][change["kind"]])
        for check in report["checks"]:
            if not allowed(): raise WorkspaceError("cancelled","Workspace verification cancelled")
            path=workspace.resolve_source(check["path"]);stat=Path(path).stat()
            if [stat.st_mtime_ns,stat.st_size]!=check["signature"] or (check["sha256"] and _hash_file(path,allowed)!=check["sha256"]):
                raise WorkspaceError("source_changed","Relink target changed since inspection")
            if check.get("baseline_path"):
                baseline=old.resolve_source(check["baseline_path"]);stat=Path(baseline).stat()
                if [stat.st_mtime_ns,stat.st_size]!=check["signature"] or _hash_file(baseline,allowed)!=check["sha256"]:
                    raise WorkspaceError("source_changed","Original baseline changed since inspection")
        # A single replace is the commit point. No separate job/vector migration
        # can be left half-applied, even if the process dies immediately after it.
        if not allowed(): raise WorkspaceError("cancelled","Workspace update cancelled before commit")
        _atomic(Workspace.path(project),data)
        return status(project,run_id)
