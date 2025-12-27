# [FILE: workers/indexer.py]
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
        
        # --- Smart Indexing Settings (RESTORED) ---
        self.scene_threshold = 0.65  # Sensitivity to cuts
        self.min_interval = 1.0      # Min 1 sec between keyframes
        self.max_interval = 15.0     # Max 15 sec (catch slow pans)

    def calculate_histogram(self, image):
        """Creates a color fingerprint for the frame to detect cuts."""
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    def run(self):
        self.progress_signal.emit(1)
        self.log_signal.emit("Initializing Dual-Core AI (Smart Scene + Captioning)...")
        
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            # 1. Load BOTH Models
            # CLIP for fast scanning & tags, BLIP for the final sentence
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
            
            self.log_signal.emit(f"Deep Scanning: {video_path}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): continue
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0: fps = 24.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Identify the middle frame index (best candidate for a general summary)
            midpoint_frame = total_frames // 2
            best_thumbnail_for_blip = None
            
            frames_batch = []
            timestamps_batch = []
            
            # Accumulator for CLIP Tags
            tag_scores = defaultdict(float)
            
            prev_hist = None
            last_indexed_time = -self.max_interval
            
            # Scan Step
            scan_step = int(fps / 5) if fps > 20 else 2
            
            for frame_num in range(0, total_frames, scan_step):
                if not self.is_running: break
                
                if frame_num % 100 == 0:
                    current_percent = int(((idx) / total_files * 100) + (frame_num / total_frames * (100 / total_files)))
                    self.progress_signal.emit(current_percent)

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret: break
                
                current_time = frame_num / fps
                
                # --- SNAPSHOT FOR BLIP ---
                # If we are near the middle, grab this frame for the caption generator
                if best_thumbnail_for_blip is None and frame_num >= midpoint_frame:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    best_thumbnail_for_blip = Image.fromarray(rgb)

                # --- SCENE DETECTION LOGIC ---
                time_since_last = current_time - last_indexed_time
                should_index = False
                
                curr_hist = self.calculate_histogram(frame)
                
                if time_since_last >= self.max_interval:
                    should_index = True
                elif time_since_last >= self.min_interval:
                    if prev_hist is not None:
                        similarity = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
                        if similarity < self.scene_threshold:
                            should_index = True
                    else:
                        should_index = True

                if should_index:
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(img_rgb)
                    
                    # If we missed the midpoint (short video), grab the first indexed frame
                    if best_thumbnail_for_blip is None:
                        best_thumbnail_for_blip = pil_img

                    frames_batch.append(pil_img)
                    timestamps_batch.append(current_time)
                    
                    prev_hist = curr_hist
                    last_indexed_time = current_time

                    if len(frames_batch) >= self.batch_size:
                        self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores)
                        frames_batch = []
                        timestamps_batch = []

            # Process remaining CLIP batch
            if frames_batch:
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, clip_model, clip_processor, tag_list, tag_scores)
            
            cap.release()
            
            # --- PHASE 2: GENERATE SENTENCE (BLIP) ---
            # We run this ONCE per video using the representative frame
            description = "No description generated."
            if best_thumbnail_for_blip:
                try:
                    inputs = blip_processor(images=best_thumbnail_for_blip, return_tensors="pt").to(ai.device)
                    with torch.no_grad():
                        out = blip_model.generate(**inputs, max_new_tokens=50)
                        raw_desc = blip_processor.decode(out[0], skip_special_tokens=True)
                        description = raw_desc[0].upper() + raw_desc[1:]
                except Exception as e:
                    print(f"BLIP Error: {e}")

            # --- PHASE 3: FINALIZE TAGS (CLIP) ---
            sorted_tags = sorted(tag_scores.items(), key=lambda item: item[1], reverse=True)
            
            # 5% Confidence Threshold (Optimized for Large Vocab)
            final_tags = [tag for tag, score in sorted_tags[:25] if score > 0.05]
            if not final_tags and sorted_tags:
                final_tags = [t[0] for t in sorted_tags[:5]]

            # Combine everything
            # Summary = BLIP Sentence + Transcript (if any)
            # Tags = CLIP Keywords
            
            # Check for transcript to append
            current_meta = db.get_video_metadata(video_path)
            transcript_data = current_meta.get("transcript", [])
            
            final_summary = description
            if transcript_data:
                 full_text = " ".join([t['text'] for t in transcript_data])
                 words = full_text.split()[:15]
                 final_summary += f" | Audio: \"{' '.join(words)}...\""

            # SAVE
            db.save_tags(video_path, final_tags, final_summary)
            self.summary_signal.emit(video_path, final_summary)
        
        ai.unload_models()
        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def process_batch(self, images, timestamps, ai, db, video_path, model, processor, tag_list, tag_scores):
        """Standard CLIP processing for Vectors and Tags"""
        try:
            inputs = processor(images=images, return_tensors="pt", padding=True).to(ai.device)
            with torch.no_grad():
                img_features = model.get_image_features(**inputs)
                img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                
                # 1. SAVE VECTORS (Crucial for Search Tab)
                vectors_list = img_features.cpu().numpy().tolist()
                db.add_visual_embeddings(video_path, vectors_list, timestamps)
                
                # 2. ACCUMULATE TAGS
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