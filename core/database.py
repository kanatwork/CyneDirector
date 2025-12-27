import chromadb
import json
import os
import threading
import time
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
        db_path = os.path.join(project_path, "_cyne_db")
        os.makedirs(db_path, exist_ok=True)
        
        # Use a persistent client
        self.client = chromadb.PersistentClient(path=db_path)
        self.visuals = self.client.get_or_create_collection(name="visual_embeddings", metadata={"hnsw:space": "cosine"})
        self.faces = self.client.get_or_create_collection(name="face_embeddings", metadata={"hnsw:space": "cosine"})
        self.transcripts = self.client.get_or_create_collection(name="transcripts", metadata={"hnsw:space": "cosine"})

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
        data["last_scanned"] = str(os.path.getmtime(meta_path.replace(".json", "")))
        
        with self._lock:
            temp_path = meta_path + ".tmp"
            try:
                # 1. Write to temp
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                
                # 2. Retry Loop for Windows Rename (Fix for "Permission Denied")
                retries = 3
                while retries > 0:
                    try:
                        os.replace(temp_path, meta_path)
                        break
                    except OSError:
                        retries -= 1
                        time.sleep(0.1) # Wait for file lock to release
                
            except Exception as e:
                print(f"Save Error: {e}")

    # Wrappers remain the same, they use the robust private methods above
    def get_video_metadata(self, video_path):
        meta_path = f"{video_path}.json"
        return self._load_metadata(meta_path)

    def save_tags(self, video_path, tags, summary_text):
        meta_path = f"{video_path}.json"
        data = self._load_metadata(meta_path)
        data["tags"] = tags
        data["summary"] = summary_text
        self._save_metadata_atomic(meta_path, data)

    def save_transcript(self, video_path, transcript_list):
        meta_path = f"{video_path}.json"
        data = self._load_metadata(meta_path)
        data["transcript"] = transcript_list
        self._save_metadata_atomic(meta_path, data)

    def save_summary(self, video_path, summary_text):
        meta_path = f"{video_path}.json"
        data = self._load_metadata(meta_path)
        data["summary"] = summary_text
        self._save_metadata_atomic(meta_path, data)

    def update_metadata_key(self, video_path, key, value):
        meta_path = f"{video_path}.json"
        data = self._load_metadata(meta_path)
        data[key] = value
        self._save_metadata_atomic(meta_path, data)

    def clear_metadata_keys(self, video_path, keys_to_remove):
        meta_path = f"{video_path}.json"
        if not os.path.exists(meta_path): return
        data = self._load_metadata(meta_path)
        changed = False
        for key in keys_to_remove:
            if key in data:
                del data[key]
                changed = True
        if changed:
            self._save_metadata_atomic(meta_path, data)