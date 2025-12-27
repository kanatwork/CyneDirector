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
        self.batch_size = 64 # Smaller batch size for better VRAM management during heavy inference
        
        # --- Smart Indexing Settings ---
        self.scene_threshold = 0.65  # Slightly more sensitive to cuts
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
        self.log_signal.emit("Initializing AI Core (Smart Weighting Mode)...")
        
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            model, processor = ai.load_clip()
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
            
            frames_batch = []
            timestamps_batch = []
            
            # --- ACCUMULATOR FOR SMART TAGS ---
            # Format: { 'TagString': accumulated_score }
            tag_scores = defaultdict(float)
            
            prev_hist = None
            last_indexed_time = -self.max_interval
            
            # Scan Step: Adaptive based on FPS (approx every 0.2s check)
            scan_step = int(fps / 5) if fps > 20 else 2
            
            for frame_num in range(0, total_frames, scan_step):
                if not self.is_running: break
                
                # Progress update
                if frame_num % 100 == 0:
                    current_percent = int(((idx) / total_files * 100) + (frame_num / total_frames * (100 / total_files)))
                    self.progress_signal.emit(current_percent)

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret: break
                
                current_time = frame_num / fps
                time_since_last = current_time - last_indexed_time
                should_index = False
                
                curr_hist = self.calculate_histogram(frame)
                
                # 1. Force Keyframe if max interval reached
                if time_since_last >= self.max_interval:
                    should_index = True
                
                # 2. Scene Cut Detection
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
                    
                    frames_batch.append(pil_img)
                    timestamps_batch.append(current_time)
                    
                    prev_hist = curr_hist
                    last_indexed_time = current_time

                    if len(frames_batch) >= self.batch_size:
                        self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, model, processor, tag_list, tag_scores)
                        frames_batch = []
                        timestamps_batch = []

            # Process remaining
            if frames_batch:
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, model, processor, tag_list, tag_scores)
            
            cap.release()
            
            # --- FINAL TAG SELECTION ---
            # Sort tags by their accumulated score (Highest confidence + frequency)
            sorted_tags = sorted(tag_scores.items(), key=lambda item: item[1], reverse=True)
            
            # Filter: Take top 15 tags, but only if they have a decent score
            final_tags = [tag for tag, score in sorted_tags[:15] if score > 0.5]
            
            # If the list is empty (dark video?), take at least top 3
            if not final_tags and sorted_tags:
                final_tags = [t[0] for t in sorted_tags[:3]]

            # Generate Summary Text
            if final_tags:
                # First 5 tags are "Primary", rest are "Context"
                primary = ", ".join(final_tags[:5])
                base_summary = f"Visuals: {primary}"
            else:
                base_summary = "No clear visual subjects identified."

            # Merge with Transcript if available
            current_meta = db.get_video_metadata(video_path)
            transcript_data = current_meta.get("transcript", [])
            
            if transcript_data:
                # Use first 15 words of transcript
                full_text = " ".join([t['text'] for t in transcript_data])
                words = full_text.split()[:15]
                text_preview = " ".join(words)
                summary_text = f"{base_summary} | Audio: \"{text_preview}...\""
            else:
                summary_text = base_summary

            db.save_tags(video_path, final_tags, summary_text)
            self.summary_signal.emit(video_path, summary_text)
        
        ai.unload_models()
        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def process_batch(self, images, timestamps, ai, db, video_path, model, processor, tag_list, tag_scores):
        try:
            inputs = processor(images=images, return_tensors="pt", padding=True).to(ai.device)
            with torch.no_grad():
                img_features = model.get_image_features(**inputs)
                img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                
                # 1. Save Vector Embeddings (For "Find Similar" search)
                vectors_list = img_features.cpu().numpy().tolist()
                db.add_visual_embeddings(video_path, vectors_list, timestamps)
                
                # 2. Calculate Tag Probabilities (Dot Product)
                # similarity shape: [batch_size, num_tags]
                similarity = (100.0 * img_features @ ai.tag_embeddings.T).softmax(dim=-1)
                
                # Get top 5 tags for EACH frame in the batch
                # values: [batch_size, 5], indices: [batch_size, 5]
                values, indices = similarity.topk(5, dim=-1)
                
                vals_np = values.cpu().numpy()
                inds_np = indices.cpu().numpy()
                
                # 3. Accumulate Weighted Scores
                for i in range(len(images)):
                    for rank in range(5):
                        tag_idx = inds_np[i][rank]
                        confidence = vals_np[i][rank] # 0.0 to 1.0 (after softmax)
                        tag_name = tag_list[tag_idx]
                        
                        # LOGIC: 
                        # - We add the raw confidence to the global score.
                        # - If "Dog" appears in 10 frames with 0.9 confidence, score = 9.0
                        # - If "Cat" appears in 1 frame with 0.9 confidence, score = 0.9
                        # - This naturally favors sustained objects but catches distinct high-confidence ones.
                        tag_scores[tag_name] += confidence

        except Exception as e:
            print(f"Batch Error: {e}")

    def stop(self):
        self.is_running = False