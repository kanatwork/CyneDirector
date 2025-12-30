# [FILE: core/database.py]
import sqlite3
import json
import os
import threading
import time
import chromadb
from core.logger import get_logger

logger = get_logger(__name__)

class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, project_path=None):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.project_path = project_path
            cls._instance.conn = None
        return cls._instance

    def initialize(self, project_path):
        logger.debug(f"Initializing database for project: {project_path}")
        self.project_path = project_path
        
        # 1. Setup Main DB Folder
        db_path = os.path.join(project_path, "_cyne_db")
        os.makedirs(db_path, exist_ok=True)
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
        
        logger.info("Database initialization completed successfully")

    def _init_sqlite(self):
        """Creates the SQLite table if it doesn't exist."""
        # check_same_thread=False allows Workers to write to DB safely
        self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row # Access columns by name
        
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS video_metadata (
                    video_path TEXT PRIMARY KEY,
                    last_scanned REAL,
                    json_data TEXT
                )
            """)
            # Create index for ultra-fast lookups
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_path ON video_metadata(video_path)")

    # --- INTERNAL SQL HELPERS ---
    
    def _get_data(self, video_path):
        """Internal: Fetch metadata dict from SQLite."""
        with self._lock:
            try:
                cursor = self.conn.execute("SELECT json_data FROM video_metadata WHERE video_path = ?", (video_path,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row['json_data'])
            except Exception as e:
                logger.error(f"SQL Read Error: {e}")
            return {}

    def _save_data(self, video_path, data):
        """Internal: Save metadata dict to SQLite."""
        # Only update last_scanned if not already set (preserve original scan time)
        if "last_scanned" not in data:
            data["last_scanned"] = time.time()
        json_str = json.dumps(data)
        
        with self._lock:
            try:
                self.conn.execute("""
                    INSERT INTO video_metadata (video_path, last_scanned, json_data)
                    VALUES (?, ?, ?)
                    ON CONFLICT(video_path) DO UPDATE SET
                        last_scanned = excluded.last_scanned,
                        json_data = excluded.json_data
                """, (video_path, data["last_scanned"], json_str))
                self.conn.commit()
            except Exception as e:
                logger.error(f"SQL Save Error: {e}")

    # --- PUBLIC API (Compatible with MainWindow) ---

    def get_video_metadata(self, video_path):
        return self._get_data(video_path)

    def save_tags(self, video_path, tags, summary_text):
        data = self._get_data(video_path)
        data["tags"] = tags
        data["summary"] = summary_text
        self._save_data(video_path, data)
    
    def save_shot_type(self, video_path, shot_type):
        data = self._get_data(video_path)
        data["shot_type"] = shot_type
        self._save_data(video_path, data)

    def save_transcript(self, video_path, transcript_list):
        data = self._get_data(video_path)
        data["transcript"] = transcript_list
        self._save_data(video_path, data)

    def save_summary(self, video_path, summary_text):
        data = self._get_data(video_path)
        data["summary"] = summary_text
        self._save_data(video_path, data)

    def update_metadata_key(self, video_path, key, value):
        data = self._get_data(video_path)
        data[key] = value
        self._save_data(video_path, data)

    def clear_metadata_keys(self, video_path, keys_to_remove):
        data = self._get_data(video_path)
        changed = False
        for key in keys_to_remove:
            if key in data:
                del data[key]
                changed = True
        if changed:
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
        data = self._get_data(video_path)
        data["scene_segments"] = scenes
        self._save_data(video_path, data)

    def close(self):
        if self.conn:
            self.conn.close()