# [FILE: core/search_engine.py]
import os
import json
import torch
import numpy as np
from core.database import Database
from core.ai_models import AIBackend
from core.face_db import FaceDB 

class SearchEngine:
    def __init__(self, project_path):
        self.project_path = project_path
        self.db = Database(project_path)
        # We access the singleton, but we DON'T load models yet.
        # This keeps the app fast on startup.
        self.ai = AIBackend()
        self.face_db = FaceDB(project_path) 
        
        self.cache = {} 
        # Initial scan
        self.build_index()

    def build_index(self, file_list=None):
        """
        Refreshes the search index. 
        """
        print("Building Search Index...")
        
        # 1. If provided a specific list (from Project Tree), use that.
        if file_list:
            for video_path in file_list:
                self._index_single_file(video_path)
        else:
            # Fallback: Walk project dir (only works for local assets)
            for root, dirs, files in os.walk(self.project_path):
                if "_cyne_db" in root: continue 
                
                for file in files:
                    if file.endswith(".json"):
                        meta_path = os.path.join(root, file)
                        # Reconstruct video path from json path
                        video_path = meta_path.replace(".json", "")
                        if os.path.exists(video_path):
                            self._index_single_file(video_path)

        print(f"Index built. Loaded {len(self.cache)} items.")

    def _index_single_file(self, video_path):
        meta_path = f"{video_path}.json"
        if not os.path.exists(meta_path): return
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.cache[video_path] = data
        except:
            pass

    def resolve_name_to_ids(self, query_name):
        """Finds person IDs that match the searched name."""
        query_name = query_name.lower()
        matched_ids = []
        for person_id, name in self.face_db.id_to_name.items():
            if query_name in name.lower():
                matched_ids.append(person_id)
        return matched_ids

    def search(self, query):
        query_terms = query.lower().strip().split()
        full_query = query.lower().strip()
        if not query_terms: return []

        results = []
        seen_paths = set()
        
        # 1. Resolve Face Names (e.g., "Find John")
        target_person_ids = self.resolve_name_to_ids(full_query)

        # 2. VECTOR SEARCH (Visuals)
        # Only attempt this if we have a valid text query and models can be loaded
        try:
            # Check if we need to load CLIP for this search
            if self.ai.clip_model is None:
                print("🔎 Search Engine: Lazy loading AI models for visual search...")
                self.ai.load_clip()

            if self.ai.clip_model and self.ai.clip_processor:
                # Tokenize and Encode Text
                inputs = self.ai.clip_processor(text=[query], return_tensors="pt", padding=True).to(self.ai.device)
                
                with torch.no_grad():
                    text_features = self.ai.clip_model.get_text_features(**inputs)
                    text_features /= text_features.norm(p=2, dim=-1, keepdim=True)
                    
                    query_vector = text_features.cpu().numpy()[0].tolist()

                # Query ChromaDB
                vec_res = self.db.visuals.query(
                    query_embeddings=[query_vector],
                    n_results=20,
                    include=["metadatas", "distances"]
                )
                
                if vec_res['ids'] and vec_res['ids'][0]:
                    for i, _id in enumerate(vec_res['ids'][0]):
                        metadata = vec_res['metadatas'][0][i]
                        distance = vec_res['distances'][0][i]
                        
                        # Convert Cosine Distance to % Score (approximate)
                        # ChromaDB Cosine distance is 0.0 (identical) to 2.0 (opposite)
                        # We want 100% (identical) to 0%
                        score = max(0, (1.0 - distance) * 100)
                        
                        if score < 15: continue # Filter noise
                        
                        path = metadata['source']
                        timestamp = metadata.get('timestamp', 0)
                        
                        results.append({
                            "path": path,
                            "match_type": "VISUAL (AI)",
                            "context": f"Visual match ~ {int(timestamp)}s",
                            "score": score,
                            "timestamp": timestamp
                        })
                        seen_paths.add(path)
        except Exception as e:
            print(f"⚠️ Vector Search skipped: {e}")

        # 3. TEXT & METADATA SEARCH (Deterministic)
        for video_path, data in self.cache.items():
            score = 0
            match_type = ""
            context = ""
            timestamp = 0
            
            filename = os.path.basename(video_path).lower()

            # A. Filename Match (Highest Priority)
            if all(t in filename for t in query_terms):
                score += 100
                match_type = "FILENAME"
                context = "Filename match"

            # B. FACE SEARCH (High Priority)
            elif target_person_ids and "faces" in data:
                video_faces = data["faces"]
                for target_id in target_person_ids:
                    if target_id in video_faces:
                        score = 200 # Boost above almost everything
                        match_type = "CAST"
                        human_name = self.face_db.get_name(target_id)
                        context = f"Featuring: {human_name}"
                        break

            # C. Transcript Match
            elif "transcript" in data:
                trans_data = data["transcript"]
                if isinstance(trans_data, list):
                    for seg in trans_data:
                        seg_lower = seg["text"].lower()
                        if full_query in seg_lower:
                             score = 80
                             match_type = "DIALOGUE"
                             timestamp = seg["start"]
                             context = f"Says: \"{seg['text']}\""
                             break 

            # D. Tag Match (Lower Priority)
            elif "tags" in data:
                tags = [t.lower() for t in data["tags"]]
                for tag in tags:
                    if full_query in tag:
                        score += 50
                        match_type = "TAG"
                        context = f"Tagged: {tag}"
                        break
            
            # Add to results if we found something new (or better score)
            if score > 0:
                # If we already saw this path via Vector search, only update if this score is higher?
                # Actually, duplicate entries for different timestamps are good.
                # But let's avoid exact duplicates.
                
                # Simple dedup based on path for non-timestamped matches
                is_duplicate = False
                for r in results:
                    if r['path'] == video_path and r['match_type'] == match_type and abs(r['timestamp'] - timestamp) < 1.0:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    results.append({
                        "path": video_path,
                        "match_type": match_type,
                        "context": context,
                        "score": score,
                        "timestamp": timestamp
                    })

        # Sort by Score Descending
        results.sort(key=lambda x: x['score'], reverse=True)
        return results