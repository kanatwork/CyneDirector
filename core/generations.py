"""Immutable vector generations, published by one SQLite metadata commit.

Old and abandoned vectors remain until explicit verified retention. Readers select only the generation named
in SQLite, including legacy vectors (no generation) for unmigrated projects.
No cross-store transaction or destructive rollback is assumed.
"""
import copy
import uuid
import time
import math
import heapq
from core.memory_budget import MemoryPolicy
from core.source_state import source_signature


class ReprocessingAborted(RuntimeError):
    pass


class PublishedCollection:
    def __init__(self, raw, db, stage):
        self.raw, self.db, self.stage = raw, db, stage

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def _snapshot(self):
        import json
        with self.db._lock:
            rows = self.db._get_conn().execute("SELECT video_path,json_extract(json_data, ?) FROM video_metadata", ("$."+self.stage+"_generation",))
            return {r[0]: r[1] for r in rows}

    @staticmethod
    def _visible(meta, snapshot):
        meta = meta or {}
        return meta.get("generation") == snapshot.get(meta.get("source"))

    def get(self, **kwargs):
        with self.db._lock:
            return self._get_locked(**kwargs)

    def _get_locked(self, **kwargs):
        snapshot = self._snapshot()
        requested = kwargs.pop("include", ["metadatas", "documents"])
        offset, limit = kwargs.pop("offset", 0) or 0, kwargs.pop("limit", None)
        result = self.raw.get(include=list(dict.fromkeys(requested + ["metadatas"])), **kwargs)
        indices = [i for i, m in enumerate(result["metadatas"]) if self._visible(m, snapshot)]
        indices = indices[offset:] if limit is None else indices[offset:offset + limit]
        return {k: ([v[i] for i in indices] if v is not None and k not in ("included",) else v)
                for k, v in result.items() if k != "metadatas" or "metadatas" in requested}

    def count(self):
        with self.db._lock:
            snapshot=self._snapshot();offset=total=0
            while True:
                rows=self.raw.get(include=["metadatas"],limit=64,offset=offset)
                if not rows["ids"]: return total
                total+=sum(self._visible(meta,snapshot) for meta in rows["metadatas"])
                offset+=len(rows["ids"])

    def query(self, **kwargs):
        with self.db._lock:
            return self._query_locked(**kwargs)

    def _query_locked(self, **kwargs):
        snapshot = self._snapshot()
        requested = kwargs.pop("include", ["metadatas", "documents", "distances"])
        wanted = kwargs.pop("n_results", 10)
        if type(wanted) is not int:
            raise ValueError("n_results must be an integer")
        if wanted>2048:
            raise ValueError("Query result budget is 2048 rows; request smaller pages")
        if wanted <= 0:
            batches = len(kwargs.get("query_embeddings", kwargs.get("query_texts", [[]])))
            return {k: [[] for _ in range(batches)] for k in ["ids"] + requested}
        total = self.raw.count()
        # Inactive generations can occupy nearest-neighbor slots. Widen until
        # enough visible candidates exist, rather than silently losing recall.
        size = min(max(wanted, 1), max(total, 1))
        self.last_query_diagnostics={"mode":"ann","max_candidates":0}
        while True:
            if size>256:
                return self._exact(snapshot,wanted,requested,kwargs)
            self.last_query_diagnostics["max_candidates"]=size
            try:
                result = self.raw.query(n_results=size, include=list(dict.fromkeys(requested + ["metadatas"])), **kwargs)
            except RuntimeError as exc:
                if not any(message in str(exc) for message in ("contigious","contiguous","ef or M")):
                    raise
                return self._exact(snapshot,wanted,requested,kwargs)
            indices = [[i for i, m in enumerate(batch) if self._visible(m, snapshot)]
                       for batch in result["metadatas"]]
            if size >= total or all(len(batch) >= wanted for batch in indices):
                break
            size = min(total, size * 2)
        return {k: ([[batch[i] for i in selected[:wanted]] for batch, selected in zip(v, indices)]
                    if v is not None and k != "included" else v)
                for k, v in result.items() if k != "metadatas" or "metadatas" in requested}

    def _exact(self,snapshot,wanted,requested,kwargs):
        """Bounded heap + vector pages; avoid unbounded ANN oversampling.

        Slower scans are explicit diagnostics, never silently missing active hits.
        Existing application calls supply CLIP embeddings, not query_texts.
        """
        queries=kwargs.get("query_embeddings")
        if queries is None:
            raise ValueError("Bounded fallback requires query_embeddings")
        if hasattr(queries,"tolist"): queries=queries.tolist()
        if queries and isinstance(queries[0],(int,float)): queries=[queries]
        if wanted*len(queries)>2048 or any(len(q)>4096 for q in queries):
            raise ValueError("Query batch exceeds bounded result/dimension budget")
        if any(not math.isfinite(float(x)) for query in queries for x in query):
            raise ValueError("Query embeddings must be finite")
        if set(requested)-{"metadatas","documents","embeddings","distances"}:
            raise ValueError("Unsupported field in bounded vector fallback")
        space=(getattr(self.raw,"metadata",None) or {}).get("hnsw:space","l2")
        norms=[math.sqrt(math.fsum(float(x)**2 for x in q)) for q in queries]
        heaps=[[] for _ in queries];offset=ordinal=0
        filters={key:kwargs[key] for key in ("where","where_document") if key in kwargs}
        while True:
            rows=self.raw.get(include=["metadatas","embeddings","documents"],limit=64,offset=offset,**filters)
            if not rows["ids"]: break
            offset+=len(rows["ids"])
            for index,row_id in enumerate(rows["ids"]):
                meta=rows["metadatas"][index]
                if not self._visible(meta,snapshot): continue
                raw_vector=rows["embeddings"][index]
                vector=raw_vector.tolist() if hasattr(raw_vector,"tolist") else list(raw_vector)
                norm=math.sqrt(math.fsum(float(x)**2 for x in vector)) if space=="cosine" else 0
                document=rows["documents"][index] if rows.get("documents") is not None else None
                for number,query in enumerate(queries):
                    if len(query)!=len(vector): raise ValueError("Query dimension differs from stored vectors")
                    if space=="l2": distance=math.fsum((float(a)-float(b))**2 for a,b in zip(query,vector))
                    else:
                        dot=math.fsum(float(a)*float(b) for a,b in zip(query,vector))
                        distance=1-(dot/(norms[number]*norm) if norms[number]*norm else 0) if space=="cosine" else 1-dot
                    entry=(-distance,-ordinal,row_id,meta,document,vector if "embeddings" in requested else None)
                    heap=heaps[number]
                    if len(heap)<wanted: heapq.heappush(heap,entry)
                    elif entry[:2]>heap[0][:2]: heapq.heapreplace(heap,entry)
                ordinal+=1
        result={key:[] for key in ["ids"]+requested}
        for heap in heaps:
            ordered=sorted(heap,key=lambda row:(-row[0],-row[1]))
            result["ids"].append([row[2] for row in ordered])
            for field in requested:
                result[field].append([(-row[0] if field=="distances" else row[{"metadatas":3,"documents":4,"embeddings":5}[field]]) for row in ordered])
        self.last_query_diagnostics={"mode":"paged_exact","scanned_rows":offset,"max_page_rows":64,
                                     "retained_results":sum(len(heap) for heap in heaps),"max_candidates":256}
        return result


class StagedCollection:
    def __init__(self, raw, source, generation, active, lock):
        self.raw, self.source, self.generation = raw, source, generation
        self.active = active
        self.lock = lock

    def upsert(self, ids, embeddings, metadatas, **kwargs):
        with self.lock:
            if not self.active():
                raise ReprocessingAborted("Staged vector writer is outside its live context")
            self.raw.upsert(ids=[self.generation + ":" + key for key in ids], embeddings=embeddings,
                            metadatas=[dict(m, source=self.source, generation=self.generation) for m in metadatas], **kwargs)


class StageUpdate:
    def __init__(self, db, path, stage, signature, allowed=lambda: True):
        if stage not in ("visual", "transcript"):
            raise ValueError("Unknown processing stage")
        self.db, self.path, self.stage = db, path, stage
        self.signature, self.allowed = signature, allowed
        self.generation = uuid.uuid4().hex
        self.entered = False
        self.policy = getattr(db._local, "memory_policy", MemoryPolicy())
        self.original = db.get_bounded_video_metadata(path, self.policy)
        self.data = copy.deepcopy(self.original)
        self.changed, self.removed = set(), set()
        if stage == "transcript":
            self.clear_metadata_keys(path, ["transcript_language", "transcription_gaps", "transcript_embeddings_status"])
        for name in ("visuals", "temporal_sequences") if stage == "visual" else ("transcripts",):
            collection = getattr(db, name, None)
            if collection is not None:
                raw = getattr(collection, "raw", collection)
                setattr(self, name, StagedCollection(raw, path, self.generation,
                    lambda: self.entered and self.generation in self.db._active_generations,self.db._lock))

    def __enter__(self):
        with self.db._lock:
            conn = self.db._get_conn()
            conn.execute("INSERT INTO generation_records(generation,source,stage,created,state) VALUES(?,?,?,?,'staging')",
                         (self.generation,self.path,self.stage,time.time()))
            conn.commit()
            self.db._active_generations.add(self.generation)
            self.entered = True
        return self

    def __exit__(self, kind, value, tb):
        committed = False
        try:
            if kind is not None:
                return False
            with self.db._lock:
                if not self.entered or self.generation not in self.db._active_generations:
                    raise ReprocessingAborted("Stage no longer owns its writer context")
                if not self.allowed() or self.signature is None or source_signature(self.db.media_path(self.path)) != self.signature:
                    raise ReprocessingAborted("Cancelled, failed, or source changed during processing")
                current = self.db.get_bounded_video_metadata(self.path, self.policy)
                previous = self.original.get(self.stage + "_generation")
                if current.get(self.stage + "_generation") != previous:
                    raise ReprocessingAborted("Another worker published this stage; retry against its new generation")
                for key in self.removed:
                    current.pop(key, None)
                current.update({key: self.data[key] for key in self.changed})
                current[self.stage + "_generation"] = self.generation
                current[self.stage + "_source_signature"] = self.signature
                current["vector_publication_version"] = 1
                old = getattr(self.db._local, "generation_publication", None)
                self.db._local.generation_publication = dict(policy=self.policy,generation=self.generation,previous=previous)
                try:
                    self.db._save_data(self.path, current)
                    committed = True
                finally:
                    self.db._local.generation_publication = old
        finally:
            with self.db._lock:
                self.entered = False
                self.db._active_generations.discard(self.generation)
                if not committed:
                    try:
                        self.db._get_conn().execute("UPDATE generation_records SET state='abandoned',retired=? WHERE generation=? AND state='staging'", (time.time(),self.generation))
                        self.db._get_conn().commit()
                    except Exception:
                        # Original publication error wins; staging remains protected
                        # by grace and can be inspected/recovered after storage repair.
                        try: self.db._get_conn().rollback()
                        except Exception: pass

    def get_video_metadata(self, path):
        assert self.db.source_key(path) == self.path
        return copy.deepcopy(self.data)

    def update_metadata_key(self, path, key, value):
        assert self.db.source_key(path) == self.path
        self.policy.validate(value)
        self.data[key] = value
        self.changed.add(key)
        self.removed.discard(key)

    def clear_metadata_keys(self, path, keys):
        assert self.db.source_key(path) == self.path
        for key in keys:
            self.data.pop(key, None)
            self.changed.discard(key)
            self.removed.add(key)

    def save_tags(self, path, tags, summary):
        self.update_metadata_key(path, "tags", tags)
        self.update_metadata_key(path, "summary", summary)

    def save_summary(self, path, text):
        self.update_metadata_key(path, "summary", text)

    def save_scene_segments(self, path, scenes):
        self.update_metadata_key(path, "scene_segments", scenes)

    def save_transcript(self, path, transcript, source_signature=None):
        self.clear_metadata_keys(path, ["transcript_translated", "translation_timestamp", "translation_method",
                                        "translation_source_signature", "transcript_source_signature"])
        self.update_metadata_key(path, "transcript", transcript)

    def add_visual_embeddings(self, path, vectors, timestamps):
        if vectors:
            self.visuals.upsert(ids=[str(t) for t in timestamps], embeddings=vectors,
                                metadatas=[{"timestamp": t} for t in timestamps])

    def add_temporal_sequence(self, path, vector, start, end, description=""):
        if getattr(self, "temporal_sequences", None) is not None:
            self.temporal_sequences.upsert(ids=[f"{start}:{end}"], embeddings=[vector],
                metadatas=[{"start_time": start, "end_time": end, "duration": end-start, "description": description}])
