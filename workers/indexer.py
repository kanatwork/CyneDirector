from PyQt6.QtCore import QThread, pyqtSignal
import cv2
import torch
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
        self.batch_size = 32 

    def run(self):
        # NEW: Instant feedback for user
        self.progress_signal.emit(1)
        self.log_signal.emit("Initializing AI Core...")
        
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
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            step = int(fps * 1.5) if fps > 0 else 30
            
            frames_batch = []
            timestamps_batch = []
            all_detected_indices = []
            
            for frame_num in range(0, total_frames, step):
                if not self.is_running: break
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret: break
                
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img)
                
                frames_batch.append(pil_img)
                timestamps_batch.append(frame_num / fps if fps > 0 else 0)
                
                if len(frames_batch) >= self.batch_size:
                    self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, model, processor, all_detected_indices)
                    frames_batch = []
                    timestamps_batch = []
                
                current_percent = int(((idx) / total_files * 100) + (frame_num / total_frames * (100 / total_files)))
                self.progress_signal.emit(current_percent)
            
            if frames_batch:
                self.process_batch(frames_batch, timestamps_batch, ai, db, video_path, model, processor, all_detected_indices)
            
            cap.release()
            
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