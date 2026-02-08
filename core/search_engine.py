# [FILE: core/search_engine.py]
import os
import json
import torch
import numpy as np
import time
from collections import defaultdict
from core.database import Database
from core.ai_models import AIBackend
from core.face_db import FaceDB
from core.logger import get_logger

logger = get_logger(__name__)

class SearchEngine:
    def __init__(self, project_path):
        self.project_path = project_path
        self.db = Database(project_path)
        # We access the singleton, but we DON'T load models yet.
        # This keeps the app fast on startup.
        self.ai = AIBackend()
        self.face_db = FaceDB(project_path) if project_path else None
        
        self.cache = {} 
        # Query embedding cache for performance
        self.query_embedding_cache = {}
        # Result cache with TTL (max 50 entries, 5 minute TTL)
        self.result_cache = {}
        self.result_cache_max_size = 50
        self.result_cache_ttl = 300  # 5 minutes in seconds
        self.result_cache_timestamps = {}  # Track when cache entries were created
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
        # Try database first (new system)
        try:
            data = self.db.get_video_metadata(video_path)
            if data:
                self.cache[video_path] = data
                return
        except:
            pass
        
        # Fallback to JSON sidecar (legacy)
        meta_path = f"{video_path}.json"
        if not os.path.exists(meta_path): return
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.cache[video_path] = data
        except:
            pass

    def _expand_query(self, query):
        """
        Generate semantic variations of the query for better search coverage.
        Returns list of query variations including the original.
        """
        variations = [query]  # Always include original
        
        # Simple expansion: add common variations
        query_lower = query.lower()
        
        # Action variations
        action_map = {
            "running": ["jogging", "sprinting", "moving fast"],
            "walking": ["strolling", "moving", "traveling"],
            "sitting": ["seated", "resting"],
            "talking": ["speaking", "conversing", "discussing"],
            "smiling": ["happy", "grinning", "cheerful"],
            "crying": ["sad", "weeping", "upset"]
        }
        
        for key, synonyms in action_map.items():
            if key in query_lower:
                for synonym in synonyms:
                    variation = query_lower.replace(key, synonym)
                    if variation not in variations:
                        variations.append(variation)
        
        # Object variations
        object_map = {
            "car": ["vehicle", "automobile", "auto"],
            "phone": ["smartphone", "mobile", "cell phone"],
            "person": ["people", "human", "individual"],
            "dog": ["puppy", "canine", "pet"]
        }
        
        for key, synonyms in object_map.items():
            if key in query_lower:
                for synonym in synonyms:
                    variation = query_lower.replace(key, synonym)
                    if variation not in variations:
                        variations.append(variation)
        
        # Limit to 5 variations to avoid too many queries
        return variations[:5]

    def _decompose_query(self, query):
        """
        Decompose complex queries into components.
        E.g., "person running in park" -> ["person", "running", "park"]
        """
        # Simple decomposition: split by common prepositions and conjunctions
        separators = [" in ", " on ", " at ", " with ", " and ", " or ", " near ", " by "]
        components = [query]
        
        for sep in separators:
            new_components = []
            for comp in components:
                if sep in comp.lower():
                    parts = comp.split(sep)
                    new_components.extend([p.strip() for p in parts if p.strip()])
                else:
                    new_components.append(comp)
            components = new_components
        
        # Remove very short components (likely noise)
        components = [c for c in components if len(c) > 2]
        
        return components if len(components) > 1 else [query]

    def _get_query_embedding(self, query):
        """Get or compute query embedding with caching."""
        if query in self.query_embedding_cache:
            return self.query_embedding_cache[query]
        
        if self.ai.clip_model is None:
            self.ai.load_clip()
        
        if self.ai.clip_model and self.ai.clip_processor:
            inputs = self.ai.clip_processor(text=[query], return_tensors="pt", padding=True).to(self.ai.device)
            with torch.no_grad():
                text_features = self.ai.clip_model.get_text_features(**inputs)
                text_features /= text_features.norm(p=2, dim=-1, keepdim=True)
                query_vector = text_features.cpu().numpy()[0].tolist()
            
            self.query_embedding_cache[query] = query_vector
            return query_vector
        return None

    def _calculate_adaptive_threshold(self, scores, query_type="general"):
        """Calculate adaptive threshold based on score distribution."""
        if not scores:
            return 15.0  # Default threshold
        
        scores_sorted = sorted(scores, reverse=True)
        
        # For specific queries (objects, actions), use stricter thresholds
        if query_type in ["object", "action", "person"]:
            # Use 75th percentile for specific queries
            if len(scores_sorted) > 10:
                threshold = scores_sorted[int(len(scores_sorted) * 0.25)]
            else:
                threshold = scores_sorted[-1] if scores_sorted else 15.0
            return max(20.0, threshold)  # Minimum 20% for specific queries
        
        # For general/abstract queries, use 50th percentile
        if len(scores_sorted) > 20:
            threshold = scores_sorted[int(len(scores_sorted) * 0.5)]
        else:
            threshold = scores_sorted[-1] if scores_sorted else 15.0
        
        return max(15.0, threshold)  # Minimum 15% for general queries

    def _fuse_multimodal_results(self, results_by_type, query_vector=None):
        """
        Intelligently fuse results from multiple modalities.
        
        Args:
            results_by_type: Dict with keys like 'visual', 'dialogue', 'metadata', etc.
            query_vector: Optional query embedding for similarity calculations
        
        Returns:
            Fused and deduplicated results list
        """
        # Weight for each match type (higher = more important)
        type_weights = {
            "VISUAL (AI)": 1.0,
            "DIALOGUE (SEMANTIC)": 0.9,
            "DIALOGUE": 0.85,
            "FILENAME": 1.2,  # Filename matches are very reliable
            "CAST": 1.3,  # Face matches are highly reliable
            "EMOTION": 0.8,
            "OBJECT (YOLO)": 0.9,
            "OBJECT": 0.85,
            "SHOT_TYPE": 0.75,
            "TAG": 0.7,
            "DESCRIPTION": 0.65
        }
        
        # Collect all results with their source types
        all_results = []
        for match_type, results in results_by_type.items():
            for result in results:
                result['source_type'] = match_type
                result['base_score'] = result.get('score', 0)
                # Apply type weight
                result['weighted_score'] = result['base_score'] * type_weights.get(match_type, 0.7)
                all_results.append(result)
        
        # Group by path+timestamp (within 2s window) for deduplication
        result_groups = defaultdict(list)
        for result in all_results:
            path = result['path']
            timestamp = result.get('timestamp', 0)
            # Create a key that groups results within 2 seconds
            time_key = int(timestamp / 2) * 2
            group_key = (path, time_key)
            result_groups[group_key].append(result)
        
        # Fuse results within each group
        fused_results = []
        for group_key, group_results in result_groups.items():
            if len(group_results) == 1:
                # Single result, just use it with weighted score
                fused = group_results[0].copy()
                fused['score'] = fused['weighted_score']
                fused['match_types'] = [fused['source_type']]
                fused_results.append(fused)
            else:
                # Multiple results for same location - fuse them
                # Boost score for multi-modal matches
                base_scores = [r['weighted_score'] for r in group_results]
                max_score = max(base_scores)
                
                # Multi-modal boost: +20% for each additional modality (capped at +60%)
                modality_count = len(set(r['source_type'] for r in group_results))
                multi_modal_boost = min(0.6, (modality_count - 1) * 0.2)
                
                fused_score = max_score * (1.0 + multi_modal_boost)
                
                # Combine contexts
                contexts = [r.get('context', '') for r in group_results]
                combined_context = " | ".join(set(contexts[:3]))  # Limit to 3 unique contexts
                
                # Use the best match type as primary
                best_result = max(group_results, key=lambda x: x['weighted_score'])
                
                fused = {
                    'path': best_result['path'],
                    'match_type': f"MULTI-MODAL ({modality_count} sources)",
                    'context': combined_context,
                    'score': fused_score,
                    'timestamp': best_result.get('timestamp', 0),
                    'match_types': list(set(r['source_type'] for r in group_results)),
                    'base_score': max_score,
                    'modality_count': modality_count
                }
                fused_results.append(fused)
        
        return fused_results

    def _collect_results_by_type(self, query, query_terms, full_query, query_vector):
        """Collect search results organized by match type."""
        results_by_type = defaultdict(list)
        
        # 1. FACE SEARCH (if applicable)
        if self.face_db:
            target_person_ids = self._resolve_name_to_ids(full_query)
            if target_person_ids:
                for video_path, data in self.cache.items():
                    if "faces" in data:
                        video_faces = data.get("faces", [])
                        for target_id in target_person_ids:
                            if target_id in video_faces:
                                human_name = self.face_db.get_name(target_id)
                                results_by_type["CAST"].append({
                                    "path": video_path,
                                    "match_type": "CAST",
                                    "context": f"Featuring: {human_name}",
                                    "score": 200,
                                    "timestamp": 0
                                })
                                break
        
        # 2. VECTOR SEARCH (Visuals & Dialogue)
        if query_vector:
            try:
                # Visual search - optimized: fetch more results initially for better ranking
                # Use approximate search for better performance on large collections
                # Limit to 200 for performance, can be paginated later
                vec_res = self.db.visuals.query(
                    query_embeddings=[query_vector],
                    n_results=min(200, self.db.visuals.count() if hasattr(self.db.visuals, 'count') else 200),
                    include=["metadatas", "distances"],
                    # ChromaDB automatically uses approximate search for large collections
                )
                
                visual_scores = []
                if vec_res['ids'] and vec_res['ids'][0]:
                    for i, _id in enumerate(vec_res['ids'][0]):
                        metadata = vec_res['metadatas'][0][i]
                        distance = vec_res['distances'][0][i]
                        score = max(0, (1.0 - distance) * 100)
                        visual_scores.append(score)
                        
                        path = metadata['source']
                        timestamp = metadata.get('timestamp', 0)
                        
                        results_by_type["VISUAL (AI)"].append({
                            "path": path,
                            "match_type": "VISUAL (AI)",
                            "context": f"Visual match ~ {int(timestamp)}s",
                            "score": score,
                            "timestamp": timestamp
                        })
                
                # Calculate adaptive threshold for visuals
                visual_threshold = self._calculate_adaptive_threshold(visual_scores, "visual")
                results_by_type["VISUAL (AI)"] = [
                    r for r in results_by_type["VISUAL (AI)"] 
                    if r['score'] >= visual_threshold
                ]
                
                # Dialogue search - optimized: fetch more results for better ranking
                try:
                    max_transcripts = min(200, self.db.transcripts.count() if hasattr(self.db.transcripts, 'count') else 200)
                    transcript_res = self.db.transcripts.query(
                        query_embeddings=[query_vector],
                        n_results=max_transcripts,
                        include=["metadatas", "distances"]
                    )
                    
                    dialogue_scores = []
                    if transcript_res['ids'] and transcript_res['ids'][0]:
                        for i, _id in enumerate(transcript_res['ids'][0]):
                            metadata = transcript_res['metadatas'][0][i]
                            distance = transcript_res['distances'][0][i]
                            score = max(0, (1.0 - distance) * 100)
                            dialogue_scores.append(score)
                            
                            path = metadata['source']
                            timestamp = metadata.get('start', 0)
                            text = metadata.get('text', '')
                            
                            results_by_type["DIALOGUE (SEMANTIC)"].append({
                                "path": path,
                                "match_type": "DIALOGUE (SEMANTIC)",
                                "context": f"Dialogue: \"{text[:60]}...\"",
                                "score": score,
                                "timestamp": timestamp
                            })
                    
                    # Calculate adaptive threshold for dialogue
                    dialogue_threshold = self._calculate_adaptive_threshold(dialogue_scores, "dialogue")
                    results_by_type["DIALOGUE (SEMANTIC)"] = [
                        r for r in results_by_type["DIALOGUE (SEMANTIC)"] 
                        if r['score'] >= dialogue_threshold
                    ]
                except Exception:
                    pass  # Transcript collection might not exist
            except Exception as e:
                print(f"WARNING: Vector Search skipped: {e}")
        
        # 3. METADATA SEARCH (Deterministic)
        for video_path, data in self.cache.items():
            filename = os.path.basename(video_path).lower()
            
            # Filename match
            if all(t in filename for t in query_terms):
                results_by_type["FILENAME"].append({
                    "path": video_path,
                    "match_type": "FILENAME",
                    "context": "Filename match",
                    "score": 100,
                    "timestamp": 0
                })
            
            # Emotion search
            if "emotions" in data and any(term in query.lower() for term in ["happy", "sad", "angry", "surprised", "excited", "worried", "confused", "neutral", "emotion", "feeling"]):
                emotions = data.get("emotions", [])
                query_lower = query.lower()
                for emotion in emotions:
                    if emotion.lower() in query_lower or query_lower in emotion.lower():
                        results_by_type["EMOTION"].append({
                            "path": video_path,
                            "match_type": "EMOTION",
                            "context": f"Emotion: {emotion}",
                            "score": 85,
                            "timestamp": 0
                        })
                        break
            
            # YOLO object search (high-confidence bounding-box detections)
            if "objects_yolo" in data:
                yolo_objects = data.get("objects_yolo", [])
                query_lower = query.lower()
                matched_yolo = set()
                for det in yolo_objects:
                    label = det.get("label", "").lower()
                    if any(term in label for term in query_terms) or query_lower in label or label in query_lower:
                        if label not in matched_yolo:
                            matched_yolo.add(label)
                            confidence = det.get("confidence", 0)
                            timestamp = det.get("timestamp", 0)
                            results_by_type["OBJECT (YOLO)"].append({
                                "path": video_path,
                                "match_type": "OBJECT (YOLO)",
                                "context": f"Detected: {label} ({confidence:.0%} conf) @ {int(timestamp)}s",
                                "score": 90 * confidence,
                                "timestamp": timestamp
                            })

            # Object search (CLIP zero-shot fallback for abstract concepts)
            if "objects" in data and any(term in query.lower() for term in ["holding", "near", "phone", "camera", "book", "cup", "bag", "car", "computer", "object"]):
                objects = data.get("objects", [])
                query_lower = query.lower()
                for obj in objects:
                    if query_lower in obj.lower() or any(term in obj.lower() for term in query_terms):
                        results_by_type["OBJECT"].append({
                            "path": video_path,
                            "match_type": "OBJECT",
                            "context": f"Object: {obj}",
                            "score": 85,
                            "timestamp": 0
                        })
                        break
            
            # Shot type search
            if "shot_type" in data and any(term in query.lower() for term in ["shot", "close", "wide", "medium", "long", "aerial", "angle"]):
                shot_type = data.get("shot_type", "")
                if shot_type and shot_type != "Unknown":
                    query_lower = query.lower()
                    shot_lower = shot_type.lower()
                    if any(term in shot_lower for term in query_terms) or query_lower in shot_lower:
                        results_by_type["SHOT_TYPE"].append({
                            "path": video_path,
                            "match_type": "SHOT_TYPE",
                            "context": f"Shot: {shot_type}",
                            "score": 80,
                            "timestamp": 0
                        })
            
            # Transcript match (exact text)
            if "transcript" in data:
                trans_data = data["transcript"]
                if isinstance(trans_data, list):
                    for seg in trans_data:
                        seg_lower = seg["text"].lower()
                        if full_query in seg_lower:
                            results_by_type["DIALOGUE"].append({
                                "path": video_path,
                                "match_type": "DIALOGUE",
                                "context": f"Says: \"{seg['text']}\"",
                                "score": 80,
                                "timestamp": seg["start"]
                            })
                            break
            
            # Summary/Description match
            if "summary" in data and data["summary"]:
                summary_lower = data["summary"].lower()
                if any(term in summary_lower for term in query_terms):
                    score = 75 if full_query in summary_lower else 60
                    results_by_type["DESCRIPTION"].append({
                        "path": video_path,
                        "match_type": "DESCRIPTION",
                        "context": f"Summary: {data['summary'][:80]}...",
                        "score": score,
                        "timestamp": 0
                    })
            
            # Tag match
            if "tags" in data:
                tags = [t.lower() for t in data["tags"]]
                for tag in tags:
                    if full_query in tag:
                        results_by_type["TAG"].append({
                            "path": video_path,
                            "match_type": "TAG",
                            "context": f"Tagged: {tag}",
                            "score": 50,
                            "timestamp": 0
                        })
                        break
        
        return results_by_type

    def _resolve_name_to_ids(self, query_name):
        """Finds person IDs that match the searched name."""
        if not self.face_db:
            return []
        query_name = query_name.lower()
        matched_ids = []
        for person_id, name in self.face_db.id_to_name.items():
            if query_name in name.lower():
                matched_ids.append(person_id)
        return matched_ids

    def _parse_query_operators(self, query):
        """
        Parse query with operators: AND, OR, NOT, field:value, "phrase", score:>80, etc.
        Returns parsed query structure.
        """
        import re

        parsed = {
            'original': query,
            'fields': {},
            'phrases': [],
            'terms': [],
            'operators': [],
            'score_range': None,
            'duration_range': None
        }

        query_remaining = query

        # Extract score range before generic fields (score:>80, score:50-90).
        score_pattern = r'\bscore:([><=]?)(\d+)(?:-(\d+))?\b'
        score_match = re.search(score_pattern, query_remaining, flags=re.IGNORECASE)
        if score_match:
            op, val1, val2 = score_match.groups()
            if val2:
                parsed['score_range'] = (float(val1), float(val2))
            elif op == '>':
                parsed['score_range'] = (float(val1), 100.0)
            elif op == '<':
                parsed['score_range'] = (0.0, float(val1))
            else:
                parsed['score_range'] = (float(val1), float(val1))
            query_remaining = re.sub(
                score_pattern, '', query_remaining, count=1, flags=re.IGNORECASE
            )

        # Extract duration range before generic fields (duration:30-60).
        duration_pattern = r'\bduration:(\d+)(?:-(\d+))?\b'
        duration_match = re.search(duration_pattern, query_remaining, flags=re.IGNORECASE)
        if duration_match:
            val1, val2 = duration_match.groups()
            if val2:
                parsed['duration_range'] = (float(val1), float(val2))
            else:
                parsed['duration_range'] = (0.0, float(val1))
            query_remaining = re.sub(
                duration_pattern, '', query_remaining, count=1, flags=re.IGNORECASE
            )

        # Extract field-specific searches (supports quoted values with spaces).
        field_pattern = r'(\w+):(?:"([^"]+)"|\'([^\']+)\'|([^\s]+))'
        for field, double_quoted, single_quoted, unquoted in re.findall(field_pattern, query_remaining):
            value = (double_quoted or single_quoted or unquoted).strip()
            parsed['fields'][field.lower()] = value
        query_remaining = re.sub(field_pattern, '', query_remaining)

        # Extract standalone phrases that are not consumed by field:value parsing.
        phrase_pattern = r'"([^"]+)"'
        parsed['phrases'] = re.findall(phrase_pattern, query_remaining)
        query_remaining = re.sub(phrase_pattern, '', query_remaining)

        # Extract boolean operators and terms
        query_clean = query_remaining.strip()
        # Simple tokenization - split by AND, OR, NOT (case insensitive)
        tokens = re.split(r'\s+(AND|OR|NOT)\s+', query_clean, flags=re.IGNORECASE)
        
        terms = []
        operators = []
        for i, token in enumerate(tokens):
            token = token.strip()
            if not token:
                continue
            if token.upper() in ['AND', 'OR', 'NOT']:
                operators.append(token.upper())
            else:
                terms.append(token)
        
        parsed['terms'] = terms
        parsed['operators'] = operators
        
        return parsed

    def _apply_query_filters(self, results, parsed_query):
        """Apply field-specific filters, score ranges, etc. from parsed query."""
        filtered = results
        
        # Score range filter
        if parsed_query.get('score_range'):
            min_score, max_score = parsed_query['score_range']
            filtered = [r for r in filtered if min_score <= r.get('score', 0) <= max_score]
        
        # Field-specific filters
        if 'visual' in parsed_query.get('fields', {}):
            # Only visual matches
            filtered = [r for r in filtered if 'VISUAL' in r.get('match_type', '')]
        
        if 'dialogue' in parsed_query.get('fields', {}):
            # Only dialogue matches
            filtered = [r for r in filtered if 'DIALOGUE' in r.get('match_type', '')]
        
        if 'tag' in parsed_query.get('fields', {}):
            # Only tag matches
            filtered = [r for r in filtered if r.get('match_type') == 'TAG']
        
        # Phrase matching (exact phrase in context)
        if parsed_query.get('phrases'):
            phrase_filtered = []
            for result in filtered:
                context_lower = result.get('context', '').lower()
                for phrase in parsed_query['phrases']:
                    if phrase.lower() in context_lower:
                        phrase_filtered.append(result)
                        break
            if phrase_filtered:
                filtered = phrase_filtered
        
        return filtered

    def search(self, query, use_expansion=True, use_decomposition=False, use_cache=True, 
               page=1, page_size=50):
        """
        Search with optional query expansion and decomposition.
        
        Args:
            query: Search query string
            use_expansion: If True, generate semantic variations of the query
            use_decomposition: If True, split complex queries into components
            use_cache: If True, use cached results for exact query matches
        """
        query_normalized = query.lower().strip()
        
        # Parse query operators
        parsed_query = self._parse_query_operators(query)
        
        # Extract base query (without operators for caching)
        base_query = parsed_query['original']
        if parsed_query['terms']:
            base_query = ' '.join(parsed_query['terms'])
        
        # Check cache first (use base query for cache key) with TTL
        cache_key = base_query.lower().strip()
        if use_cache and cache_key in self.result_cache and not parsed_query.get('fields') and not parsed_query.get('score_range'):
            # Check if cache entry is still valid (TTL)
            cache_time = self.result_cache_timestamps.get(cache_key, 0)
            if time.time() - cache_time < self.result_cache_ttl:
                # Apply filters to cached results
                cached_results = self.result_cache[cache_key]
                filtered_results = self._apply_query_filters(cached_results, parsed_query)
                # Apply pagination to cached results
                total = len(filtered_results)
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                paginated_results = filtered_results[start_idx:end_idx]
                return {
                    'results': paginated_results,
                    'total': total,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total + page_size - 1) // page_size,
                    'cached': True
                }
            else:
                # Cache expired, remove it
                logger.debug(f"Cache expired for query: {cache_key}")
                del self.result_cache[cache_key]
                del self.result_cache_timestamps[cache_key]
        
        query_terms = query_normalized.split()
        full_query = query_normalized
        if not query_terms and not parsed_query.get('phrases'): 
            return {
                'results': [],
                'total': 0,
                'page': page,
                'page_size': page_size,
                'total_pages': 0,
                'cached': False
            }

        all_results_by_type = defaultdict(list)
        
        # Generate query variations (only for base terms, not operators)
        query_variations = [base_query] if base_query else [query]
        if use_expansion and base_query:
            expanded = self._expand_query(base_query)
            query_variations.extend(expanded)
            query_variations = list(dict.fromkeys(query_variations))  # Remove duplicates
        
        if use_decomposition and base_query:
            decomposed = self._decompose_query(base_query)
            query_variations.extend(decomposed)
            query_variations = list(dict.fromkeys(query_variations))
        
        # Check for temporal queries (e.g., "person walking then sitting")
        temporal_keywords = [" then ", " followed by ", " after ", " before "]
        has_temporal = any(kw in query.lower() for kw in temporal_keywords)
        
        # Get base query vector for temporal queries
        query_vector = None
        if has_temporal:
            # Parse temporal query
            for kw in temporal_keywords:
                if kw in query.lower():
                    parts = query.lower().split(kw)
                    if len(parts) == 2:
                        action_a = parts[0].strip()
                        action_b = parts[1].strip()
                        
                        # Get embeddings for both actions
                        query_vector_a = self._get_query_embedding(action_a)
                        query_vector_b = self._get_query_embedding(action_b)
                        
                        if query_vector_a:
                            # Search for temporal sequences
                            temporal_results = self._search_temporal_sequence(query_vector_a, action_a, action_b)
                            for match_type, results_list in temporal_results.items():
                                all_results_by_type[match_type].extend(results_list)
                        break
        
        # Handle boolean operators
        if parsed_query.get('operators'):
            # For now, handle simple AND/OR/NOT logic
            # AND: results must match all terms
            # OR: results match any term
            # NOT: exclude results matching term
            operators = parsed_query['operators']
            terms = parsed_query['terms']
            
            if 'AND' in operators or len(terms) > 1 and 'OR' not in operators:
                # AND logic: search each term and intersect results
                term_results = []
                for term in terms:
                    q_terms = term.lower().strip().split()
                    q_full = term.lower().strip()
                    query_vector = self._get_query_embedding(term)
                    results_by_type = self._collect_results_by_type(term, q_terms, q_full, query_vector)
                    term_results.append(results_by_type)
                
                # Intersect: only keep results that appear in all term searches
                if term_results:
                    # Get all paths from first search
                    first_paths = set()
                    for match_type, results in term_results[0].items():
                        for r in results:
                            first_paths.add((r['path'], r.get('timestamp', 0)))
                    
                    # Keep only paths that appear in all searches
                    common_paths = first_paths.copy()
                    for other_results in term_results[1:]:
                        other_paths = set()
                        for match_type, results in other_results.items():
                            for r in results:
                                other_paths.add((r['path'], r.get('timestamp', 0)))
                        common_paths &= other_paths
                    
                    # Rebuild results with only common paths
                    for match_type, results in term_results[0].items():
                        for r in results:
                            if (r['path'], r.get('timestamp', 0)) in common_paths:
                                all_results_by_type[match_type].append(r)
            elif 'OR' in operators:
                # OR logic: union all results
                for term in terms:
                    q_terms = term.lower().strip().split()
                    q_full = term.lower().strip()
                    query_vector = self._get_query_embedding(term)
                    results_by_type = self._collect_results_by_type(term, q_terms, q_full, query_vector)
                    for match_type, results in results_by_type.items():
                        all_results_by_type[match_type].extend(results)
            else:
                # Default: search with all terms
                search_query = ' '.join(terms)
                q_terms = search_query.lower().strip().split()
                q_full = search_query.lower().strip()
                query_vector = self._get_query_embedding(search_query)
                results_by_type = self._collect_results_by_type(search_query, q_terms, q_full, query_vector)
                for match_type, results in results_by_type.items():
                    all_results_by_type[match_type].extend(results)
        else:
            # No operators: normal search
            for q_var in query_variations[:3]:  # Limit to 3 variations
                q_terms = q_var.lower().strip().split()
                q_full = q_var.lower().strip()
                
                # Get query embedding for this variation
                query_vector = self._get_query_embedding(q_var)
                
                # Collect results for this variation
                results_by_type = self._collect_results_by_type(q_var, q_terms, q_full, query_vector)
                
                # Merge into combined results (with slight score reduction for variations)
                variation_weight = 1.0 if q_var == base_query else 0.8
                for match_type, results in results_by_type.items():
                    for result in results:
                        result['score'] *= variation_weight
                        all_results_by_type[match_type].append(result)
        
        # Handle NOT operator (exclude results)
        if 'NOT' in parsed_query.get('operators', []):
            not_terms = []
            for i, op in enumerate(parsed_query['operators']):
                if op == 'NOT' and i < len(parsed_query['terms']):
                    not_terms.append(parsed_query['terms'][i])
            
            # Remove results matching NOT terms
            for not_term in not_terms:
                not_lower = not_term.lower()
                for match_type in list(all_results_by_type.keys()):
                    all_results_by_type[match_type] = [
                        r for r in all_results_by_type[match_type]
                        if not_lower not in r.get('context', '').lower()
                    ]
        
        # Fuse multi-modal results
        fused_results = self._fuse_multimodal_results(all_results_by_type, None)
        
        # Apply query filters (field-specific, score range, etc.)
        filtered_results = self._apply_query_filters(fused_results, parsed_query)
        
        # Enhanced ranking with multi-factor scoring
        ranked_results = self._rank_results(filtered_results)
        
        # Cache results (limit cache size) - cache base query only
        if use_cache and base_query and not parsed_query.get('fields') and not parsed_query.get('score_range'):
            # Clean expired cache entries first
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in self.result_cache_timestamps.items()
                if current_time - timestamp >= self.result_cache_ttl
            ]
            for key in expired_keys:
                del self.result_cache[key]
                del self.result_cache_timestamps[key]
            
            # Add new cache entry if there's room
            if len(self.result_cache) >= self.result_cache_max_size:
                # Remove oldest entry (simple FIFO)
                oldest_key = next(iter(self.result_cache))
                del self.result_cache[oldest_key]
                del self.result_cache_timestamps[oldest_key]
            
            self.result_cache[cache_key] = ranked_results
            self.result_cache_timestamps[cache_key] = time.time()
        
        # Apply pagination
        total = len(ranked_results)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_results = ranked_results[start_idx:end_idx]
        
        return {
            'results': paginated_results,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'cached': False
        }

    def _search_temporal_sequence(self, query_vector, action_a, action_b, max_gap_seconds=30):
        """
        Search for temporal sequences where action A precedes action B within max_gap_seconds.
        """
        if not query_vector or not self.db.temporal_sequences:
            return {}
        
        try:
            # Search for sequences matching action A
            seq_res_a = self.db.temporal_sequences.query(
                query_embeddings=[query_vector],
                n_results=50,
                include=["metadatas", "distances"]
            )
            
            # Find sequences where A is followed by B within time window
            sequence_results = []
            if seq_res_a['ids'] and seq_res_a['ids'][0]:
                for i, seq_id in enumerate(seq_res_a['ids'][0]):
                    metadata_a = seq_res_a['metadatas'][0][i]
                    path = metadata_a['source']
                    end_time_a = metadata_a.get('end_time', 0)
                    
                    # Look for sequence B starting within max_gap_seconds after A ends
                    # Query temporal sequences for the same video
                    try:
                        # Get all sequences for this video
                        all_seqs = self.db.temporal_sequences.get(
                            where={"source": path},
                            include=["metadatas"]
                        )
                        
                        if all_seqs and all_seqs['metadatas']:
                            for seq_meta in all_seqs['metadatas']:
                                start_time_b = seq_meta.get('start_time', 0)
                                gap = start_time_b - end_time_a
                                
                                if 0 < gap <= max_gap_seconds:
                                    # Found sequence: A -> B
                                    sequence_results.append({
                                        "path": path,
                                        "match_type": "TEMPORAL SEQUENCE",
                                        "context": f"Sequence: {action_a} then {action_b} (gap: {int(gap)}s)",
                                        "score": 90,  # High score for temporal matches
                                        "timestamp": end_time_a,
                                        "sequence_start": metadata_a.get('start_time', 0),
                                        "sequence_end": seq_meta.get('end_time', 0)
                                    })
                                    break
                    except:
                        pass
        except:
            pass

        results_by_type = defaultdict(list)
        for r in sequence_results:
            results_by_type[r.get("match_type", "TEMPORAL SEQUENCE")].append(r)
        return dict(results_by_type)

    def _search_temporal_proximity(self, query_vector, concept_a, concept_b, max_proximity_seconds=10):
        """
        Find clips where two concepts appear within max_proximity_seconds of each other.
        """
        # This would require searching visual embeddings and checking temporal proximity
        # For now, return empty - can be enhanced later
        return []

    def search_similar_to_image(self, image_path_or_pil, n_results=20):
        """
        Find frames similar to a reference image.
        
        Args:
            image_path_or_pil: Path to image file or PIL Image object
            n_results: Number of similar results to return
        
        Returns:
            List of similar results
        """
        from PIL import Image
        
        # Load image
        if isinstance(image_path_or_pil, str):
            ref_image = Image.open(image_path_or_pil)
        else:
            ref_image = image_path_or_pil
        
        if self.ai.clip_model is None:
            self.ai.load_clip()
        
        if not self.ai.clip_model or not self.ai.clip_processor:
            return []
        
        # Get image embedding
        inputs = self.ai.clip_processor(images=ref_image, return_tensors="pt", padding=True).to(self.ai.device)
        with torch.no_grad():
            image_features = self.ai.clip_model.get_image_features(**inputs)
            image_features /= image_features.norm(p=2, dim=-1, keepdim=True)
            ref_embedding = image_features.cpu().numpy()[0].tolist()
        
        # Search visual embeddings
        try:
            vec_res = self.db.visuals.query(
                query_embeddings=[ref_embedding],
                n_results=n_results,
                include=["metadatas", "distances"]
            )
            
            results = []
            if vec_res['ids'] and vec_res['ids'][0]:
                for i, _id in enumerate(vec_res['ids'][0]):
                    metadata = vec_res['metadatas'][0][i]
                    distance = vec_res['distances'][0][i]
                    score = max(0, (1.0 - distance) * 100)
                    
                    if score >= 20:  # Minimum similarity threshold
                        results.append({
                            "path": metadata['source'],
                            "match_type": "SIMILAR IMAGE",
                            "context": f"Similar visual ~ {int(metadata.get('timestamp', 0))}s",
                            "score": score,
                            "timestamp": metadata.get('timestamp', 0)
                        })
        except Exception as e:
            print(f"Similarity search error: {e}")
        
        return results

    def search_similar_to_clip(self, video_path, timestamp, n_results=20):
        """
        Find clips similar to a reference clip at a specific timestamp.
        
        Args:
            video_path: Path to reference video
            timestamp: Timestamp in seconds
            n_results: Number of similar results to return
        """
        import cv2
        from PIL import Image
        
        # Extract frame at timestamp
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 24.0
        
        frame_num = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return []
        
        # Convert to PIL Image
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        
        # Use image similarity search
        results = self.search_similar_to_image(pil_img, n_results)
        
        # Filter out the reference clip itself
        results = [r for r in results if not (r['path'] == video_path and abs(r['timestamp'] - timestamp) < 2.0)]
        
        return results

    def search_similar_to_sequence(self, video_path, start_time, end_time, n_results=20):
        """
        Find sequences similar to a reference sequence (multi-frame comparison).
        
        Args:
            video_path: Path to reference video
            start_time: Start timestamp
            end_time: End timestamp
            n_results: Number of similar results to return
        """
        import cv2
        from PIL import Image
        import numpy as np
        
        # Extract multiple frames from sequence
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return []
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 24.0
        
        # Sample 3-5 frames from the sequence
        num_samples = min(5, int((end_time - start_time) * fps / 10))
        if num_samples < 1:
            num_samples = 1
        
        frame_times = np.linspace(start_time, end_time, num_samples)
        sequence_embeddings = []
        
        if self.ai.clip_model is None:
            self.ai.load_clip()
        
        if not self.ai.clip_model or not self.ai.clip_processor:
            return []
        
        for t in frame_times:
            frame_num = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if ret:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                
                inputs = self.ai.clip_processor(images=pil_img, return_tensors="pt", padding=True).to(self.ai.device)
                with torch.no_grad():
                    img_features = self.ai.clip_model.get_image_features(**inputs)
                    img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                    sequence_embeddings.append(img_features.cpu().numpy()[0])
        
        cap.release()
        
        if not sequence_embeddings:
            return []
        
        # Average embeddings to get sequence representation
        avg_embedding = np.mean(sequence_embeddings, axis=0)
        avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
        seq_embedding = avg_embedding.tolist()
        
        # Search temporal sequences
        try:
            seq_res = self.db.temporal_sequences.query(
                query_embeddings=[seq_embedding],
                n_results=n_results,
                include=["metadatas", "distances"]
            )
            
            results = []
            if seq_res['ids'] and seq_res['ids'][0]:
                for i, _id in enumerate(seq_res['ids'][0]):
                    metadata = seq_res['metadatas'][0][i]
                    distance = seq_res['distances'][0][i]
                    score = max(0, (1.0 - distance) * 100)
                    
                    if score >= 25:  # Higher threshold for sequences
                        # Filter out the reference sequence
                        if metadata['source'] == video_path:
                            seq_start = metadata.get('start_time', 0)
                            seq_end = metadata.get('end_time', 0)
                            if abs(seq_start - start_time) < 5.0:
                                continue
                        
                        results.append({
                            "path": metadata['source'],
                            "match_type": "SIMILAR SEQUENCE",
                            "context": f"Similar sequence {int(metadata.get('start_time', 0))}s-{int(metadata.get('end_time', 0))}s",
                            "score": score,
                            "timestamp": metadata.get('start_time', 0),
                            "sequence_start": metadata.get('start_time', 0),
                            "sequence_end": metadata.get('end_time', 0)
                        })
        except Exception as e:
            print(f"Sequence similarity search error: {e}")
        
        return results

    def _rank_results(self, results):
        """
        Enhanced multi-factor ranking considering:
        - Similarity score (primary)
        - Match type confidence
        - Multi-modal boost
        - Result diversity (avoid too many from same video)
        - File recency (if available)
        """
        if not results:
            return []
        
        # Group by video for diversity calculation
        videos_seen = defaultdict(int)
        for result in results:
            videos_seen[result['path']] += 1
        
        # Calculate diversity penalty (reduce score if too many results from same video)
        max_results_per_video = 5
        for result in results:
            video_count = videos_seen[result['path']]
            if video_count > max_results_per_video:
                # Penalize results beyond the first 5 from same video
                diversity_penalty = (video_count - max_results_per_video) * 0.05
                result['score'] = max(0, result['score'] * (1.0 - diversity_penalty))
        
        # Sort by final score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Limit to top 100 results
        return results[:100]
