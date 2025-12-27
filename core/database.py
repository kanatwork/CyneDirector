import chromadb
import json
import os
import threading
import time
import hashlib
from pathlib import Path

class Database:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, project_path=None):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.client = None
            cls._instance.project_path = project_path
        return cls._instance

    def initialize(self, project_path):
        self.project_path = project_path
        
        # 1. Setup Main DB Folder
        db_path = os.path.join(project_path, "_cyne_db")
        os.makedirs(db_path, exist_ok=True)
        
        # 2. Setup Metadata Folder (The "Safe" Storage)
        self.meta_dir = os.path.join(db_path, "metadata")
        os.makedirs(self.meta_dir, exist_ok=True)
        
        # 3. Setup Vector DB
        self.client = chromadb.PersistentClient(path=db_path)
        self.visuals = self.client.get_or_create_collection(name="visual_embeddings", metadata={"hnsw:space": "cosine"})
        self.faces = self.client.get_or_create_collection(name="face_embeddings", metadata={"hnsw:space": "cosine"})
        self.transcripts = self.client.get_or_create_collection(name="transcripts", metadata={"hnsw:space": "cosine"})

    def _get_meta_path(self, video_path):
        """
        Generates a unique, safe path for the metadata JSON inside _cyne_db.
        Format: HASH_Filename.json
        """
        if not self.project_path:
            raise ValueError("Database not initialized with project path")

        # Normalize path to ensure consistency
        norm_path = os.path.normpath(video_path).lower()
        
        # Create MD5 hash of the full path to prevent collisions
        # (e.g. CameraA/C001.mp4 vs CameraB/C001.mp4)
        path_hash = hashlib.md5(norm_path.encode('utf-8')).hexdigest()
        
        # Keep original filename for readability in debug
        original_name = os.path.basename(video_path)
        safe_name = f"{path_hash}_{original_name}.json"
        
        return os.path.join(self.meta_dir, safe_name)

    def add_visual_embeddings(self, video_path, vectors, timestamps):
        if not vectors: return
        ids = [f"{video_path}_{t}" for t in timestamps]
        metadatas = [{"source": video_path, "timestamp": t} for t in timestamps]
        try:
            self.visuals.upsert(ids=ids, embeddings=vectors, metadatas=metadatas)
        except Exception as e:
            print(f"DB ERROR: {e}")

    # --- METADATA HANDLERS (Robust) ---
    def _load_metadata(self, meta_path):
        with self._lock:
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except: pass
            return {}

    def _save_metadata_atomic(self, meta_path, data):
        data["last_scanned"] = str(time.time())
        
        with self._lock:
            temp_path = meta_path + ".tmp"
            try:
                # 1. Write to temp
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                
                # 2. Retry Loop for Windows Rename (Fix for "Permission Denied")
                retries = 10
                while retries > 0:
                    try:
                        # On Windows, os.replace can fail if destination exists and is locked
                        if os.path.exists(meta_path):
                            try:
                                os.remove(meta_path)
                            except OSError:
                                # If we can't delete the target, we certainly can't replace it
                                raise OSError("Target Locked")
                                
                        os.rename(temp_path, meta_path)
                        break
                    except OSError:
                        retries -= 1
                        time.sleep(0.2) # Wait for file lock to release
                
                if retries == 0:
                    print(f"❌ CRITICAL: Could not save metadata to {meta_path} (File Locked)")

            except Exception as e:
                print(f"Save Error: {e}")

    # Wrappers now use _get_meta_path instead of pollution source folder
    def get_video_metadata(self, video_path):
        meta_path = self._get_meta_path(video_path)
        return self._load_metadata(meta_path)

    def save_tags(self, video_path, tags, summary_text):
        meta_path = self._get_meta_path(video_path)
        data = self._load_metadata(meta_path)
        data["tags"] = tags
        data["summary"] = summary_text
        self._save_metadata_atomic(meta_path, data)

    def save_transcript(self, video_path, transcript_list):
        meta_path = self._get_meta_path(video_path)
        data = self._load_metadata(meta_path)
        data["transcript"] = transcript_list
        self._save_metadata_atomic(meta_path, data)

    def save_summary(self, video_path, summary_text):
        meta_path = self._get_meta_path(video_path)
        data = self._load_metadata(meta_path)
        data["summary"] = summary_text
        self._save_metadata_atomic(meta_path, data)

    def update_metadata_key(self, video_path, key, value):
        meta_path = self._get_meta_path(video_path)
        data = self._load_metadata(meta_path)
        data[key] = value
        self._save_metadata_atomic(meta_path, data)

    def clear_metadata_keys(self, video_path, keys_to_remove):
        meta_path = self._get_meta_path(video_path)
        if not os.path.exists(meta_path): return
        data = self._load_metadata(meta_path)
        changed = False
        for key in keys_to_remove:
            if key in data:
                del data[key]
                changed = True
        if changed:
            self._save_metadata_atomic(meta_path, data)