"""Read-only media roots and explicit, pinned write destinations (no Qt/AI).

Configuration is additive. Existing project databases/artifacts are never moved.
Preflight reports estimates, not a guarantee against another process filling disk.
"""
import json
import math
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from contextlib import contextmanager
import threading
import time

GIB = 1024 ** 3
STAGES = ("inventory", "index_visuals", "transcribe_audio")
DIR_FD_SUPPORTED = os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd
_configuration_threads=threading.RLock()


@contextmanager
def configuration_lock(project):
    """Serialize submissions/config replacements, including across processes."""
    from core.processing_lock import ProjectSession,ProcessingBusy
    folder=Path(project)/"_cyne_db"
    if not folder.is_dir() or folder.is_symlink():
        raise WorkspaceError("configuration","Configure the project before updating it")
    with _configuration_threads:
        deadline=time.monotonic()+10
        while True:
            try:
                lock=ProjectSession(folder/"workspace-config.lock");break
            except ProcessingBusy:
                if time.monotonic()>=deadline: raise
                time.sleep(.05)
        try: yield
        finally: lock.close()


class WorkspaceError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def inside(path, parent):
    return path == parent or parent in path.parents


def identity(path):
    """Pin the directory as well as the volume; never create a missing mount."""
    path = Path(path).resolve(strict=True)
    stat = path.stat()
    result = {"device": stat.st_dev, "inode": stat.st_ino}
    if sys.platform == "darwin":
        try:
            raw = subprocess.check_output(["diskutil", "info", "-plist", str(path)], timeout=10)
            info = plistlib.loads(raw)
            if info.get("VolumeUUID"):
                result["volume_uuid"] = info["VolumeUUID"]
        except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException):
            pass
    return result


def probe(path):
    """Read stream metadata only, including exact rational rates and source TC."""
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                                 "-of", "json", str(path)], capture_output=True, text=True,
                                check=True, timeout=30)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not any(s.get("codec_type") in ("audio", "video") for s in streams):
            raise ValueError("No audio/video streams")
        duration = float(data.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("No usable duration")
        return {"duration": duration, "streams": streams, "format": data.get("format", {})}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("unsupported_media", f"Cannot probe {path}: {exc}") from exc


class Workspace:
    def __init__(self, project, data, *, check=True):
        self.project = Path(project).resolve(strict=True)
        self.data = data
        self._verified = {}
        if data.get("version") != 1:
            raise WorkspaceError("configuration", "Unsupported workspace configuration version")
        if not isinstance(data.get("id"), str) or len(data["id"]) != 32 or not data["id"].isalnum():
            raise WorkspaceError("configuration", "Invalid workspace identifier")
        reserve = data.get("reserve_bytes")
        if type(reserve) is not int or reserve < 0:
            raise WorkspaceError("configuration", "reserve_bytes must be a non-negative integer")
        self.reserve = reserve
        revision=data.get("revision",0)
        if type(revision) is not int or revision<0:
            raise WorkspaceError("configuration","Invalid workspace revision")
        if check:
            self.check_locations()

    @classmethod
    def path(cls, project):
        return Path(project) / "_cyne_db" / "workspace.json"

    @classmethod
    def load(cls, project, *, check=True):
        try:
            return cls(project, json.loads(cls.path(project).read_text()), check=check)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WorkspaceError("configuration", f"Configure Workspace & Jobs first: {exc}") from exc

    @classmethod
    def configure(cls, project, media_roots, output, model_cache, reserve_bytes=20 * GIB):
        """All destinations must already exist. No mkdir in /Volumes fallbacks."""
        if not media_roots or any(not str(p).strip() for p in media_roots) or not str(output).strip() or not str(model_cache).strip():
            raise WorkspaceError("configuration", "Select explicit, nonempty media and destination folders")
        project = Path(project).resolve(strict=True)
        config = cls.path(project)
        if config.parent.is_symlink():
            raise WorkspaceError("unsafe_destination", "Project database directory may not be a symlink")
        if config.exists():
            raise WorkspaceError("configuration", "Workspace already configured; create a new project to change destinations")
        roots = list(dict.fromkeys(Path(p).resolve(strict=True) for p in media_roots))
        destinations = {"project": project, "output": Path(output).resolve(strict=True),
                        "models": Path(model_cache).resolve(strict=True)}
        data = {"version": 1, "id": uuid.uuid4().hex, "reserve_bytes": reserve_bytes,
                "media_roots": [{"id": uuid.uuid4().hex, "path": str(p), "identity": identity(p)} for p in roots],
                "destinations": {k: {"path": str(p), "identity": identity(p)} for k, p in destinations.items()}}
        workspace = cls(project, data)
        # New sidecar only. The .cyne/settings/metadata/Chroma stores are untouched.
        config.parent.mkdir(exist_ok=True)
        from core.processing_lock import ProjectSession
        lock = ProjectSession(config.parent / "workspace-config.lock")
        tmp = None
        try:
            if config.exists():
                raise WorkspaceError("configuration", "Workspace was configured by another process")
            fd, tmp = tempfile.mkstemp(prefix="workspace-", suffix=".tmp", dir=config.parent)
            with os.fdopen(fd, "w") as handle:
                json.dump(data, handle, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(tmp, config)  # Works on exFAT too; no hard-link requirement.
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
            lock.close()
        return workspace

    def check_locations(self):
        try:
            roots = self.data["media_roots"]
            destinations = self.data["destinations"]
            if not roots or set(destinations) != {"project", "output", "models"}:
                raise WorkspaceError("configuration", "Media roots and all three destinations are required")
            paths = []
            for location in roots + list(destinations.values()):
                path = Path(location["path"])
                expected = location["identity"]
                stat = path.stat() if path.is_dir() else None
                fast = (stat.st_dev, stat.st_ino) if stat else None
                actual = self._verified.get(str(path))
                if actual != fast or actual is None:
                    actual_id = identity(path) if stat else {}
                    # Volume UUID survives a remount with a changed device number.
                    keys = ("volume_uuid", "inode") if "volume_uuid" in expected else ("device", "inode")
                    if any(actual_id.get(k) != expected.get(k) for k in keys):
                        raise WorkspaceError("waiting_media", f"Directory/volume missing or replaced: {path}")
                    self._verified[str(path)] = fast
                if stat is None or path.resolve() != path:
                    raise WorkspaceError("waiting_media", f"Directory/volume missing or replaced: {path}")
                paths.append(path)
            if Path(destinations["project"]["path"]) != self.project:
                raise WorkspaceError("configuration", "Workspace belongs to a different project directory")
            for source in paths[:len(roots)]:
                for dest in paths[len(roots):]:
                    if inside(dest, source) or inside(source, dest):
                        raise WorkspaceError("unsafe_destination", f"Separate original media and write destinations: {source} / {dest}")
            for dest in paths[len(roots):]:
                if not os.access(dest, os.W_OK):
                    raise WorkspaceError("unwritable", f"Destination is not writable: {dest}")
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise WorkspaceError("configuration", str(exc)) from exc

    def asset(self, path, check=True):
        if check:
            self.check_locations()
        root, relative = self.locate(path)
        actual = self.resolve_source(path)
        stat = Path(actual).stat()
        return {"root_id":root["id"], "relative_path":relative,
                "path":self.source_key(path), "resolved_path":actual,
                "signature":[stat.st_mtime_ns,stat.st_size]}

    def locate(self, path):
        """Map current or historical paths without trusting a replacement mount."""
        original=Path(os.path.abspath(path))
        canonical=Path(os.path.realpath(original))
        candidates={original,canonical}
        matches=[]
        by_id={r["id"]:r for r in self.data["media_roots"]}
        if not hasattr(self,"_binding_lookup"):
            self._binding_lookup={}
            for root_id,bindings in self.data.get("source_bindings",{}).items():
                for relative,binding in bindings.items():
                    if Path(relative).is_absolute() or '..' in Path(relative).parts or root_id not in by_id:
                        raise WorkspaceError("configuration","Invalid source binding")
                    for alias in [binding["key"]]+binding.get("aliases",[]):
                        self._binding_lookup.setdefault(Path(alias),[]).append((root_id,relative))
        for candidate in candidates:
            for root_id,relative in self._binding_lookup.get(candidate,[]):
                matches.append((100000,by_id[root_id],relative))
        for root in self.data["media_roots"]:
            for alias in set([root["path"]]+root.get("aliases",[])):
                parent=Path(alias)
                for candidate in candidates:
                    if inside(candidate,parent) and candidate!=parent:
                        matches.append((len(parent.parts)*2+int(candidate==canonical),root,str(candidate.relative_to(parent))))
        if not matches:
            raise WorkspaceError("unsafe_source",f"Source is outside registered media roots: {path}")
        matches.sort(key=lambda row:row[0],reverse=True)
        _,root,relative=matches[0]
        if any((r[1]["id"],r[2])!=(root["id"],relative) and r[0]==matches[0][0] for r in matches):
            raise WorkspaceError("configuration","Source has ambiguous root aliases")
        return root,relative

    def source_key(self,path):
        root,relative=self.locate(path)
        binding=self.data.get("source_bindings",{}).get(root["id"],{}).get(relative)
        if binding: return binding["key"]
        if root.get("origin_path"):
            return str(Path(root["origin_path"])/relative)
        return os.path.abspath(path)

    def resolve_source(self,path):
        root,relative=self.locate(path)
        self.check_location(root)
        proposed=Path(root["path"])/relative
        try:
            actual = proposed.resolve(strict=True)
        except FileNotFoundError as exc:
            raise WorkspaceError("waiting_media", f"Source missing: {path}") from exc
        if not inside(actual,Path(root["path"])):
            raise WorkspaceError("unsafe_source",f"Source escapes its registered root: {path}")
        if not actual.is_file():
            raise WorkspaceError("waiting_media", f"Not a source file: {path}")
        return str(actual)

    def check_location(self,location):
        path=Path(location["path"])
        if not path.is_dir() or path.resolve()!=path:
            raise WorkspaceError("waiting_media",f"Directory/volume missing or replaced: {path}")
        stat=path.stat()
        if self._verified.get(str(path))==(stat.st_dev,stat.st_ino): return
        expected=location["identity"];actual=identity(path)
        keys=("volume_uuid","inode") if "volume_uuid" in expected else ("device","inode")
        if any(actual.get(k)!=expected.get(k) for k in keys):
            raise WorkspaceError("waiting_media",f"Directory/volume missing or replaced: {path}")
        stat=path.stat();self._verified[str(path)]=(stat.st_dev,stat.st_ino)

    def output_locations(self):
        return [self.data["destinations"]["output"]]+self.data.get("output_history",[])

    def output_for(self,path):
        for location in self.output_locations():
            if inside(Path(path),Path(location["path"])/("cyne-"+self.data["id"])):
                self.check_location(location)
                return location
        raise WorkspaceError("unsafe_destination","Artifact is outside all pinned output locations")

    def artifact_dir(self, kind, generation, *, output=None):
        self.check_locations()
        if kind not in ("thumbnails", "proxies", "logs", "temporary", "quarantine") or not generation.isalnum():
            raise WorkspaceError("configuration", "Invalid artifact namespace")
        location=output or self.data["destinations"]["output"]
        if location not in self.output_locations():
            raise WorkspaceError("unsafe_destination","Unknown output location")
        self.check_location(location)
        base = Path(location["path"])
        target = base / ("cyne-" + self.data["id"]) / kind / generation
        if not inside(target.resolve(), base):
            raise WorkspaceError("unsafe_destination", "Artifact directory escapes workspace")
        parts = ("cyne-" + self.data["id"], kind, generation)
        if DIR_FD_SUPPORTED:
            # Anchor creation to the opened volume, never to a replacement mount
            # path. A forced eject yields an IO failure rather than internal mkdir.
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(base, flags)
            try:
                stat = os.fstat(fd)
                if (stat.st_dev, stat.st_ino) != self._verified[str(base)]:
                    raise WorkspaceError("waiting_media", "Output directory changed during creation")
                for part in parts:
                    try:
                        os.mkdir(part, dir_fd=fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(part, flags, dir_fd=fd)
                    os.close(fd); fd = next_fd
            finally:
                os.close(fd)
        else:
            current = base
            for part in parts:
                self.check_locations()
                current = current / part
                current.mkdir(exist_ok=True)  # Never recursively recreate the root.
        self.check_locations()
        self.check_location(location)
        return target

    def preflight(self, files, stages, settings, *, probe_fn=probe, disk_usage=shutil.disk_usage):
        from core.memory_budget import MemoryPolicy,MemoryBudgetExceeded
        memory=MemoryPolicy.from_settings(settings)
        self.check_locations()
        if not stages or set(stages) - set(STAGES):
            raise WorkspaceError("configuration", "Unsupported/empty stage list")
        # Group by actual filesystem: project, model cache and outputs may share it.
        demands = {key: 0 for key in self.data["destinations"]}
        demands["project"] = 16 * 1024 ** 2
        details, peak, errors = [], 0, []
        speech_peak=0
        for path in dict.fromkeys(files):
            asset = self.asset(path, check=False)
            try:
                meta = probe_fn(asset["resolved_path"])
            except WorkspaceError as exc:
                if exc.code != "unsupported_media":
                    raise
                errors.append({"path": asset["path"], "error": str(exc)})
                continue
            seconds = meta["duration"]
            if "index_visuals" in stages and not any(s.get("codec_type") == "video" for s in meta["streams"]):
                errors.append({"path": asset["path"], "error": "Visual indexing requires video", "stages": ["index_visuals"]})
            if "index_visuals" in stages:
                try:
                    for stream in meta["streams"]:
                        if stream.get("codec_type")=="video": memory.dimensions(int(stream.get("width",0)),int(stream.get("height",0)))
                except MemoryBudgetExceeded as exc:
                    errors.append({"path":asset["path"],"error":str(exc),"stages":["index_visuals"]})
            if "transcribe_audio" in stages:
                speech_peak=max(speech_peak,int(min(seconds,memory.speech_seconds+4)*32000)+4096)
            index = int(seconds * 16384 + 2 * 1024 ** 2) if "index_visuals" in stages else 0
            speech = int(seconds * 4096 + 1024 ** 2) if "transcribe_audio" in stages else 0
            demands["project"] += index + speech
            output = 0
            if "index_visuals" in stages:
                output += 2 * 1024 ** 2 if settings.get("generate_thumbnails", True) else 0
                # Current preview encoder is CRF, so this is an explicit estimate.
                output += int(seconds * 4_000_000 / 8 * 1.25) if settings.get("generate_proxies", False) else 0
            demands["output"] += output
            peak = max(peak, output)
            details.append(dict(asset, metadata=meta, estimated_output_bytes=output))
        demands["output"] += max(peak,speech_peak)  # one concurrent derivative/PCM window
        volumes = {}
        for role, loc in self.data["destinations"].items():
            path = Path(loc["path"])
            device = str(path.stat().st_dev)
            group = volumes.setdefault(device, {"paths": [], "estimated_additional_bytes": 0,
                                                "free_bytes": disk_usage(path).free})
            group["paths"].append(str(path))
            group["estimated_additional_bytes"] += demands[role]
            group["free_bytes"] = min(group["free_bytes"], disk_usage(path).free)
        for group in volumes.values():
            group["reserve_bytes"] = self.reserve
            group["required_bytes"] = group["estimated_additional_bytes"] + self.reserve
            group["ok"] = group["free_bytes"] >= group["required_bytes"]
        capacity_ok = all(v["ok"] for v in volumes.values())
        return {"ok": capacity_ok and not errors, "capacity_ok": capacity_ok, "errors": errors, "volumes": list(volumes.values()),
                "assets": details, "model_policy": "cached only; no job-initiated downloads",
                "memory_policy": memory.describe(), "temporary_pcm_bytes": speech_peak,
                "estimate_policy": "16 KiB/s visual + 4 KiB/s speech, 4 Mbps CRF proxy estimate ×1.25, one concurrent temporary proxy/PCM window; existing generations retained"}


def artifact_directory(project, kind, generation):
    # Legacy reads remain where they are; only configured future writes relocate.
    workspace=Workspace.load(project)
    directory=workspace.artifact_dir(kind,generation)
    if kind in ("thumbnails","proxies"):
        import sqlite3
        from core.proxy_generator import _safe_stem
        from core.retention import register_artifact
        with sqlite3.connect(Path(project)/"_cyne_db"/"metadata.db") as conn:
            source=conn.execute("SELECT source FROM generation_records WHERE generation=?",(generation,)).fetchone()
        if not source: raise RuntimeError("Untracked artifact generation")
        name=_safe_stem(source[0])+("_thumb.jpg" if kind=="thumbnails" else "_proxy.mp4")
        register_artifact(project,generation,directory/name,kind)
    return str(directory)
