from PyQt6.QtCore import QThread, pyqtSignal
import cv2
import torch
import numpy as np
from PIL import Image
from core.ai_models import AIBackend
from core.database import Database
from core.tags import get_tag_bank
from collections import Counter

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
        self.batch_size = 96
        
        # Smart Indexing Settings
        self.scene_threshold = 0.7  # Similarity score (lower = distinct scene)
        self.min_interval = 1.0     # Minimum 1 sec between frames (prevents burst)
        self.max_interval = 20.0    # Force index every 20 secs (for long takes)

    def calculate_histogram(self, image):
        """Creates a color fingerprint for the frame to detect cuts."""
        # Convert to HSV for better color perception
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # Calculate hist: (Hue: 50 bins, Saturation: 60 bins)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    def run(self):
        self.progress_signal.emit(1)
        self.log_signal.emit("Initializing AI Core (Smart Mode)...")
        
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
            
            self.log_signal.emit(f"Indexing: {video_path}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): continue
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0: fps = 24.0 # Fallback
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            frames_batch = []
            timestamps_batch = []
            all_detected_indices = []
            
            # --- SMART SCANNING VARIABLES ---
            prev_hist = None
            last_indexed_time = -self.max_interval # Ensure first frame is caught
            
            # Scan every 5th frame to speed up "Watching" 
            # (We don't need to check every single frame for a cut)
            scan_step = 5 
            
            for frame_num in range(0, total_frames, scan_step):
                if not self.is_running: break
                
                # Update progress bar occasionally
                if frame_num % 100 == 0:
                    current_percent = int(((idx) / total_files * 100) + (frame_num / total_frames * (100 / total_files)))
                    self.progress_signal.emit(current_percent)

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret: break
                
                current_time = frame_num / fps
                time_since_last = current_time - last_indexed_time
                
                # 1. ALWAYS CAPTURE if max interval exceeded (Long take protection)
                should_index = False
                curr_hist = self.calculate_histogram(frame)
                
                if time_since_last >= self.max_interval:
                    should_index = True
                    # self.log_signal.emit(f"   [Timed] {int(current_time)}s")
                
                # 2. CHECK SCENE CUT (if we are past min_interval)
                elif time_since_last >= self.min_interval:
                    if prev_hist is not None:
                        # Compare histograms (Correlation)
                        similarity = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
                        
                        # If similarity drops below threshold, the scene changed
                        if similarity < self.scene_threshold:
                            should_index = True
                            # self.log_signal.emit(f"   [Cut] {int(current_time)}s (Sim: {similarity:.2f})")
                    else:
                        should_index = True # Always index first valid frame

                if should_index:
                    # Queue for CLIP Analysis
                    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(img_rgb)
                    
                    frames_batch.append(pil_img)
                    timestamps_batch.append(current_time)
                    
                    # Update State
                    prev_hist = curr_hist
                    last_indexed_time = current_time

                    # Process Batch if full
                    if len(frames_batch) >= self.batch_size:
                        self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, model, processor, all_detected_indices)
                        frames_batch = []
                        timestamps_batch = []
            
            # Process remaining frames
            if frames_batch:
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, model, processor, all_detected_indices)
            
            cap.release()
            
            # --- GENERATE SUMMARY (Unchanged) ---
            if all_detected_indices:
                counts = Counter(all_detected_indices)
                top_common = counts.most_common(5) 
                summary_tags = [tag_list[i] for i, count in top_common]
                base_summary = f"Visuals: {', '.join(summary_tags)}"
            else:
                summary_tags = []
                base_summary = "No clear visual subjects"

            current_meta = db.get_video_metadata(video_path)
            transcript_data = current_meta.get("transcript", [])
            
            if transcript_data:
                text_preview = " ".join([t['text'] for t in transcript_data[:6]])
                summary_text = f"{base_summary}. Audio: {text_preview}..."
            else:
                summary_text = base_summary

            db.save_tags(video_path, summary_tags, summary_text)
            self.summary_signal.emit(video_path, summary_text)
        
        ai.unload_models()
        self.progress_signal.emit(100)
        self.finished_signal.emit()

    def process_batch(self, images, timestamps, ai, db, video_path, model, processor, all_detected_indices):
        try:
            inputs = processor(images=images, return_tensors="pt", padding=True).to(ai.device)
            with torch.no_grad():
                img_features = model.get_image_features(**inputs)
                img_features /= img_features.norm(p=2, dim=-1, keepdim=True)
                
                vectors_list = img_features.cpu().numpy().tolist()
                db.add_visual_embeddings(video_path, vectors_list, timestamps)
                
                similarity = (100.0 * img_features @ ai.tag_embeddings.T).softmax(dim=-1)
                top_vals, top_indices = similarity.topk(3, dim=-1)
                
                all_detected_indices.extend(top_indices.cpu().numpy().flatten())
                
        except Exception as e:
            print(f"Batch Error: {e}")

    def stop(self):
        self.is_running = False