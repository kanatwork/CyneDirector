import os
import pickle
import json
import threading
import numpy as np
from pathlib import Path

class FaceDB:
    _instance = None
    _lock = threading.Lock() # Global lock for thread safety

    def __new__(cls, project_path=None):
        if cls._instance is None:
            cls._instance = super(FaceDB, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self, project_path=None):
        if self.initialized: return
        if project_path is None: return 
        
        self.project_path = project_path
        self.db_dir = os.path.join(project_path, "_cyne_db", "faces")
        self.encodings_path = os.path.join(self.db_dir, "encodings.pkl")
        self.names_path = os.path.join(self.db_dir, "names.json")
        
        os.makedirs(self.db_dir, exist_ok=True)
        
        self.known_encodings = []
        self.known_ids = []
        self.id_to_name = {}
        
        self.load()
        self.initialized = True

    def load(self):
        with self._lock:
            if os.path.exists(self.names_path):
                try:
                    with open(self.names_path, 'r') as f:
                        self.id_to_name = json.load(f)
                except:
                    self.id_to_name = {}

            if os.path.exists(self.encodings_path):
                try:
                    with open(self.encodings_path, 'rb') as f:
                        data = pickle.load(f)
                        self.known_ids = data.get("ids", [])
                        self.known_encodings = data.get("encodings", [])
                except:
                    self.known_ids = []
                    self.known_encodings = []

    def save_encodings(self):
        with self._lock:
            self._save_encodings_internal()

    def save_names(self):
        with self._lock:
            self._save_names_internal()

    def add_face(self, person_id, encoding):
        # FIX: Locking logic covers the SAVE operation now
        with self._lock:
            self.known_ids.append(person_id)
            self.known_encodings.append(encoding)
            self.id_to_name[person_id] = person_id 
            
            # Save while locked!
            self._save_encodings_internal()
            self._save_names_internal()

    def rename_person(self, person_id, new_name):
        with self._lock:
            if person_id in self.id_to_name:
                self.id_to_name[person_id] = new_name
            self._save_names_internal()

    def remove_person(self, person_id):
        with self._lock:
            if person_id in self.id_to_name:
                del self.id_to_name[person_id]

            if person_id in self.known_ids:
                new_ids = []
                new_encodings = []
                for pid, enc in zip(self.known_ids, self.known_encodings):
                    if pid != person_id:
                        new_ids.append(pid)
                        new_encodings.append(enc)
                
                self.known_ids = new_ids
                self.known_encodings = new_encodings
        
            self._save_names_internal()
            self._save_encodings_internal()

    def get_name(self, person_id):
        return self.id_to_name.get(person_id, person_id)

    def get_next_id(self):
        with self._lock:
            return f"Person_{len(self.id_to_name) + 100}"

    # Helpers (Assume Lock is already held)
    def _save_encodings_internal(self):
        data = { "ids": self.known_ids, "encodings": self.known_encodings }
        with open(self.encodings_path, 'wb') as f:
            pickle.dump(data, f)

    def _save_names_internal(self):
        with open(self.names_path, 'w') as f:
            json.dump(self.id_to_name, f, indent=4)