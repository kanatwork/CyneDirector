"""Conservative retention of tracked derived generations; never original media.

Legacy/unregistered generations are protected. Removal requires a saved dry-run
plan and revalidation, with reversible vector/file quarantine before final purge.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import math
import uuid
import zlib

from core.memory_budget import MIB
from core.processing_lock import ProcessingLock
from core.workspace import Workspace, WorkspaceError

COLLECTIONS = {"visual": ("visuals", "temporal_sequences"), "transcript": ("transcripts",)}
BATCH = 64


def initialize(db):
    conn=db._get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS generation_schema (version INTEGER NOT NULL)")
    version=conn.execute("SELECT version FROM generation_schema").fetchone()
    if version and version[0]!=1:
        raise RuntimeError("Unsupported generation schema; existing project data left unchanged")
    if not version: conn.execute("INSERT INTO generation_schema VALUES(1)")
    db._get_conn().executescript("""
      CREATE TABLE IF NOT EXISTS generation_records (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT, generation TEXT UNIQUE NOT NULL,
        source TEXT NOT NULL, stage TEXT NOT NULL, created REAL NOT NULL,
        published REAL, retired REAL, state TEXT NOT NULL,retention_owner TEXT);
      CREATE TABLE IF NOT EXISTS generation_artifacts (
        generation TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL,
        PRIMARY KEY(generation,path));
      CREATE TABLE IF NOT EXISTS generation_pins (
        generation TEXT PRIMARY KEY, reason TEXT NOT NULL, created REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS retention_runs (
        id TEXT PRIMARY KEY, created REAL NOT NULL, updated REAL NOT NULL,
        fingerprint TEXT NOT NULL, policy TEXT NOT NULL, state TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS retention_items (
        run_id TEXT NOT NULL, generation TEXT NOT NULL, state TEXT NOT NULL,
        vector_count INTEGER NOT NULL DEFAULT 0, manifest TEXT, error TEXT,
        PRIMARY KEY(run_id,generation));
      CREATE TABLE IF NOT EXISTS retention_vectors (
        run_id TEXT NOT NULL, generation TEXT NOT NULL, collection_name TEXT NOT NULL,
        row_id TEXT NOT NULL, payload BLOB, digest TEXT NOT NULL,
        PRIMARY KEY(run_id,collection_name,row_id));
      CREATE TABLE IF NOT EXISTS retention_files (
        run_id TEXT NOT NULL,generation TEXT NOT NULL,source TEXT NOT NULL,target TEXT NOT NULL,
        size INTEGER NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,
        PRIMARY KEY(run_id,source));
    """)
    if "retention_owner" not in {r[1] for r in db._get_conn().execute("PRAGMA table_info(generation_records)")}:
        db._get_conn().execute("ALTER TABLE generation_records ADD COLUMN retention_owner TEXT")
    db._get_conn().commit()


def register_artifact(project, generation, path, kind):
    """Register an exact generated file BEFORE writing, including partial output."""
    workspace = Workspace.load(project)
    path = Path(path)
    base = Path(workspace.data["destinations"]["output"]["path"]) / ("cyne-"+workspace.data["id"]) / kind / generation
    if kind not in ("thumbnails", "proxies", "temporary") or not path.is_absolute() or base not in path.parents:
        raise WorkspaceError("unsafe_destination", "Artifact is outside its generation namespace")
    if path.is_symlink() or path.parent.resolve() != path.parent:
        raise WorkspaceError("unsafe_destination", "Generated artifact may not traverse symbolic links")
    location = Path(project)/"_cyne_db"/"metadata.db"
    with sqlite3.connect(location) as conn:
        if not conn.execute("SELECT 1 FROM generation_records WHERE generation=? AND state='staging'", (generation,)).fetchone():
            raise RuntimeError("Artifact generation is not an active tracked stage")
        conn.execute("INSERT OR IGNORE INTO generation_artifacts VALUES(?,?,?)", (generation,str(path),kind))


def _rows(raw, generation, include):
    offset = 0
    while True:
        rows = raw.get(where={"generation": generation}, include=include, limit=BATCH, offset=offset)
        if not rows["ids"]:
            return
        yield rows
        offset += len(rows["ids"])


def _raw(db, name):
    collection = getattr(db, name, None)
    return getattr(collection, "raw", collection) if collection is not None else None


def pin(db, generation, reason):
    if not reason.strip():
        raise ValueError("A pin requires a reason")
    with db._lock:
        conn = db._get_conn()
        if not conn.execute("SELECT 1 FROM generation_records WHERE generation=?", (generation,)).fetchone():
            raise ValueError("Only tracked generations can be pinned")
        conn.execute("INSERT OR REPLACE INTO generation_pins VALUES(?,?,?)", (generation,reason,time.time()))
        conn.commit()


def unpin(db, generation):
    with db._lock:
        db._get_conn().execute("DELETE FROM generation_pins WHERE generation=?", (generation,))
        db._get_conn().commit()


def _protection(db, keep_previous, min_age, now, run_id=None):
    conn = db._get_conn()
    active, references = set(), set()
    # SQLite extracts only pointer/reference fields; do not hydrate every transcript.
    snapshot = []
    for row in conn.execute("""SELECT video_path,json_extract(json_data,'$.visual_generation'),
              json_extract(json_data,'$.transcript_generation'),json_extract(json_data,'$.thumbnail_path'),
              json_extract(json_data,'$.proxy_path') FROM video_metadata ORDER BY video_path"""):
        snapshot.append(tuple(row))
        active.update(g for g in (row[1],row[2]) if g)
        references.update(p for p in (row[3],row[4]) if p)
    protected = {g:"active publication" for g in active}
    protected.update({g:"active writer" for g in getattr(db,"_active_generations",set())})
    protected.update({r[0]:"pinned: "+r[1] for r in conn.execute("SELECT generation,reason FROM generation_pins")})
    canonical_refs = {os.path.realpath(p) for p in references}
    for row in conn.execute("SELECT generation,path FROM generation_artifacts"):
        if os.path.realpath(row[1]) in canonical_refs:
            protected[row[0]]="referenced artifact"
    jobs = Path(db.project_path)/"_cyne_db"/"jobs.sqlite3"
    if jobs.exists():
        with sqlite3.connect(jobs.as_uri()+"?mode=ro",uri=True) as ledger:
            for row in ledger.execute("""SELECT i.result FROM job_items i JOIN jobs j ON j.id=i.job_id
                   WHERE j.state NOT IN ('completed','failed','cancelled') AND i.result IS NOT NULL"""):
                generation=json.loads(row[0]).get("generation")
                if generation: protected[generation]="unfinished job result"
    history = {}
    for row in conn.execute("SELECT * FROM generation_records ORDER BY published DESC,sequence DESC"):
        row=dict(row); generation=row["generation"]
        if row["retention_owner"] and row["retention_owner"]!=run_id and row["state"]!="purged":
            protected.setdefault(generation,"owned by another quarantine run")
        if row["published"] is not None and generation not in active and row["state"] not in ("quarantined","purged"):
            key=(row["source"],row["stage"])
            history[key]=history.get(key,0)+1
            if history[key] <= keep_previous: protected.setdefault(generation,"recent successful generation")
        age=now-(row["retired"] if row["retired"] is not None else row["created"])
        if age < min_age: protected.setdefault(generation,"grace period")
    fingerprint=hashlib.sha256(json.dumps([snapshot,sorted(protected.items()),sorted(references)],sort_keys=True).encode()).hexdigest()
    return protected,references,fingerprint


def _payloads(db, record):
    for name in COLLECTIONS[record["stage"]]:
        raw=_raw(db,name)
        if raw is None: raise RuntimeError("Generation collection is unavailable; retention cannot verify it")
        for rows in _rows(raw,record["generation"],["embeddings","metadatas","documents"]):
            for i,row_id in enumerate(rows["ids"]):
                meta=rows["metadatas"][i]
                if not row_id.startswith(record["generation"]+":") or meta.get("source")!=record["source"]:
                    raise RuntimeError("Vector provenance differs from the tracked generation")
                embedding=rows["embeddings"][i]
                payload={"id":row_id,"embedding":embedding.tolist() if hasattr(embedding,"tolist") else embedding,
                         "metadata":meta,"document":rows["documents"][i] if rows.get("documents") is not None else None}
                data=json.dumps(payload,separators=(",",":"),allow_nan=False).encode()
                if len(data)>4*MIB: raise RuntimeError("Archive row exceeds bounded buffer limit")
                yield name,row_id,data


def _file_hash(path):
    digest=hashlib.sha256()
    with open(path,"rb") as handle:
        for block in iter(lambda:handle.read(MIB),b""): digest.update(block)
    return digest.hexdigest()


def _owned_path(workspace, generation, path, kind):
    if kind not in ("thumbnails","proxies","temporary"):
        raise RuntimeError("Unknown artifact kind")
    location=workspace.output_for(path)
    base=Path(location["path"])/("cyne-"+workspace.data["id"])/kind/generation
    path=Path(path)
    if kind not in ("thumbnails","proxies","temporary") or base not in path.parents or path.is_symlink() or path.parent.resolve()!=path.parent:
        raise RuntimeError("Artifact ownership/containment could not be verified")
    return path


def plan(db, keep_previous=2, min_age_hours=24, *, now=None):
    if type(keep_previous) is not int or keep_previous<1 or not math.isfinite(min_age_hours) or min_age_hours<0:
        raise ValueError("Keep at least one previous successful generation; age must be nonnegative")
    now=time.time() if now is None else now
    with ProcessingLock(),db._lock:
        workspace=Workspace.load(db.project_path)
        protected,_,fingerprint=_protection(db,keep_previous,min_age_hours*3600,now)
        run_id=uuid.uuid4().hex; conn=db._get_conn(); candidates=[]; kept=[]
        for row in conn.execute("SELECT * FROM generation_records ORDER BY sequence"):
            record=dict(row); generation=record["generation"]
            if record["state"] in ("quarantined","purged"): continue
            if generation in protected:
                kept.append({"generation":generation,"reason":protected[generation]}); continue
            try:
                count=total=0
                for _,_,data in _payloads(db,record): count+=1; total+=len(data)
                file_bytes=0
                for artifact in conn.execute("SELECT path,kind FROM generation_artifacts WHERE generation=?",(generation,)):
                    path=_owned_path(workspace,generation,artifact[0],artifact[1])
                    if path.exists():
                        if not path.is_file(): raise RuntimeError("Registered artifact is not a regular file")
                        file_bytes+=path.stat().st_size
                candidates.append({"generation":generation,"source":record["source"],"stage":record["stage"],
                                   "vectors":count,"archive_json_bytes":total,"artifact_bytes":file_bytes})
            except Exception as exc:
                kept.append({"generation":generation,"reason":"inspection failed: "+str(exc)})
        policy={"keep_previous":keep_previous,"min_age_hours":min_age_hours,"workspace_id":workspace.data["id"],
                "workspace_revision":workspace.data.get("revision",0)}
        conn.execute("INSERT INTO retention_runs VALUES(?,?,?,?,?,'planned')",(run_id,now,now,fingerprint,json.dumps(policy)))
        for candidate in candidates:
            conn.execute("INSERT INTO retention_items(run_id,generation,state,vector_count,manifest) VALUES(?,?,'planned',?,?)",
                         (run_id,candidate["generation"],candidate["vectors"],json.dumps(candidate)))
        conn.commit()
        return {"run_id":run_id,"dry_run":True,"policy":policy,"candidates":candidates,"protected":kept,
                "legacy":"All untracked generations/legacy vectors and unregistered files are untouched",
                "space":"Quarantine is reversible and does not reclaim file bytes until a later explicit purge"}


def status(db, run_id):
    with db._lock:
        row=db._get_conn().execute("SELECT * FROM retention_runs WHERE id=?",(run_id,)).fetchone()
        if row is None: raise KeyError("Unknown retention plan")
        result=dict(row); result["policy"]=json.loads(result["policy"])
        result["items"]=[dict(r) for r in db._get_conn().execute("SELECT * FROM retention_items WHERE run_id=? ORDER BY generation",(run_id,))]
        for item in result["items"]: item["manifest"]=json.loads(item["manifest"]) if item["manifest"] else {}
        return result


def _unpack(payload,digest):
    if payload is None: raise RuntimeError("Archive payload was purged")
    decoder=zlib.decompressobj(); data=decoder.decompress(payload,4*MIB+1)
    if len(data)>4*MIB or decoder.unconsumed_tail or not decoder.eof or hashlib.sha256(data).hexdigest()!=digest:
        raise RuntimeError("Archive checksum/size validation failed")
    return json.loads(data)


def _verify_archive(db,run_id,generation,manifest):
    count=0;digest=hashlib.sha256()
    for row in db._get_conn().execute("SELECT payload,digest FROM retention_vectors WHERE run_id=? AND generation=? ORDER BY collection_name,row_id",(run_id,generation)):
        _unpack(row[0],row[1]);count+=1;digest.update(row[1].encode())
    if count!=manifest["vectors"] or digest.hexdigest()!=manifest["archive_digest"]:
        raise RuntimeError("Archive manifest count/checksum differs; live data left intact")


def _validate_files(db,workspace,run_id,generation):
    conn=db._get_conn()
    for file in conn.execute("SELECT * FROM retention_files WHERE run_id=? AND generation=?",(run_id,generation)):
        owned=conn.execute("SELECT kind FROM generation_artifacts WHERE generation=? AND path=?",(generation,file["source"])).fetchone()
        if not owned: raise RuntimeError("File manifest has no registered owner")
        source=_owned_path(workspace,generation,file["source"],owned[0])
        expected=Path(workspace.output_for(source)["path"])/("cyne-"+workspace.data["id"])/"quarantine"/run_id/generation/owned[0]/(hashlib.sha256(str(source).encode()).hexdigest()+source.suffix)
        target=Path(file["target"])
        if target!=expected or target.is_symlink() or target.parent.resolve()!=target.parent:
            raise RuntimeError("File manifest escapes its quarantine namespace")


def _child_directory(parent, name):
    parent=Path(parent)
    if parent.resolve()!=parent or parent.is_symlink(): raise RuntimeError("Unsafe quarantine parent")
    expected=parent.stat()
    flags=os.O_RDONLY|getattr(os,"O_DIRECTORY",0)|getattr(os,"O_NOFOLLOW",0)
    if os.mkdir in os.supports_dir_fd:
        fd=os.open(parent,flags)
        try:
            actual=os.fstat(fd)
            if (actual.st_ino,actual.st_dev)!=(expected.st_ino,expected.st_dev): raise RuntimeError("Quarantine parent changed")
            try: os.mkdir(name,dir_fd=fd)
            except FileExistsError: pass
            child=os.open(name,flags,dir_fd=fd);os.close(child)
        finally: os.close(fd)
    else:
        child=parent/name
        if child.is_symlink(): raise RuntimeError("Unsafe quarantine child")
        child.mkdir(exist_ok=True)
    return parent/name


def _archive(db, run_id, record, workspace, now):
    import shutil
    conn=db._get_conn(); generation=record["generation"]
    if record["retention_owner"] and record["retention_owner"]!=run_id:
        raise RuntimeError("Another quarantine owns this generation")
    item=conn.execute("SELECT * FROM retention_items WHERE run_id=? AND generation=?",(run_id,generation)).fetchone()
    manifest=json.loads(item["manifest"])
    if item["state"] in ("planned","archiving"):
        # Copy on the project filesystem, accounting for WAL/SQLite overhead.
        required=manifest["archive_json_bytes"]*2+min(workspace.reserve,64*MIB)
        if shutil.disk_usage(db.project_path).free<required: raise RuntimeError("Insufficient space for verified vector quarantine")
        conn.execute("UPDATE generation_records SET retention_owner=? WHERE generation=?",(run_id,generation))
        conn.execute("UPDATE retention_items SET state='archiving',error=NULL WHERE run_id=? AND generation=?",(run_id,generation));conn.commit()
        count=0
        for name,row_id,data in _payloads(db,record):
            conn.execute("INSERT OR REPLACE INTO retention_vectors VALUES(?,?,?,?,?,?)",
                         (run_id,generation,name,row_id,zlib.compress(data),hashlib.sha256(data).hexdigest()))
            count+=1
            if count%BATCH==0: conn.commit()
        conn.commit()
        verified=0; digest=hashlib.sha256()
        for row in conn.execute("SELECT * FROM retention_vectors WHERE run_id=? AND generation=? ORDER BY collection_name,row_id",(run_id,generation)):
            _unpack(row["payload"],row["digest"]);verified+=1;digest.update(row["digest"].encode())
        if count!=verified or count!=manifest["vectors"]: raise RuntimeError("Generation changed since inspection; live vectors left intact")
        # Validate every registered file BEFORE deleting any live vector.
        for artifact in conn.execute("SELECT path,kind FROM generation_artifacts WHERE generation=?",(generation,)):
            source=_owned_path(workspace,generation,artifact[0],artifact[1])
            if not source.exists(): continue
            folder=_child_directory(_child_directory(workspace.artifact_dir("quarantine",run_id,output=workspace.output_for(source)),generation),artifact[1])
            target=folder/(hashlib.sha256(str(source).encode()).hexdigest()+source.suffix)
            conn.execute("INSERT OR IGNORE INTO retention_files VALUES(?,?,?,?,?,?,?)",
                         (run_id,generation,str(source),str(target),source.stat().st_size,_file_hash(source),"planned"))
        manifest.update(archive_digest=digest.hexdigest(),archived_at=now)
        conn.execute("UPDATE retention_items SET state='archived',manifest=? WHERE run_id=? AND generation=?",(json.dumps(manifest),run_id,generation));conn.commit()
    # Deletions use the verified archive's IDs, never offset-paging a shrinking set.
    _verify_archive(db,run_id,generation,manifest)
    _validate_files(db,workspace,run_id,generation)
    for name in COLLECTIONS[record["stage"]]:
        raw=_raw(db,name)
        if raw is None: raise RuntimeError("Generation collection unavailable")
        cursor=conn.execute("SELECT row_id,payload,digest FROM retention_vectors WHERE run_id=? AND generation=? AND collection_name=? ORDER BY row_id",(run_id,generation,name))
        while True:
            batch=cursor.fetchmany(BATCH)
            if not batch: break
            for row in batch: _unpack(row["payload"],row["digest"])
            live=raw.get(ids=[row["row_id"] for row in batch],include=[])["ids"]
            if live: raw.delete(ids=live)
    for file in conn.execute("SELECT * FROM retention_files WHERE run_id=? AND generation=?",(run_id,generation)):
        source,target=Path(file["source"]),Path(file["target"])
        if source.exists():
            if source.is_symlink() or _file_hash(source)!=file["digest"]: raise RuntimeError("Derived file changed during quarantine; restore/reinspect")
            if target.exists(): raise RuntimeError("Quarantine target already exists; no overwrite allowed")
            os.replace(source,target)
        elif not target.is_file() or target.is_symlink() or _file_hash(target)!=file["digest"]:
            raise RuntimeError("Derived artifact missing from both live and verified quarantine")
        conn.execute("UPDATE retention_files SET state='moved' WHERE run_id=? AND source=?",(run_id,str(source)));conn.commit()
    manifest["quarantined_at"]=now
    conn.execute("UPDATE retention_items SET state='quarantined',manifest=?,error=NULL WHERE run_id=? AND generation=?",(json.dumps(manifest),run_id,generation))
    conn.execute("UPDATE generation_records SET state='quarantined' WHERE generation=?",(generation,));conn.commit()


def apply(db, run_id, *, now=None):
    now=time.time() if now is None else now
    with ProcessingLock(),db._lock:
        workspace=Workspace.load(db.project_path); report=status(db,run_id); policy=report["policy"]
        protected,_,fingerprint=_protection(db,policy["keep_previous"],policy["min_age_hours"]*3600,now,run_id)
        if (policy["workspace_id"]!=workspace.data["id"] or policy.get("workspace_revision",0)!=workspace.data.get("revision",0)
                or fingerprint!=report["fingerprint"]):
            raise RuntimeError("Retention plan is stale; inspect a fresh plan before applying")
        conn=db._get_conn()
        for item in report["items"]:
            if item["state"] in ("quarantined","restored","purged"): continue
            generation=item["generation"]
            if generation in protected: raise RuntimeError("Protected generation cannot be quarantined")
            record=dict(conn.execute("SELECT * FROM generation_records WHERE generation=?",(generation,)).fetchone())
            if record["state"] in ("quarantined","purged"):
                raise RuntimeError("Generation was already quarantined by another plan")
            try:
                _archive(db,run_id,record,workspace,now)
            except Exception as exc:
                conn.rollback()
                conn.execute("UPDATE retention_items SET error=? WHERE run_id=? AND generation=?",(str(exc),run_id,generation));conn.commit()
                raise
        conn.execute("UPDATE retention_runs SET state='quarantined',updated=? WHERE id=?",(now,run_id));conn.commit()
        return status(db,run_id)


def restore(db, run_id, generation=None):
    with ProcessingLock(),db._lock:
        workspace=Workspace.load(db.project_path); report=status(db,run_id); conn=db._get_conn()
        for item in report["items"]:
            if generation and generation!=item["generation"]: continue
            if item["state"] in ("planned","restored"): continue
            if item["state"]=="purged": raise RuntimeError("Purged quarantine cannot be restored")
            current=item["generation"]
            pin(db,current,"restored quarantine "+run_id)
            if item["state"]=="archiving":
                # No deletion starts until archive validation completes.
                conn.execute("UPDATE retention_items SET state='restored' WHERE run_id=? AND generation=?",(run_id,current))
                conn.execute("UPDATE generation_records SET retention_owner=NULL WHERE generation=?",(current,));conn.commit()
                continue
            _verify_archive(db,run_id,current,item["manifest"])
            _validate_files(db,workspace,run_id,current)
            for name in COLLECTIONS[conn.execute("SELECT stage FROM generation_records WHERE generation=?",(current,)).fetchone()[0]]:
                raw=_raw(db,name)
                if raw is None: raise RuntimeError("Generation collection unavailable")
                cursor=conn.execute("SELECT payload,digest FROM retention_vectors WHERE run_id=? AND generation=? AND collection_name=? ORDER BY row_id",(run_id,current,name))
                while True:
                    rows=cursor.fetchmany(BATCH)
                    if not rows: break
                    payloads=[_unpack(row[0],row[1]) for row in rows]
                    # Chroma rejects None inside a documents list. Preserve mixed
                    # document/no-document rows by restoring two bounded groups.
                    for has_document in (False,True):
                        group=[p for p in payloads if (p["document"] is not None)==has_document]
                        if not group: continue
                        kwargs=dict(ids=[p["id"] for p in group],embeddings=[p["embedding"] for p in group],metadatas=[p["metadata"] for p in group])
                        if has_document: kwargs["documents"]=[p["document"] for p in group]
                        raw.upsert(**kwargs)
            for file in conn.execute("SELECT * FROM retention_files WHERE run_id=? AND generation=?",(run_id,current)):
                source,target=Path(file["source"]),Path(file["target"])
                kind=conn.execute("SELECT kind FROM generation_artifacts WHERE generation=? AND path=?",(current,str(source))).fetchone()[0]
                _owned_path(workspace,current,source,kind)
                if source.exists():
                    if _file_hash(source)!=file["digest"]: raise RuntimeError("Restore never overwrites a different live artifact")
                else:
                    if target.is_symlink() or not target.is_file() or _file_hash(target)!=file["digest"]: raise RuntimeError("Quarantine checksum failed")
                    if not source.parent.is_dir(): raise RuntimeError("Original artifact directory missing; no root recreation")
                    os.replace(target,source)
                conn.execute("UPDATE retention_files SET state='restored' WHERE run_id=? AND source=?",(run_id,str(source)));conn.commit()
            conn.execute("UPDATE retention_items SET state='restored',error=NULL WHERE run_id=? AND generation=?",(run_id,current))
            conn.execute("UPDATE generation_records SET state='retired',retention_owner=NULL WHERE generation=?",(current,));conn.commit()
        return status(db,run_id)


def purge(db, run_id, min_quarantine_days=7, *, now=None):
    if not math.isfinite(min_quarantine_days) or min_quarantine_days<0: raise ValueError("Purge age must be finite and nonnegative")
    now=time.time() if now is None else now
    with ProcessingLock(),db._lock:
        workspace=Workspace.load(db.project_path); report=status(db,run_id); conn=db._get_conn()
        protected,_,_=_protection(db,0,0,now,run_id)
        for item in report["items"]:
            if item["state"]!="quarantined": continue
            current=item["generation"]
            if current in protected: raise RuntimeError("Active/pinned/job-referenced generation cannot be purged")
            if now-item["manifest"]["quarantined_at"] < min_quarantine_days*86400:
                raise RuntimeError("Quarantine cooling period has not elapsed")
            _verify_archive(db,run_id,current,item["manifest"])
            _validate_files(db,workspace,run_id,current)
            for file in conn.execute("SELECT * FROM retention_files WHERE run_id=? AND generation=?",(run_id,current)):
                target=Path(file["target"])
                base=Path(workspace.output_for(file["source"])["path"])/("cyne-"+workspace.data["id"])/"quarantine"/run_id/current
                if base not in target.parents or target.is_symlink() or target.parent.resolve()!=target.parent: raise RuntimeError("Unsafe quarantine path")
                if target.exists():
                    if _file_hash(target)!=file["digest"]: raise RuntimeError("Quarantine file changed; not purged")
                    target.unlink()
                conn.execute("UPDATE retention_files SET state='purged' WHERE run_id=? AND source=?",(run_id,file["source"]));conn.commit()
            conn.execute("UPDATE retention_vectors SET payload=NULL WHERE run_id=? AND generation=?",(run_id,current))
            conn.execute("UPDATE retention_items SET state='purged' WHERE run_id=? AND generation=?",(run_id,current))
            conn.execute("UPDATE generation_records SET state='purged' WHERE generation=?",(current,));conn.commit()
        return status(db,run_id)
