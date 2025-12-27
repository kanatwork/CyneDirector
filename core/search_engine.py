import os
import json
import torch
from core.database import Database
from core.ai_models import AIBackend
from core.face_db import FaceDB 

class SearchEngine:
    def __init__(self, project_path):
        self.project_path = project_path
        self.db = Database(project_path)
        self.ai = AIBackend()
        self.face_db = FaceDB(project_path) 
        
        self.cache = {} 
        # Initial build tries to scan project folder, but main_window will 
        # call this again with the full file list to catch external files.
        self.build_index()

    def build_index(self, file_list=None):
        """
        Refreshes the search index. 
        If file_list is provided, it scans those specific files for metadata.
        If None, it tries to scan the project folder (fallback).
        """
        print("Building Search Index...")
        
        # 1. If we have a specific list of files (from Project Tree), use that.
        # This fixes the bug where external files weren't being indexed.
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
        
        target_person_ids = self.resolve_name_to_ids(full_query)

        # --- 1. VECTOR SEARCH (Safely Check Model) ---
        if self.ai.clip_model and self.ai.clip_processor:
            try:
                inputs = self.ai.clip_processor(text=[query], return_tensors="pt", padding=True).to(self.ai.device)
                with torch.no_grad():
                    text_features = self.ai.clip_model.get_text_features(**inputs)
                    text_features /= text_features.norm(p=2, dim=-1, keepdim=True)
                
                    query_vector = text_features.cpu().numpy()[0].tolist()

                vec_res = self.db.visuals.query(
                    query_embeddings=[query_vector],
                    n_results=20,
                    include=["metadatas", "distances"]
                )
                
                if vec_res['ids'] and vec_res['ids'][0]:
                    for i, _id in enumerate(vec_res['ids'][0]):
                        metadata = vec_res['metadatas'][0][i]
                        distance = vec_res['distances'][0][i]
                        score = max(0, (1 - distance) * 100)
                        
                        if score < 15: continue
                        
                        path = metadata['source']
                        timestamp = metadata.get('timestamp', 0)
                        
                        results.append({
                            "path": path,
                            "match_type": "VISUAL (AI)",
                            "context": f"Visual match at {int(timestamp)}s",
                            "score": score,
                            "timestamp": timestamp
                        })
                        seen_paths.add(path)
            except Exception as e:
                print(f"Vector search skip: {e}")
        else:
            print("⚠️ Visual Search skipped (Models not loaded). Run 'Index Visuals' first to load them, or just search text.")

        # --- 2. TEXT & METADATA SEARCH (Improved Matching) ---
        for video_path, data in self.cache.items():
            score = 0
            match_type = ""
            context = ""
            timestamp = 0
            
            filename = os.path.basename(video_path).lower()

            # A. Filename Match
            if all(t in filename for t in query_terms):
                score += 100
                match_type = "FILENAME"
                context = "Filename match"

            # B. FACE SEARCH
            elif target_person_ids and "faces" in data:
                video_faces = data["faces"]
                for target_id in target_person_ids:
                    if target_id in video_faces:
                        score = 200 
                        match_type = "CAST"
                        human_name = self.face_db.get_name(target_id)
                        context = f"Featuring: {human_name}"
                        break

            # C. Transcript (Tokenized) - Updated to support 'segments' or 'transcript' keys
            elif "segments" in data or "transcript" in data:
                # Prefer 'segments', fallback to 'transcript'
                trans_data = data.get("segments") or data.get("transcript")
                
                if isinstance(trans_data, list):
                    for seg in trans_data:
                        seg_lower = seg["text"].lower()
                        # Allow partial match: at least one unique keyword must exist
                        if full_query in seg_lower:
                             score = 80
                             match_type = "DIALOGUE"
                             timestamp = seg["start"]
                             context = f"Says: \"{seg['text']}\""
                             break 
                elif isinstance(trans_data, str) and full_query in trans_data.lower():
                    score = 60
                    match_type = "DIALOGUE"
                    context = "Keyword found in audio"

            # D. Visual Tags (Tokenized)
            elif "tags" in data:
                tags = [t.lower() for t in data["tags"]]
                for tag in tags:
                    if full_query in tag:
                        score += 50
                        match_type = "TAG"
                        context = f"Tagged: {tag}"
                        break
            
            if score > 0 and video_path not in seen_paths:
                results.append({
                    "path": video_path,
                    "match_type": match_type,
                    "context": context,
                    "score": score,
                    "timestamp": timestamp
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results