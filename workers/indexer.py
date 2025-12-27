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
        self.batch_size = 64 
        
        # --- Logic Settings ---
        self.scene_threshold = 0.60  # Sensitivity to scene changes (Lower = more sensitive)
        self.min_interval = 1.0      # Minimum time between scanning frames
        self.blur_threshold = 100.0  # Frames below this score are considered "Motion Blurs" and ignored

    def calculate_histogram(self, image):
        """Creates a color fingerprint for the frame to detect cuts/motion."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    def calculate_sharpness(self, image):
        """
        Returns a score representing how focused the image is.
        Low score (<100) usually means fast camera movement (Blur).
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()

    def run(self):
        self.progress_signal.emit(1)
        self.log_signal.emit("Initializing Smart-Action AI (Blur-Gate Enabled)...")
        
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            # Load BOTH Models (CLIP for tags, BLIP-2 for descriptions)
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
            
            self.log_signal.emit(f"Deep Analysis: {video_path}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): continue
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0: fps = 24.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # --- SCENE CONTAINER ---
            # We store "Candidate Frames" for each distinct scene found in the clip
            # Structure: [ {'best_frame': img, 'score': 0.0}, ... ]
            detected_scenes = []
            
            # Current scene tracker
            current_scene = {'best_frame': None, 'score': -1.0}
            
            # Batching for CLIP (Tags)
            frames_batch = []
            timestamps_batch = []
            tag_scores = defaultdict(float)
            
            prev_hist = None
            last_indexed_time = -self.max_interval
            
            # Scan 3 times per second (balance between speed and accuracy)
            scan_step = int(fps / 3) if fps > 10 else 1
            
            for frame_num in range(0, total_frames, scan_step):
                if not self.is_running: break
                
                # UI Progress
                if frame_num % 50 == 0:
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
                
                # If similarity drops drastically, we entered a new "Scene" (Subject 2?)
                if similarity < self.scene_threshold:
                    # Save the previous scene's best frame if it was good
                    if current_scene['best_frame'] is not None:
                        detected_scenes.append(current_scene)
                    # Reset tracker for new scene
                    current_scene = {'best_frame': None, 'score': -1.0}

                # --- 2. FIND BEST ACTION FRAME (With Blur Gate) ---
                # We want: HIGH change (low similarity) AND HIGH sharpness
                # If camera moves fast -> Sharpness drops -> Score drops -> Ignored.
                if prev_hist is not None:
                    motion_score = (1.0 - similarity) # 0.0 (still) to 1.0 (big move)
                    
                    # Logic: 
                    # If image is blurry (<100), penalty is massive.
                    # If image is sharp, we reward motion.
                    if sharpness > self.blur_threshold:
                        # Composite Score: Motion * Sharpness
                        quality_score = motion_score * sharpness
                        
                        if quality_score > current_scene['score']:
                            current_scene['score'] = quality_score
                            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            current_scene['best_frame'] = Image.fromarray(rgb)

                # --- 3. INDEXING FOR TAGS (Standard) ---
                time_since_last = current_time - last_indexed_time
                should_index = False
                
                if time_since_last >= self.max_interval:
                    should_index = True
                elif time_since_last >= self.min_interval:
                     # Index if there's enough change, but not blurry garbage
                     if similarity < 0.85 and sharpness > self.blur_threshold:
                         should_index = True

                if should_index:
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(img_rgb)
                    
                    frames_batch.append(pil_img)
                    timestamps_batch.append(current_time)
                    last_indexed_time = current_time

                    if len(frames_batch) >= self.batch_size:
                        self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores)
                        frames_batch = []
                        timestamps_batch = []
                        
                prev_hist = curr_hist

            # End of file: Save the last active scene
            if current_scene['best_frame'] is not None:
                detected_scenes.append(current_scene)

            # Process remaining CLIP batch
            if frames_batch:
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores)
            
            cap.release()
            
            # --- PHASE 2: GENERATE MULTI-SCENE DESCRIPTION (BLIP-2) ---
            descriptions = []
            
            # Limit to max 3 scenes per clip to prevent spamming
            final_scenes = detected_scenes[:3]
            if not final_scenes and total_frames > 0:
                # Fallback: If no "Action" passed the blur gate, just grab the middle frame
                # This happens for very still shots (interviews).
                pass # We rely on CLIP tags in this case
            
            for i, scene in enumerate(final_scenes):
                try:
                    inputs = blip_processor(images=scene['best_frame'], return_tensors="pt").to(ai.device, dtype=ai.dtype)
                    with torch.no_grad():
                        out_ids = blip_model.generate(**inputs, max_new_tokens=40) # Short sentence
                        desc = blip_processor.batch_decode(out_ids, skip_special_tokens=True)[0].strip()
                        if desc:
                            # Cleanup punctuation
                            if desc.endswith('.'): desc = desc[:-1]
                            descriptions.append(desc)
                except Exception as e:
                    print(f"BLIP Scene {i} Error: {e}")

            # Join sentences: "A woman running. A man drinking coffee."
            if descriptions:
                # Dedup sentences (in case the scene split was redundant)
                unique_desc = list(dict.fromkeys(descriptions))
                full_description = ". ".join([d[0].upper() + d[1:] for d in unique_desc]) + "."
            else:
                full_description = "Static shot or unclear action."

            # --- PHASE 3: FINALIZE TAGS (CLIP) ---
            sorted_tags = sorted(tag_scores.items(), key=lambda item: item[1], reverse=True)
            final_tags = [tag for tag, score in sorted_tags[:25] if score > 0.05]
            if not final_tags and sorted_tags:
                final_tags = [t[0] for t in sorted_tags[:5]]

            # Merge with Transcript
            current_meta = db.get_video_metadata(video_path)
            transcript_data = current_meta.get("transcript", [])
            
            final_summary = full_description
            if transcript_data:
                 full_text = " ".join([t['text'] for t in transcript_data])
                 words = full_text.split()[:15]
                 final_summary += f" | Audio: \"{' '.join(words)}...\""

            db.save_tags(video_path, final_tags, final_summary)
            self.summary_signal.emit(video_path, final_summary)
        
        ai.unload_models()
        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def process_batch(self, images, timestamps, ai, db, video_path, model, processor, tag_list, tag_scores):
        try:
            inputs = processor(images=images, return_tensors="pt", padding=True).to(ai.device)
            with torch.no_grad():
                img_features = model.get_image_features(**inputs)
                img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                
                vectors_list = img_features.cpu().numpy().tolist()
                db.add_visual_embeddings(video_path, vectors_list, timestamps)
                
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