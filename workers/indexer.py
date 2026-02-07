# [FILE: workers/indexer.py]
import os
import json
import time
from PyQt6.QtCore import QThread, pyqtSignal
import cv2
import torch
import numpy as np
from PIL import Image
from core.ai_models import AIBackend
from core.database import Database
from core.tags import get_tag_bank
from core.logger import get_logger
from core.performance import get_optimal_batch_size, log_memory_usage
from collections import defaultdict

logger = get_logger(__name__)

class IndexerWorker(QThread):
    log_signal = pyqtSignal(str)       
    progress_signal = pyqtSignal(int)      
    finished_signal = pyqtSignal()
    summary_signal = pyqtSignal(str, str)  
    
    def __init__(self, file_paths, project_path, mode="speed"):
        super().__init__()
        self.file_paths = file_paths
        self.project_path = project_path
        self.is_running = True
        self.mode = mode  # "speed" or "accuracy"
        
        # --- Mode-based Settings ---
        # Optimize batch size based on available memory and device
        device = AIBackend().device
        base_batch_accuracy = 32
        base_batch_speed = 64

        if mode == "accuracy":
            self.batch_size = get_optimal_batch_size(base_batch_accuracy, min_batch=16, max_batch=64, device=device)
            self.min_interval = 0.5  # More frequent sampling (1 frame per 0.5-5 seconds)
            self.max_interval = 5.0
            self.scene_threshold = 0.60
            self.blur_threshold = 50.0
            self.tag_threshold_percent = 0.40  # 40% of max score for accuracy mode
            self.min_frames_for_tag = 3  # Very strict: tag must appear in at least 3 frames
        else:  # speed mode
            self.batch_size = get_optimal_batch_size(base_batch_speed, min_batch=32, max_batch=128, device=device)
            self.min_interval = 1.0  # Current sampling (1 frame per 1.5-15 seconds)
            self.max_interval = 15.0
            self.scene_threshold = 0.60
            self.blur_threshold = 50.0
            self.tag_threshold_percent = 0.20  # 20% of max score for speed mode
            self.min_frames_for_tag = 1  # Tag appears in at least 1 frame
        
        logger.info(f"Indexer initialized with batch_size={self.batch_size} (mode={mode})")
        log_memory_usage("IndexerWorker init")
        
        # Batch write optimization (applies to both modes)
        self.db_write_batch = []  # Batch database writes
        self.db_write_batch_size = 100  # Write every 100 embeddings  

    def calculate_histogram(self, image):
        """Creates a color fingerprint for the frame to detect cuts/motion."""
        # OPTIMIZATION: Use smaller histogram for faster computation
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 40], [0, 180, 0, 256])  # Reduced from [50, 60]
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    def calculate_sharpness(self, image):
        """Returns a score representing how focused the image is."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def _resize_for_ai(self, pil_img, target_size=384):
        """
        Resizes image for AI consumption to save RAM.
        CLIP uses 224/336, BLIP uses ~384. 
        Keeping full 4K images in RAM lists causes crashes.
        """
        w, h = pil_img.size
        scale = target_size / max(w, h)
        if scale >= 1: return pil_img
        new_w, new_h = int(w * scale), int(h * scale)
        return pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def run(self):
        logger.debug(f"IndexerWorker.run() started (mode={self.mode})")
        self.progress_signal.emit(1)
        self.log_signal.emit("Initializing Smart-Action AI (Blur-Gate Enabled)...")
        
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            # Load Models
            self.log_signal.emit("Loading CLIP model for visual analysis...")
            clip_model, clip_processor = ai.load_clip()
            self.log_signal.emit("CLIP model loaded successfully")
            
            from config import USE_BLIP2
            blip_label = "BLIP-2" if USE_BLIP2 else "BLIP-large"
            self.log_signal.emit(f"Loading {blip_label} model for caption generation...")
            blip_model, blip_processor = ai.load_blip()
            self.log_signal.emit(f"{blip_label} model loaded successfully")
        except Exception as e:
            self.log_signal.emit(f"CRITICAL: AI Load Error - {e}")
            self.finished_signal.emit()
            return
            
        tag_list = get_tag_bank()
        total_files = len(self.file_paths)
        
        total_files = len(self.file_paths)
        log_memory_usage("Before indexing loop")
        
        for idx, video_path in enumerate(self.file_paths):
            if not self.is_running: break
            
            filename = os.path.basename(video_path)
            self.log_signal.emit(f"Processing {idx + 1}/{total_files}: {filename}")
            self.log_signal.emit(f"  → Starting deep visual analysis...")
            
            # Log memory usage periodically
            if idx % 5 == 0:
                log_memory_usage(f"Processing file {idx + 1}/{total_files}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.log_signal.emit(f"  ✗ Failed to open video file")
                continue
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0: fps = 24.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # --- SCENE CONTAINER ---
            detected_scenes = []
            current_scene = {'best_frame': None, 'score': -1.0}
            
            # Batching for CLIP
            frames_batch = []
            timestamps_batch = []
            tag_scores = defaultdict(float)
            
            # For accuracy mode: track which tags appear in which frames
            if self.mode == "accuracy":
                tag_frame_occurrences = defaultdict(set)  # tag_name -> set of frame indices
            else:
                tag_frame_occurrences = None
            
            prev_hist = None
            last_indexed_time = -self.max_interval
            
            # Track frame count for accuracy mode
            total_indexed_frames = 0
            
            # Adaptive sampling: Track motion history for adaptive step size
            motion_history = []
            recent_motion_scores = []
            adaptive_scan_step = int(fps / 3) if fps > 10 else 1
            
            # Keyframe candidates (high quality, high motion frames)
            keyframe_candidates = []
            
            # Scan Step - More frequent in accuracy mode
            if self.mode == "accuracy":
                base_scan_step = max(1, int(fps / 6)) if fps > 10 else 1  # More frequent sampling
            else:
                # Speed mode: Use larger steps for faster processing
                base_scan_step = max(1, int(fps / 2)) if fps > 10 else 1  # Changed from fps/3
            
            for frame_num in range(0, total_frames, base_scan_step):
                if not self.is_running: break
                
                # Update UI occasionally
                if frame_num % 100 == 0:
                    current_percent = int(((idx) / total_files * 100) + (frame_num / total_frames * (100 / total_files)))
                    self.progress_signal.emit(current_percent)

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret: break
                
                current_time = frame_num / fps
                curr_hist = self.calculate_histogram(frame)
                sharpness = self.calculate_sharpness(frame)

                # --- 1. DETECT SCENE CUTS ---
                similarity = 1.0
                motion_score = 0.0
                if prev_hist is not None:
                    similarity = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
                    motion_score = (1.0 - similarity)
                    recent_motion_scores.append(motion_score)
                    if len(recent_motion_scores) > 10:
                        recent_motion_scores.pop(0)
                
                # Adaptive sampling: Adjust scan step based on motion
                if len(recent_motion_scores) >= 5:
                    avg_motion = sum(recent_motion_scores) / len(recent_motion_scores)
                    # High motion: sample more frequently (smaller step)
                    # Low motion: sample less frequently (larger step)
                    if avg_motion > 0.3:  # High motion
                        adaptive_scan_step = max(1, int(base_scan_step * 0.5))
                    elif avg_motion < 0.1:  # Low motion
                        adaptive_scan_step = min(int(base_scan_step * 2), int(fps * 2))
                    else:
                        adaptive_scan_step = base_scan_step
                
                # New Scene Detected?
                if similarity < self.scene_threshold:
                    if current_scene['best_frame'] is not None:
                        detected_scenes.append(current_scene)
                    current_scene = {'best_frame': None, 'score': -1.0}

                # --- 2. FIND BEST ACTION FRAME & KEYFRAME DETECTION ---
                if prev_hist is not None:
                    if sharpness > self.blur_threshold:
                        quality_score = motion_score * sharpness
                        if quality_score > current_scene['score']:
                            current_scene['score'] = quality_score
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            pil_img = Image.fromarray(rgb)
                            
                            # OPTIMIZATION: Resize immediately to save RAM
                            # We only need ~384px for BLIP captioning
                            current_scene['best_frame'] = self._resize_for_ai(pil_img, 480)
                        
                        # Keyframe detection: High quality + significant motion or scene cut
                        is_keyframe = False
                        if motion_score > 0.4 and sharpness > self.blur_threshold * 1.5:
                            is_keyframe = True  # High motion + high quality
                        elif similarity < self.scene_threshold and sharpness > self.blur_threshold:
                            is_keyframe = True  # Scene cut + good quality
                        
                        if is_keyframe:
                            keyframe_candidates.append({
                                'frame_num': frame_num,
                                'time': current_time,
                                'motion': motion_score,
                                'sharpness': sharpness,
                                'score': quality_score
                            })

                # --- 3. ADAPTIVE INDEXING FOR TAGS (CLIP) ---
                time_since_last = current_time - last_indexed_time
                should_index = False
                
                # Priority indexing for keyframes
                is_keyframe_frame = any(kf['frame_num'] == frame_num for kf in keyframe_candidates[-5:])
                
                if is_keyframe_frame:
                    # Always index keyframes
                    should_index = True
                elif time_since_last >= self.max_interval:
                    # Force index if too much time has passed
                    should_index = True
                elif time_since_last >= self.min_interval:
                    # Adaptive indexing: index if significant change or high quality
                    if similarity < 0.85 and sharpness > self.blur_threshold:
                        should_index = True
                    # Also index high-quality frames even if similar (for better coverage)
                    elif sharpness > self.blur_threshold * 1.3:
                        should_index = True

                if should_index:
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(img_rgb)
                    
                    # OPTIMIZATION: Resize immediately for CLIP (input is usually 224 or 336)
                    # Storing 64 4K images in a list will crash Python.
                    resized_img = self._resize_for_ai(pil_img, 336)
                    
                    frames_batch.append(resized_img)
                    timestamps_batch.append(current_time)
                    last_indexed_time = current_time
                    total_indexed_frames += 1

                    if len(frames_batch) >= self.batch_size:
                        start_frame_idx = total_indexed_frames - len(frames_batch) if self.mode == "accuracy" else None
                        self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores, tag_frame_occurrences, start_frame_idx)
                        frames_batch = []
                        timestamps_batch = []
                        
                prev_hist = curr_hist

            # --- END OF FILE PROCESSING ---
            if current_scene['best_frame'] is not None:
                detected_scenes.append(current_scene)

            # Process leftover batch
            if frames_batch:
                start_frame_idx = total_indexed_frames - len(frames_batch) if self.mode == "accuracy" else None
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores, tag_frame_occurrences, start_frame_idx)
            
            # Flush any remaining batched database writes
            if hasattr(self, 'db_write_batch') and self.db_write_batch:
                self._flush_db_batch(db, video_path)
            
            cap.release()
            
            # --- SAVE SCENE SEGMENTS FOR TEMPORAL SEARCH ---
            if detected_scenes:
                scene_segments = []
                scene_start = 0
                for i, scene in enumerate(detected_scenes):
                    # Estimate scene end (next scene start or video end)
                    scene_end = (i + 1) * (total_frames / fps / len(detected_scenes)) if i < len(detected_scenes) - 1 else total_frames / fps
                    scene_segments.append({
                        "start": scene_start,
                        "end": scene_end,
                        "duration": scene_end - scene_start,
                        "score": scene.get('score', 0),
                        "has_best_frame": scene.get('best_frame') is not None
                    })
                    scene_start = scene_end
                
                # Save scene segments to database
                db.save_scene_segments(video_path, scene_segments)
                
                # Generate temporal sequence embeddings for key scenes
                if len(detected_scenes) > 0 and clip_model:
                    try:
                        # Sample frames from each scene to create sequence embeddings
                        for i, scene in enumerate(detected_scenes[:5]):  # Limit to first 5 scenes
                            if scene.get('best_frame'):
                                # Use scene frame as sequence representation
                                inputs = clip_processor(images=scene['best_frame'], return_tensors="pt", padding=True).to(ai.device)
                                with torch.no_grad():
                                    seq_embedding = clip_model.get_image_features(**inputs)
                                    seq_embedding /= seq_embedding.norm(p=2, dim=-1, keepdim=True)
                                    seq_embedding = seq_embedding.cpu().numpy()[0].tolist()
                                
                                # Get scene time bounds
                                scene_start = scene_segments[i]['start'] if i < len(scene_segments) else 0
                                scene_end = scene_segments[i]['end'] if i < len(scene_segments) else total_frames / fps
                                
                                db.add_temporal_sequence(video_path, seq_embedding, scene_start, scene_end)
                    except Exception as e:
                        print(f"Temporal sequence error: {e}")

            # --- PHASE 2: GENERATE DESCRIPTIONS (BLIP) - Improved Quality ---
            self.log_signal.emit(f"  → Detected {len(detected_scenes)} scene(s), generating descriptions...")
            descriptions = []
            # Analyze more scenes (up to 5) for better coverage
            final_scenes = detected_scenes[:5] if len(detected_scenes) >= 5 else detected_scenes
            
            # Also sample frames at key timestamps: beginning, 25%, 50%, 75%, end
            key_timestamps = []
            if total_frames > 0:
                key_timestamps = [
                    int(total_frames * 0.0),   # Beginning
                    int(total_frames * 0.25),  # Quarter
                    int(total_frames * 0.5),   # Middle
                    int(total_frames * 0.75),  # Three quarters
                    int(total_frames * 0.95)   # Near end
                ]
            
            # Fallback: If no good frames found, use key timestamps
            if not final_scenes and total_frames > 0:
                try:
                    cap_retry = cv2.VideoCapture(video_path)
                    for frame_num in key_timestamps[:3]:  # Use first 3 key frames
                        cap_retry.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                        ret, frame = cap_retry.read()
                        if ret:
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            pil_img = Image.fromarray(rgb)
                            final_scenes.append({'best_frame': self._resize_for_ai(pil_img, 480), 'score': 0.0})
                    cap_retry.release()
                except Exception as e:
                    print(f"Fallback frame capture error: {e}")
                    pass
            
            # Improved prompts - more specific to prevent hallucinations and out-of-context phrases
            prompts = [
                "a photo of",
                "a picture showing",
                "an image of"
            ]
            
            # Common hallucination patterns to filter out
            hallucination_patterns = [
                "with words that describe",
                "in your mobile app",
                "with an iphone",
                "with an ipad",
                "or android app",
                "mobile app",
                "iphone, ipad",
                "android app",
                "in the app",
                "on the app",
                "using the app",
                "download the app",
                "install the app",
                "get the app",
                "use the app",
                "in this app",
                "with this app",
                "for the app",
                "to the app",
                "from the app"
            ]
            
            for i, scene in enumerate(final_scenes):
                try:
                    # Use rotating prompts for variety
                    prompt = prompts[i % len(prompts)]
                    
                    # Pass the resized image to BLIP with prompt
                    inputs = blip_processor(images=scene['best_frame'], text=prompt, return_tensors="pt").to(ai.device)
                    
                    # BLIP pixel values must match model dtype.
                    # Only use half() on CUDA — MPS/CPU use float32.
                    if ai.device == "cuda" and ai.dtype == torch.float16:
                        inputs["pixel_values"] = inputs["pixel_values"].half()

                    with torch.no_grad():
                        # Generate with better parameters to avoid repetition and hallucinations
                        out_ids = blip_model.generate(
                            **inputs, 
                            max_new_tokens=50,  # Reduced to prevent longer hallucinations
                            num_beams=2,  # Fewer beams for more focused output
                            temperature=0.7,  # Lower temperature for more accurate, less creative output
                            do_sample=True,
                            repetition_penalty=2.0,  # Higher penalty to prevent repetition
                            length_penalty=1.0,  # Neutral length penalty
                            no_repeat_ngram_size=2  # Prevent 2-gram repetition
                        )
                        desc = blip_processor.batch_decode(out_ids, skip_special_tokens=True)[0].strip()
                        if desc:
                            # Remove the prompt prefix if present
                            desc_lower = desc.lower()
                            for p in prompts:
                                if desc_lower.startswith(p.lower()):
                                    desc = desc[len(p):].strip()
                                    desc_lower = desc.lower()
                                    break
                            
                            # Remove hallucination patterns (aggressive filtering)
                            for pattern in hallucination_patterns:
                                if pattern in desc_lower:
                                    # Remove the entire sentence containing the pattern
                                    sentences = desc.split('.')
                                    cleaned_sentences = []
                                    for sentence in sentences:
                                        if pattern not in sentence.lower():
                                            cleaned_sentences.append(sentence.strip())
                                    desc = '. '.join(cleaned_sentences).strip()
                                    desc_lower = desc.lower()
                            
                            # Remove common repetitive patterns and artifacts
                            desc = desc.replace("in this image", "")
                            desc = desc.replace("in the image", "")
                            desc = desc.replace("from the", "")
                            desc = desc.replace("to the", "")
                            desc = desc.replace("of the", "")
                            
                            # Remove repetitive phrases (check for word repetition)
                            words = desc.split()
                            cleaned_words = []
                            seen_words_recent = []
                            for word in words:
                                word_lower = word.lower().strip(".,;:!?")
                                # Skip if word appears too frequently or is a common stopword
                                if words.count(word_lower) > 3 and len(word_lower) < 4:
                                    continue
                                # Skip if we just saw this word
                                if word_lower in seen_words_recent[-3:]:
                                    continue
                                cleaned_words.append(word)
                                seen_words_recent.append(word_lower)
                                if len(seen_words_recent) > 5:
                                    seen_words_recent.pop(0)
                            
                            desc = " ".join(cleaned_words).strip()
                            
                            # Remove multiple spaces
                            while "  " in desc:
                                desc = desc.replace("  ", " ")
                            
                            # Final cleanup - remove leading/trailing punctuation
                            desc = desc.strip(".,;: ")
                            # Ensure it ends with proper punctuation
                            if desc and not desc[-1] in ".!?":
                                desc = desc + "."
                            
                            # Only add if meaningful (more than 10 chars, at least 3 unique words, no hallucinations)
                            unique_words = set([w.lower().strip(".,;:!?") for w in desc.split() if len(w) > 2])
                            if len(desc) > 10 and len(unique_words) >= 3:
                                # Final check: ensure no hallucination patterns remain
                                has_hallucination = any(pattern in desc_lower for pattern in hallucination_patterns)
                                if not has_hallucination:
                                    descriptions.append(desc)
                except Exception as e:
                    print(f"BLIP Scene {i} Error: {e}")

            # Format Summary - Improved merging
            if descriptions:
                # Remove duplicates and very similar descriptions
                unique_desc = []
                seen = set()
                for desc in descriptions:
                    desc_lower = desc.lower()
                    # Check if this description is too similar to one we've seen
                    is_duplicate = False
                    for seen_desc in seen:
                        # If 80% of words overlap, consider it duplicate
                        words1 = set(desc_lower.split())
                        words2 = set(seen_desc.split())
                        if len(words1) > 0 and len(words2) > 0:
                            overlap = len(words1 & words2) / max(len(words1), len(words2))
                            if overlap > 0.8:
                                is_duplicate = True
                                break
                    if not is_duplicate:
                        unique_desc.append(desc)
                        seen.add(desc_lower)
                
                # Create a more natural summary
                if len(unique_desc) == 1:
                    full_description = unique_desc[0][0].upper() + unique_desc[0][1:] + "."
                elif len(unique_desc) > 1:
                    # Join with proper formatting
                    formatted = []
                    for d in unique_desc:
                        d_clean = d.strip()
                        if d_clean:
                            formatted.append(d_clean[0].upper() + d_clean[1:])
                    full_description = ". ".join(formatted) + "."
                else:
                    full_description = "Visuals unavailable."
            else:
                full_description = "Visuals unavailable."

            # --- PHASE 3: FINALIZE TAGS (Improved Accuracy - Target 8+ Highly Accurate Keywords) ---
            self.log_signal.emit(f"  → Finalizing tags from {len(tag_scores)} candidates...")
            sorted_tags = sorted(tag_scores.items(), key=lambda item: item[1], reverse=True)
            
            # Calculate adaptive threshold based on score distribution and mode
            if sorted_tags:
                max_score = sorted_tags[0][1]
                # Use mode-based threshold
                adaptive_threshold = max(0.1, max_score * self.tag_threshold_percent)
            else:
                adaptive_threshold = 0.1
            
            # Filter tags: higher threshold for accuracy
            # Take top 30 candidates that meet the threshold
            candidate_tags = [tag for tag, score in sorted_tags[:30] if score >= adaptive_threshold]
            
            # Accuracy mode: Cross-frame validation - tags must appear in multiple frames
            # For very strict mode: require 3+ frames instead of 2
            min_frames_required = 3 if self.mode == "accuracy" else self.min_frames_for_tag
            if self.mode == "accuracy" and tag_frame_occurrences:
                validated_candidates = []
                for tag in candidate_tags:
                    frame_count = len(tag_frame_occurrences.get(tag, set()))
                    if frame_count >= min_frames_required:
                        validated_candidates.append(tag)
                candidate_tags = validated_candidates
                self.log_signal.emit(f"  → Cross-frame validation: {len(candidate_tags)} tags appear in {min_frames_required}+ frames")
            
            # BLIP Description Validation - tags must appear in BLIP scene descriptions
            if self.mode == "accuracy" and descriptions:
                blip_text = " ".join([d.lower() for d in descriptions]).lower()
                blip_validated = []
                for tag in candidate_tags:
                    tag_lower = tag.lower()
                    # Check if tag or its words appear in BLIP descriptions
                    tag_words = tag_lower.split()
                    # Allow if any significant word from tag appears in BLIP text
                    matches = False
                    for word in tag_words:
                        if len(word) > 3 and word in blip_text:  # Only check words longer than 3 chars
                            matches = True
                            break
                    # Also check if full tag appears (for single-word tags)
                    if len(tag_words) == 1 and tag_lower in blip_text:
                        matches = True
                    if matches:
                        blip_validated.append(tag)
                candidate_tags = blip_validated
                self.log_signal.emit(f"  → BLIP validation: {len(candidate_tags)} tags match scene descriptions")
            
            # Semantic Relevance Check - tags must be semantically relevant to scene context
            if self.mode == "accuracy" and len(candidate_tags) > 0 and detected_scenes:
                try:
                    # Calculate average scene frame embeddings
                    scene_embeddings = []
                    for scene in detected_scenes[:3]:  # Use first 3 scenes
                        if scene.get('best_frame'):
                            inputs = clip_processor(images=scene['best_frame'], return_tensors="pt", padding=True).to(ai.device)
                            with torch.no_grad():
                                frame_features = clip_model.get_image_features(**inputs)
                                frame_features /= frame_features.norm(p=2, dim=-1, keepdim=True)
                                scene_embeddings.append(frame_features.cpu().numpy()[0])
                    
                    if scene_embeddings:
                        # Average scene embedding
                        avg_scene_emb = np.mean(scene_embeddings, axis=0)
                        avg_scene_emb = avg_scene_emb / np.linalg.norm(avg_scene_emb)
                        
                        # Check tag relevance
                        semantically_relevant = []
                        tag_texts = list(candidate_tags)
                        inputs = clip_processor(text=tag_texts, return_tensors="pt", padding=True).to(ai.device)
                        with torch.no_grad():
                            tag_features = clip_model.get_text_features(**inputs)
                            tag_features /= tag_features.norm(p=2, dim=-1, keepdim=True)
                            
                            for i, tag in enumerate(candidate_tags):
                                tag_emb = tag_features[i].cpu().numpy()
                                similarity = np.dot(tag_emb, avg_scene_emb)
                                if similarity >= 0.4:  # Semantic relevance threshold
                                    semantically_relevant.append(tag)
                        
                        candidate_tags = semantically_relevant
                        self.log_signal.emit(f"  → Semantic relevance: {len(candidate_tags)} tags match scene context")
                except Exception as e:
                    print(f"Semantic relevance check error: {e}")
                    # Continue without semantic check if it fails
            
            # Remove redundant/similar tags
            # For accuracy mode: use semantic similarity with CLIP embeddings
            # For speed mode: use simple substring matching
            filtered_tags = []
            if self.mode == "accuracy" and len(candidate_tags) > 0:
                # Semantic deduplication using CLIP embeddings
                try:
                    # Get embeddings for all candidate tags
                    tag_embeddings = {}
                    tag_texts = list(candidate_tags)
                    inputs = clip_processor(text=tag_texts, return_tensors="pt", padding=True).to(ai.device)
                    with torch.no_grad():
                        text_features = clip_model.get_text_features(**inputs)
                        text_features /= text_features.norm(p=2, dim=-1, keepdim=True)
                        for i, tag in enumerate(candidate_tags):
                            tag_embeddings[tag] = text_features[i].cpu().numpy()
                    
                    # Find semantically similar tags and keep only the best one
                    similarity_threshold = 0.85  # High threshold for semantic similarity
                    for tag in candidate_tags:
                        is_redundant = False
                        tag_emb = tag_embeddings[tag]
                        tag_lower = tag.lower()
                        
                        for existing in filtered_tags:
                            existing_emb = tag_embeddings[existing]
                            existing_lower = existing.lower()
                            
                            # Check substring match first (faster)
                            if tag_lower in existing_lower or existing_lower in tag_lower:
                                if len(tag) <= len(existing):
                                    is_redundant = True
                                    break
                                else:
                                    filtered_tags.remove(existing)
                                    break
                            
                            # Check semantic similarity
                            similarity = np.dot(tag_emb, existing_emb)
                            if similarity >= similarity_threshold:
                                # Keep the tag with higher score
                                tag_score = tag_scores.get(tag, 0)
                                existing_score = tag_scores.get(existing, 0)
                                if tag_score <= existing_score:
                                    is_redundant = True
                                    break
                                else:
                                    filtered_tags.remove(existing)
                                    break
                        
                        if not is_redundant:
                            filtered_tags.append(tag)
                    
                    self.log_signal.emit(f"  → Semantic deduplication: {len(filtered_tags)} unique tags after similarity filtering")
                except Exception as e:
                    # Fallback to simple substring matching if semantic deduplication fails
                    print(f"Semantic deduplication error: {e}")
                    for tag in candidate_tags:
                        is_redundant = False
                        tag_lower = tag.lower()
                        for existing in filtered_tags:
                            existing_lower = existing.lower()
                            if tag_lower in existing_lower or existing_lower in tag_lower:
                                if len(tag) <= len(existing):
                                    is_redundant = True
                                    break
                                else:
                                    filtered_tags.remove(existing)
                                    break
                        if not is_redundant:
                            filtered_tags.append(tag)
            else:
                # Speed mode: Simple substring matching
                for tag in candidate_tags:
                    is_redundant = False
                    tag_lower = tag.lower()
                    for existing in filtered_tags:
                        existing_lower = existing.lower()
                        # Check if tag is substring of existing or vice versa
                        if tag_lower in existing_lower or existing_lower in tag_lower:
                            # Keep the longer/more specific tag
                            if len(tag) <= len(existing):
                                is_redundant = True
                                break
                            else:
                                # Replace existing with more specific tag
                                filtered_tags.remove(existing)
                                break
                    if not is_redundant:
                        filtered_tags.append(tag)
            
            # Final Tag Bank Relevance Filter - remove tags that are in irrelevant list
            from core.tags import _is_irrelevant_tag
            final_filtered = []
            for tag in filtered_tags:
                if not _is_irrelevant_tag(tag):
                    final_filtered.append(tag)
            filtered_tags = final_filtered
            if len(final_filtered) < len(filtered_tags):
                self.log_signal.emit(f"  → Tag bank filter: {len(final_filtered)} tags after removing irrelevant")
            
            # Target: 8-12 highly accurate tags (reduced from 15 for stricter filtering)
            # If we have enough high-quality tags, use them
            if len(filtered_tags) >= 8:
                final_tags = filtered_tags[:12]  # Cap at 12 for very strict mode
            elif len(filtered_tags) >= 5:
                # If we have 5-7 tags, try to get a few more from slightly lower threshold
                lower_threshold = max(0.08, max_score * 0.15) if sorted_tags else 0.08
                additional_candidates = [tag for tag, score in sorted_tags[len(candidate_tags):50] 
                                       if score >= lower_threshold and tag not in filtered_tags]
                # Add a few more, but still filter for redundancy
                for tag in additional_candidates[:5]:
                    is_redundant = False
                    tag_lower = tag.lower()
                    for existing in filtered_tags:
                        existing_lower = existing.lower()
                        if tag_lower in existing_lower or existing_lower in tag_lower:
                            if len(tag) <= len(existing):
                                is_redundant = True
                                break
                    if not is_redundant:
                        filtered_tags.append(tag)
                final_tags = filtered_tags[:12]  # Cap at 12 for very strict mode
            else:
                # Fallback: If we have very few tags, lower threshold slightly but still maintain quality
                if sorted_tags:
                    fallback_threshold = max(0.05, max_score * 0.10)
                    fallback_candidates = [tag for tag, score in sorted_tags[:25] if score >= fallback_threshold]
                    # Apply same redundancy filtering
                    for tag in fallback_candidates:
                        if tag in filtered_tags:
                            continue
                        is_redundant = False
                        tag_lower = tag.lower()
                        for existing in filtered_tags:
                            existing_lower = existing.lower()
                            if tag_lower in existing_lower or existing_lower in tag_lower:
                                if len(tag) <= len(existing):
                                    is_redundant = True
                                    break
                        if not is_redundant:
                            filtered_tags.append(tag)
                            if len(filtered_tags) >= 8:
                                break
                    final_tags = filtered_tags[:12]  # Cap at 12 for very strict mode
                else:
                    final_tags = []
            
            # Final safety: Ensure we have at least 8 tags if possible
            if len(final_tags) < 8 and sorted_tags:
                # Take top 8-12 by score, but still apply basic filtering
                top_by_score = [t[0] for t in sorted_tags[:12]]
                for tag in top_by_score:
                    if tag not in final_tags:
                        # Quick redundancy check
                        is_redundant = False
                        tag_lower = tag.lower()
                        for existing in final_tags:
                            if tag_lower in existing.lower() or existing.lower() in tag_lower:
                                if len(tag) <= len(existing):
                                    is_redundant = True
                                    break
                        if not is_redundant:
                            final_tags.append(tag)
                            if len(final_tags) >= 12:
                                break

            # --- PHASE 4: DETECT SHOT TYPE ---
            shot_type = "Unknown"
            if detected_scenes and len(detected_scenes) > 0:
                # Use the best frame from the first scene (or most representative)
                best_scene_frame = detected_scenes[0]['best_frame']
                if best_scene_frame is None and len(detected_scenes) > 1:
                    best_scene_frame = detected_scenes[1]['best_frame']
                
                if best_scene_frame is not None:
                    try:
                        # Shot type tags to match against
                        shot_type_tags = [
                            "Close-up", "Close up", "Extreme Close-up", "Extreme Close up",
                            "Medium Shot", "Medium Close-up", "Medium Close up",
                            "Wide Shot", "Long Shot", "Extreme Wide Shot", "Extreme Long Shot",
                            "Establishing Shot", "Aerial Shot", "Aerial View",
                            "Overhead Shot", "Bird's Eye View", "Low Angle Shot", "High Angle Shot",
                            "Dutch Angle", "Point of View Shot", "POV Shot",
                            "Two Shot", "Three Shot", "Group Shot", "Crowd Shot"
                        ]
                        
                        # Process frame for CLIP
                        inputs = clip_processor(images=best_scene_frame, return_tensors="pt", padding=True).to(ai.device)
                        with torch.no_grad():
                            frame_features = clip_model.get_image_features(**inputs)
                            frame_features /= frame_features.norm(p=2, dim=-1, keepdim=True)
                            
                            # Encode shot type tags
                            shot_inputs = clip_processor(text=shot_type_tags, return_tensors="pt", padding=True).to(ai.device)
                            shot_text_features = clip_model.get_text_features(**shot_inputs)
                            shot_text_features /= shot_text_features.norm(p=2, dim=-1, keepdim=True)
                            
                            # Calculate similarity
                            similarities = (frame_features @ shot_text_features.T).cpu().numpy()[0]
                            
                            # Get best match
                            best_idx = np.argmax(similarities)
                            best_score = float(similarities[best_idx])
                            
                            # Only use if confidence is high enough (0.3 threshold)
                            if best_score >= 0.3:
                                shot_type = shot_type_tags[best_idx]
                            else:
                                # Fallback: analyze frame composition
                                # Check if it's likely a close-up (face/object fills frame)
                                # or wide shot (lots of background visible)
                                # Simple heuristic based on edge density and subject size
                                shot_type = "Medium Shot"  # Default
                    except Exception as e:
                        print(f"Shot type detection error: {e}")
                        shot_type = "Unknown"

            # Store visual descriptions temporarily (will be combined with audio later by transcriber)
            # Don't save final summary yet - wait for audio transcription to generate unified summary
            visual_descriptions_list = []
            if full_description and full_description != "Visuals unavailable.":
                # Split by sentences for better LLM processing
                visual_descriptions_list = [d.strip() for d in full_description.split('.') if d.strip()]
            
            # Save visual descriptions temporarily for later summary generation
            db.update_metadata_key(video_path, "visual_descriptions_temp", visual_descriptions_list)
            
            # For now, save a placeholder summary (will be replaced when audio is transcribed)
            final_summary = full_description

            # --- PHASE 5: EMOTION & OBJECT DETECTION ---
            detected_emotions = []
            detected_objects = []
            
            if detected_scenes and len(detected_scenes) > 0:
                # Use representative frames from scenes for emotion/object detection
                sample_frames = []
                for scene in detected_scenes[:3]:  # Use first 3 scenes
                    if scene.get('best_frame'):
                        sample_frames.append(scene['best_frame'])
                
                if sample_frames:
                    try:
                        # Emotion Detection
                        emotion_prompts = [
                            "happy face", "sad face", "angry face", "surprised face", 
                            "neutral face", "excited face", "worried face", "confused face"
                        ]
                        
                        # Object Detection Prompts
                        object_prompts = [
                            "person holding phone", "person holding camera", "person holding book",
                            "person holding cup", "person holding bag", "person near car",
                            "person near computer", "person near table", "person near door"
                        ]
                        
                        # Process frames for emotion detection
                        for frame in sample_frames:
                            inputs = clip_processor(images=frame, return_tensors="pt", padding=True).to(ai.device)
                            with torch.no_grad():
                                frame_features = clip_model.get_image_features(**inputs)
                                frame_features /= frame_features.norm(p=2, dim=-1, keepdim=True)
                                
                                # Check emotions
                                emotion_inputs = clip_processor(text=emotion_prompts, return_tensors="pt", padding=True).to(ai.device)
                                emotion_text_features = clip_model.get_text_features(**emotion_inputs)
                                emotion_text_features /= emotion_text_features.norm(p=2, dim=-1, keepdim=True)
                                emotion_similarities = (frame_features @ emotion_text_features.T).cpu().numpy()[0]
                                
                                best_emotion_idx = np.argmax(emotion_similarities)
                                best_emotion_score = float(emotion_similarities[best_emotion_idx])
                                
                                if best_emotion_score >= 0.3:  # Threshold for emotion detection
                                    emotion_name = emotion_prompts[best_emotion_idx].replace(" face", "").title()
                                    if emotion_name not in detected_emotions:
                                        detected_emotions.append(emotion_name)
                                
                                # Check objects
                                object_inputs = clip_processor(text=object_prompts, return_tensors="pt", padding=True).to(ai.device)
                                object_text_features = clip_model.get_text_features(**object_inputs)
                                object_text_features /= object_text_features.norm(p=2, dim=-1, keepdim=True)
                                object_similarities = (frame_features @ object_text_features.T).cpu().numpy()[0]
                                
                                best_object_idx = np.argmax(object_similarities)
                                best_object_score = float(object_similarities[best_object_idx])
                                
                                if best_object_score >= 0.3:  # Threshold for object detection
                                    object_desc = object_prompts[best_object_idx]
                                    if object_desc not in detected_objects:
                                        detected_objects.append(object_desc)
                    except Exception as e:
                        print(f"Emotion/Object detection error: {e}")
            
            # Save tags, summary, shot type, emotions, and objects
            self.log_signal.emit(f"  → Saving {len(final_tags)} tags, summary, and context data...")
            db.save_tags(video_path, final_tags, final_summary)
            db.update_metadata_key(video_path, "shot_type", shot_type)
            if detected_emotions:
                db.update_metadata_key(video_path, "emotions", detected_emotions)
            if detected_objects:
                db.update_metadata_key(video_path, "objects", detected_objects)
            
            # Update last_scanned timestamp for incremental indexing
            try:
                file_mtime = os.path.getmtime(video_path)
                db.update_metadata_key(video_path, "last_scanned", file_mtime)
            except OSError:
                db.update_metadata_key(video_path, "last_scanned", time.time())
            
            self.summary_signal.emit(video_path, final_summary)
            self.log_signal.emit(f"  Completed: {filename} ({len(final_tags)} tags, {shot_type})")
        
        # Cleanup - Keep CLIP loaded as transcriber needs it for embeddings
        logger.debug("Unloading models (keeping CLIP for transcript embeddings)")
        try:
            ai.unload_models(keep_clip=True)
            logger.debug("Models unloaded successfully")
        except Exception as e:
            logger.exception("Error unloading models")
            raise
        self.progress_signal.emit(100)
        logger.debug("Indexing complete, emitting finished signal")
        self.finished_signal.emit()

    def process_batch(self, images, timestamps, ai, db, video_path, model, processor, tag_list, tag_scores, tag_frame_occurrences=None, start_frame_idx=None):
        try:
            inputs = processor(images=images, return_tensors="pt", padding=True).to(ai.device)
            with torch.no_grad():
                img_features = model.get_image_features(**inputs)
                img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                
                # OPTIMIZATION: Batch database writes instead of immediate writes
                vectors_list = img_features.cpu().numpy().tolist()
                
                # Store in batch instead of immediate write
                if hasattr(self, 'db_write_batch'):
                    for vec, ts in zip(vectors_list, timestamps):
                        self.db_write_batch.append((vec, ts))
                    
                    # Flush batch when it reaches threshold
                    if len(self.db_write_batch) >= self.db_write_batch_size:
                        self._flush_db_batch(db, video_path)
                else:
                    # Fallback to immediate write
                    db.add_visual_embeddings(video_path, vectors_list, timestamps)
                
                # Match against tags - Enhanced with contextual awareness and hierarchical support
                from core.tags import get_tag_parent, get_tag_family
                
                # Use cosine similarity directly (0-1 range) instead of softmax
                # This preserves the actual similarity strength
                raw_similarity = img_features @ ai.tag_embeddings.T  # (batch_size, tag_count)
                # Normalize to 0-1 range for better interpretability
                raw_similarity = (raw_similarity + 1.0) / 2.0  # Cosine similarity is -1 to 1, map to 0-1
                
                # Get top matches per image (reduced to 15 for better accuracy, less noise)
                values, indices = raw_similarity.topk(15, dim=-1)
                
                vals_np = values.cpu().numpy()
                inds_np = indices.cpu().numpy()
                
                # Contextual tag matching: Track tag co-occurrences in this batch
                tag_cooccurrences = defaultdict(set)
                
                for i in range(len(images)):    
                    current_frame_idx = start_frame_idx + i if (start_frame_idx is not None and tag_frame_occurrences is not None) else None
                    
                    # Collect tags for this frame for contextual analysis
                    frame_tags = []
                    
                    for rank in range(15):
                        tag_idx = inds_np[i][rank]
                        confidence = float(vals_np[i][rank])
                        tag_name = tag_list[tag_idx]
                        
                        # Enhanced confidence calibration based on tag type
                        # Objects and actions get higher thresholds, abstract concepts get lower
                        tag_type_threshold = 0.4  # Default
                        if any(word in tag_name.lower() for word in ["person", "man", "woman", "people"]):
                            tag_type_threshold = 0.45  # Slightly higher for people (common false positives)
                        elif tag_name.endswith("ing") or tag_name in ["Running", "Walking", "Sitting", "Standing"]:
                            tag_type_threshold = 0.42  # Actions
                        elif any(word in tag_name.lower() for word in ["car", "vehicle", "phone", "laptop"]):
                            tag_type_threshold = 0.38  # Objects (more reliable)
                        
                        # Only process if above type-specific threshold
                        if confidence >= tag_type_threshold:
                            frame_tags.append((tag_name, confidence))
                            
                            # Improved scoring: Weight by rank (top matches get significantly more weight)
                            rank_weight = 1.0 / ((rank + 1) ** 1.5)  # Exponential decay
                            weighted_score = confidence * rank_weight
                            
                            tag_scores[tag_name] += weighted_score
                            
                            # Track frame occurrences for accuracy mode
                            if current_frame_idx is not None and tag_frame_occurrences is not None:
                                tag_frame_occurrences[tag_name].add(current_frame_idx)
                    
                    # Contextual awareness: Boost tags that co-occur with related tags
                    for tag1, conf1 in frame_tags:
                        tag_family = get_tag_family(tag1)
                        for tag2, conf2 in frame_tags:
                            if tag1 != tag2:
                                # If tags are related (same family), boost both
                                if tag2 in tag_family or tag1 in get_tag_family(tag2):
                                    # Small contextual boost
                                    contextual_boost = 0.05 * min(conf1, conf2)
                                    tag_scores[tag1] += contextual_boost
                                    tag_scores[tag2] += contextual_boost
                                
                                # Track co-occurrences
                                tag_cooccurrences[tag1].add(tag2)
        except Exception as e:
            print(f"Batch Error: {e}")

    def _flush_db_batch(self, db, video_path):
        """Flush batched embeddings to database."""
        if not hasattr(self, 'db_write_batch') or not self.db_write_batch:
            return
        
        vectors = [item[0] for item in self.db_write_batch]
        timestamps = [item[1] for item in self.db_write_batch]
        db.add_visual_embeddings(video_path, vectors, timestamps)
        self.db_write_batch.clear()

    def stop(self):
        self.is_running = False