# [FILE: workers/indexer.py]
import os
from PyQt6.QtCore import QThread, pyqtSignal
import cv2
import torch
import numpy as np
from PIL import Image
from core.ai_models import AIBackend
from core.database import Database
from core.tags import get_tag_bank
from collections import defaultdict

class IndexerWorker(QThread):
    log_signal = pyqtSignal(str)       
    progress_signal = pyqtSignal(int)      
    finished_signal = pyqtSignal()
    summary_signal = pyqtSignal(str, str)  
    
    def __init__(self, file_paths, project_path):
        super().__init__()
        self.file_paths = file_paths
        self.project_path = project_path
        self.is_running = True
        self.batch_size = 32 # Reduced slightly to be safe on VRAM
        
        # --- Logic Settings ---
        self.scene_threshold = 0.60  # Sensitivity to scene changes
        self.min_interval = 1.0      # Minimum time between scanning frames
        self.max_interval = 15.0     # Max time before forcing a scan
        
        # Lower blur threshold for cinematic footage
        self.blur_threshold = 50.0  

    def calculate_histogram(self, image):
        """Creates a color fingerprint for the frame to detect cuts/motion."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
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
        self.progress_signal.emit(1)
        self.log_signal.emit("Initializing Smart-Action AI (Blur-Gate Enabled)...")
        
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            # Load Models
            clip_model, clip_processor = ai.load_clip()
            blip_model, blip_processor = ai.load_blip()
        except Exception as e:
            self.log_signal.emit(f"AI Load Error: {e}")
            self.finished_signal.emit()
            return
            
        tag_list = get_tag_bank()
        total_files = len(self.file_paths)
        
        for idx, video_path in enumerate(self.file_paths):
            if not self.is_running: break
            
            self.log_signal.emit(f"Deep Analysis: {os.path.basename(video_path)}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): continue
            
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
            
            prev_hist = None
            last_indexed_time = -self.max_interval
            
            # Scan Step
            scan_step = int(fps / 3) if fps > 10 else 1
            
            for frame_num in range(0, total_frames, scan_step):
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
                if prev_hist is not None:
                    similarity = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
                
                # New Scene Detected?
                if similarity < self.scene_threshold:
                    if current_scene['best_frame'] is not None:
                        detected_scenes.append(current_scene)
                    current_scene = {'best_frame': None, 'score': -1.0}

                # --- 2. FIND BEST ACTION FRAME ---
                if prev_hist is not None:
                    motion_score = (1.0 - similarity)
                    if sharpness > self.blur_threshold:
                        quality_score = motion_score * sharpness
                        if quality_score > current_scene['score']:
                            current_scene['score'] = quality_score
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            pil_img = Image.fromarray(rgb)
                            
                            # OPTIMIZATION: Resize immediately to save RAM
                            # We only need ~384px for BLIP captioning
                            current_scene['best_frame'] = self._resize_for_ai(pil_img, 480)

                # --- 3. INDEXING FOR TAGS (CLIP) ---
                time_since_last = current_time - last_indexed_time
                should_index = False
                
                if time_since_last >= self.max_interval:
                    should_index = True
                elif time_since_last >= self.min_interval:
                     if similarity < 0.85 and sharpness > self.blur_threshold:
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

                    if len(frames_batch) >= self.batch_size:
                        self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores)
                        frames_batch = []
                        timestamps_batch = []
                        
                prev_hist = curr_hist

            # --- END OF FILE PROCESSING ---
            if current_scene['best_frame'] is not None:
                detected_scenes.append(current_scene)

            # Process leftover batch
            if frames_batch:
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores)
            
            cap.release()

            # --- PHASE 2: GENERATE DESCRIPTIONS (BLIP-2) ---
            descriptions = []
            final_scenes = detected_scenes[:3] # Max 3 scenes per video
            
            # Fallback: If no good frames found, try grabbing middle frame
            if not final_scenes and total_frames > 0:
                try:
                    cap_retry = cv2.VideoCapture(video_path)
                    cap_retry.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
                    ret, frame = cap_retry.read()
                    cap_retry.release()
                    if ret:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(rgb)
                        # Resize fallback too
                        final_scenes.append({'best_frame': self._resize_for_ai(pil_img, 480), 'score': 0.0})
                except: pass
            
            for i, scene in enumerate(final_scenes):
                try:
                    # Pass the resized image to BLIP
                    # Ensure we use the correct device and dtype from AIBackend
                    inputs = blip_processor(images=scene['best_frame'], return_tensors="pt").to(ai.device)
                    
                    # BLIP needs inputs in the correct dtype if model is float16
                    if ai.dtype == torch.float16:
                        inputs["pixel_values"] = inputs["pixel_values"].half()

                    with torch.no_grad():
                        out_ids = blip_model.generate(**inputs, max_new_tokens=40)
                        desc = blip_processor.batch_decode(out_ids, skip_special_tokens=True)[0].strip()
                        if desc:
                            if desc.endswith('.'): desc = desc[:-1]
                            descriptions.append(desc)
                except Exception as e:
                    print(f"BLIP Scene {i} Error: {e}")

            # Format Summary
            if descriptions:
                unique_desc = list(dict.fromkeys(descriptions))
                full_description = ". ".join([d[0].upper() + d[1:] for d in unique_desc]) + "."
            else:
                full_description = "Visuals unavailable."

            # --- PHASE 3: FINALIZE TAGS ---
            sorted_tags = sorted(tag_scores.items(), key=lambda item: item[1], reverse=True)
            final_tags = [tag for tag, score in sorted_tags[:25] if score > 0.05]
            if not final_tags and sorted_tags:
                final_tags = [t[0] for t in sorted_tags[:5]]

            # Append Audio context if available
            current_meta = db.get_video_metadata(video_path)
            transcript_data = current_meta.get("transcript", [])
            final_summary = full_description
            if transcript_data:
                 full_text = " ".join([t['text'] for t in transcript_data])
                 words = full_text.split()[:15]
                 final_summary += f" | Audio: \"{' '.join(words)}...\""

            db.save_tags(video_path, final_tags, final_summary)
            self.summary_signal.emit(video_path, final_summary)
        
        # Cleanup
        ai.unload_models()
        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def process_batch(self, images, timestamps, ai, db, video_path, model, processor, tag_list, tag_scores):
        try:
            inputs = processor(images=images, return_tensors="pt", padding=True).to(ai.device)
            with torch.no_grad():
                img_features = model.get_image_features(**inputs)
                img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                
                # Save vectors to DB
                vectors_list = img_features.cpu().numpy().tolist()
                db.add_visual_embeddings(video_path, vectors_list, timestamps)
                
                # Match against tags
                # (Batch Size x 512) @ (Tag Count x 512).T
                similarity = (100.0 * img_features @ ai.tag_embeddings.T).softmax(dim=-1)
                values, indices = similarity.topk(15, dim=-1)
                
                vals_np = values.cpu().numpy()
                inds_np = indices.cpu().numpy()
                
                for i in range(len(images)):    
                    for rank in range(15):
                        tag_idx = inds_np[i][rank]
                        confidence = vals_np[i][rank]
                        tag_name = tag_list[tag_idx]
                        tag_scores[tag_name] += confidence
        except Exception as e:
            print(f"Batch Error: {e}")

    def stop(self):
        self.is_running = False