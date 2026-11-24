# [FILE: core/database.py]
import sqlite3
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
import chromadb
from core.logger import get_logger
from core.generations import PublishedCollection, StageUpdate
from core.source_state import source_signature as get_source_signature

logger = get_logger(__name__)

class Database:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, project_path=None):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.project_path = project_path
            cls._instance._local = threading.local()
            cls._instance._connections = []
            cls._instance._conn_lock = threading.Lock()
            cls._instance._active_generations = set()
        return cls._instance

    def initialize(self, project_path):
        logger.debug(f"Initializing database for project: {project_path}")
        if getattr(self, "sqlite_path", None) and self.project_path != project_path:
            self.close()
        self.project_path = project_path
        
        # 1. Setup Main DB Folder
        db_path = os.path.join(project_path, "_cyne_db")
        os.makedirs(db_path, exist_ok=True)
        if not getattr(self, "_session", None):
            from core.processing_lock import ProjectSession
            self._session = ProjectSession(os.path.join(db_path, "data-session.lock"))
        logger.debug(f"Database folder created: {db_path}")
        
        # 2. Initialize SQLite for Metadata (Replaces JSON Sidecars)
        self.sqlite_path = os.path.join(db_path, "metadata.db")
        self._init_sqlite()
        
        # 3. Setup Vector DB (ChromaDB) with optimized settings
        logger.debug("Creating ChromaDB client")
        self.client = chromadb.PersistentClient(path=db_path)
        logger.debug("ChromaDB client created")
        
        # Try to get existing collections first, then create with metadata if they don't exist
        # This handles the case where collections exist with old metadata format
        try:
            logger.debug("Attempting to get existing visuals collection")
            # Try to get existing collection first
            try:
                self.visuals = self.client.get_collection(name="visual_embeddings")
                logger.debug(f"Got existing visuals collection (count: {self.visuals.count()})")
            except:
                # Collection doesn't exist, create with optimized metadata
                logger.debug("Creating new visuals collection with metadata")
                # Use minimal metadata to avoid parsing issues
                # ChromaDB may have issues with custom HNSW parameters in some versions
                visuals_metadata = {"hnsw:space": "cosine"}
                self.visuals = self.client.create_collection(
                    name="visual_embeddings", 
                    metadata=visuals_metadata
                )
                logger.debug("Created visuals collection")
        except Exception as e:
            logger.warning(f"Error creating visuals collection: {e}, trying fallback")
            # Fallback: try without any metadata
            try:
                self.visuals = self.client.get_or_create_collection(name="visual_embeddings")
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                raise e2
        
        # Keep faces collection for backward compatibility but don't actively use it
        try:
            logger.debug("Attempting faces collection")
            try:
                self.faces = self.client.get_collection(name="face_embeddings")
            except:
                self.faces = self.client.create_collection(name="face_embeddings", metadata={"hnsw:space": "cosine"})
        except:
            logger.warning("Could not initialize faces collection")
            self.faces = None
        
        # Transcripts collection
        try:
            logger.debug("Attempting transcripts collection")
            try:
                self.transcripts = self.client.get_collection(name="transcripts")
            except:
                self.transcripts = self.client.create_collection(name="transcripts", metadata={"hnsw:space": "cosine"})
        except Exception as e:
            logger.error(f"Error with transcripts collection: {e}")
            raise
        
        # Temporal sequences for temporal search
        try:
            logger.debug("Attempting temporal_sequences collection")
            try:
                self.temporal_sequences = self.client.get_collection(name="temporal_sequences")
            except:
                self.temporal_sequences = self.client.create_collection(name="temporal_sequences", metadata={"hnsw:space": "cosine"})
        except Exception as e:
            logger.warning(f"Error with temporal_sequences collection: {e} (optional, continuing)")
            # Temporal sequences are optional, so don't fail if they can't be created
            self.temporal_sequences = None
        
        for name, stage in (("visuals", "visual"), ("temporal_sequences", "visual"), ("transcripts", "transcript")):
            raw = getattr(self, name, None)
            if raw is not None:
                setattr(self, name, PublishedCollection(raw, self, stage))
        logger.info("Database initialization completed successfully")

    def _init_sqlite(self):
        """Initialize SQLite schema with WAL mode for safe concurrent access.

        Each thread gets its own connection via _get_conn(). WAL mode allows
        concurrent readers alongside a single writer, and busy_timeout makes
        writers wait instead of failing immediately on contention.
        """
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS video_metadata (
                video_path TEXT PRIMARY KEY,
                last_scanned REAL,
                json_data TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON video_metadata(video_path)")
        conn.commit()
        from core.retention import initialize
        initialize(self)

    def _get_conn(self):
        """Return a thread-local SQLite connection with WAL mode enabled."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
            with self._conn_lock:
                self._connections.append(conn)
        return self._local.conn

    # --- INTERNAL SQL HELPERS ---
    # These must be called with self._lock already held.

    def _get_data(self, video_path):
        """Internal: Fetch metadata dict from SQLite. Caller must hold _lock."""
        video_path=self.source_key(video_path)
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT json_data FROM video_metadata WHERE video_path = ?", (video_path,))
            row = cursor.fetchone()
            if row:
                return json.loads(row['json_data'])
        except Exception as e:
            logger.error(f"SQL Read Error: {e}")
            raise
        return {}

    def _save_data(self, video_path, data):
        """Internal: Save metadata dict to SQLite. Caller must hold _lock."""
        video_path=self.source_key(video_path)
        if "last_scanned" not in data:
            data["last_scanned"] = time.time()
        publication = getattr(self._local, "generation_publication", None)
        if publication:
            publication["policy"].validate(data)
        json_str = json.dumps(data,ensure_ascii=not bool(publication),allow_nan=not bool(publication))
        conn = None
        try:
            conn = self._get_conn()
            prior = conn.execute("SELECT json_extract(json_data,'$.visual_generation'),json_extract(json_data,'$.transcript_generation') FROM video_metadata WHERE video_path=?",(video_path,)).fetchone()
            conn.execute("""
                INSERT INTO video_metadata (video_path, last_scanned, json_data)
                VALUES (?, ?, ?)
                ON CONFLICT(video_path) DO UPDATE SET
                    last_scanned = excluded.last_scanned,
                    json_data = excluded.json_data
            """, (video_path, data["last_scanned"], json_str))
            if publication:
                now = time.time()
                conn.execute("UPDATE generation_records SET state='published',published=? WHERE generation=?", (now,publication["generation"]))
                if publication["previous"]:
                    conn.execute("UPDATE generation_records SET state='retired',retired=? WHERE generation=? AND state='published'", (now,publication["previous"]))
            elif prior:
                for index,stage in enumerate(("visual","transcript")):
                    if prior[index] and prior[index]!=data.get(stage+"_generation"):
                        conn.execute("UPDATE generation_records SET state='retired',retired=? WHERE generation=? AND state='published'",(time.time(),prior[index]))
            conn.commit()
        except Exception as e:
            if conn is not None:
                conn.rollback()
            logger.error(f"SQL Save Error: {e}")
            raise

    # --- PUBLIC API (Compatible with MainWindow) ---
    # Every public method acquires _lock so that read-modify-write
    # sequences are atomic across threads.

    def get_video_metadata(self, video_path):
        with self._lock:
            return self._get_data(video_path)

    def source_key(self,path):
        from core.workspace import Workspace,WorkspaceError
        project=getattr(self,"project_path",None)
        if project and Workspace.path(project).is_file():
            try:
                stat=Workspace.path(project).stat();stamp=(project,stat.st_ino,stat.st_mtime_ns,stat.st_size)
                if getattr(self,"_source_workspace_stamp",None)!=stamp:
                    self._source_workspace=Workspace.load(project,check=False);self._source_workspace_stamp=stamp
                return self._source_workspace.source_key(path)
            except WorkspaceError as exc:
                if exc.code!="unsafe_source": raise
        return path

    def media_path(self,path):
        from core.source_state import media_path
        return media_path(path,getattr(self,"project_path",None))

    def get_bounded_video_metadata(self, video_path, policy):
        with self._lock:
            video_path=self.source_key(video_path)
            row = self._get_conn().execute("""SELECT length(CAST(json_data AS BLOB)),
                CASE WHEN length(CAST(json_data AS BLOB))<=? THEN json_data ELSE NULL END
                FROM video_metadata WHERE video_path=?""", (policy.metadata_bytes, video_path)).fetchone()
            if row and row[1] is None:
                from core.memory_budget import MemoryBudgetExceeded
                raise MemoryBudgetExceeded("Existing metadata exceeds processing budget; existing data left unchanged")
            value = json.loads(row[1]) if row else {}
            policy.validate(value)
            return value

    @contextmanager
    def read_snapshot(self):
        """Keep publication/retention from advancing during composed vector reads."""
        with self._lock:
            yield

    def save_tags(self, video_path, tags, summary_text):
        with self._lock:
            data = self._get_data(video_path)
            data["tags"] = tags
            data["summary"] = summary_text
            self._save_data(video_path, data)

    def save_shot_type(self, video_path, shot_type):
        with self._lock:
            data = self._get_data(video_path)
            data["shot_type"] = shot_type
            self._save_data(video_path, data)

    def save_transcript(self, video_path, transcript_list, source_signature=None):
        signature = source_signature if source_signature is not None else get_source_signature(self.media_path(video_path))
        with self.reprocess(video_path, "transcript", signature) as staged:
            staged.save_transcript(video_path, transcript_list)

    def reprocess(self, path, stage, signature, allowed=lambda: True):
        path=self.source_key(path)
        publication = getattr(self._local, "publication", None)
        predicate = (lambda: allowed() and publication[1]()) if publication else allowed
        update = StageUpdate(self, path, stage, signature, predicate)
        if publication:
            update.update_metadata_key(path, stage + "_job_checkpoint", dict(publication[0], generation=update.generation))
        return update

    @contextmanager
    def publication_context(self, checkpoint, allowed):
        """Commit the job checkpoint in the SAME metadata publication transaction."""
        previous = getattr(self._local, "publication", None)
        self._local.publication = (checkpoint, allowed)
        try:
            yield
        finally:
            self._local.publication = previous

    def ensure_segment_languages(self, video_path):
        """Ensure all transcript segments have language detection.
        Useful for existing transcripts that were created before language detection was added."""
        with self._lock:
            data = self._get_data(video_path)
            transcript = data.get("transcript", [])
            if not transcript or not isinstance(transcript, list):
                return

            updated = False
            from core.translator import detect_segment_language
            for seg in transcript:
                if 'language' not in seg:
                    detect_segment_language(seg)
                    updated = True

            if updated:
                data["transcript"] = transcript
                self._save_data(video_path, data)

    def save_summary(self, video_path, summary_text):
        with self._lock:
            data = self._get_data(video_path)
            data["summary"] = summary_text
            self._save_data(video_path, data)

    def update_metadata_key(self, video_path, key, value):
        with self._lock:
            data = self._get_data(video_path)
            data[key] = value
            self._save_data(video_path, data)

    def clear_metadata_keys(self, video_path, keys_to_remove):
        with self._lock:
            data = self._get_data(video_path)
            if "transcript" in keys_to_remove:
                data["transcript_generation"] = uuid.uuid4().hex
                data.pop("transcript_source_signature", None)
            if "tags" in keys_to_remove:
                data["visual_generation"] = uuid.uuid4().hex
                data.pop("visual_source_signature", None)
            for key in keys_to_remove:
                data.pop(key, None)
            self._save_data(video_path, data)

    def clear_visual_embeddings(self, video_path):
        # A metadata tombstone hides all old generations atomically. Retain the
        # physical records so concurrent readers of an earlier snapshot stay safe.
        with self._lock:
            data = self._get_data(video_path)
            data["visual_generation"] = uuid.uuid4().hex
            data.pop("visual_source_signature", None)
            self._save_data(video_path, data)

    def add_visual_embeddings(self, video_path, vectors, timestamps):
        # OPTIMIZATION: Batch ChromaDB writes for better performance
        if not vectors: return
        
        # Process in chunks to avoid memory issues with very large batches
        chunk_size = 1000
        for i in range(0, len(vectors), chunk_size):
            chunk_vectors = vectors[i:i+chunk_size]
            chunk_timestamps = timestamps[i:i+chunk_size]
            ids = [f"{video_path}_{t}" for t in chunk_timestamps]
            metadatas = [{"source": video_path, "timestamp": t} for t in chunk_timestamps]
            try:
                self.visuals.upsert(ids=ids, embeddings=chunk_vectors, metadatas=metadatas)
            except Exception as e:
                logger.error(f"DB ERROR (chunk {i//chunk_size + 1}): {e}")
                raise

    def add_temporal_sequence(self, video_path, sequence_embedding, start_time, end_time, description=""):
        """Store temporal sequence embedding for temporal search."""
        if sequence_embedding is None:
            return
        seq_id = f"{video_path}_{start_time}_{end_time}"
        metadata = {
            "source": video_path,
            "start_time": start_time,
            "end_time": end_time,
            "duration": end_time - start_time,
            "description": description
        }
        try:
            self.temporal_sequences.upsert(ids=[seq_id], embeddings=[sequence_embedding], metadatas=[metadata])
        except Exception as e:
            logger.error(f"DB ERROR (temporal): {e}")

    def save_scene_segments(self, video_path, scenes):
        """Save scene segmentation data."""
        with self._lock:
            data = self._get_data(video_path)
            data["scene_segments"] = scenes
            self._save_data(video_path, data)

    def close(self):
        """Close all thread-local SQLite connections."""
        with self._conn_lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
        self._local = threading.local()
        self.client = None
        self._active_generations.clear()
        if getattr(self, "_session", None):
            self._session.close()
            self._session = None
