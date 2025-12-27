# [FILE: face_scanner.py]
import os
import cv2
import torch
import numpy as np
import gc
from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
from core.face_db import FaceDB
from core.database import Database
from core.ai_models import AIBackend

# Safe Import for Facenet
try:
    from facenet_pytorch import MTCNN, InceptionResnetV1
    HAS_FACENET = True
except ImportError:
    HAS_FACENET = False

class FaceScannerWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    new_face_signal = pyqtSignal(str, str, object) 
    face_count_signal = pyqtSignal(str, int)       
    finished_signal = pyqtSignal()

    def __init__(self, file_paths, project_path):
        super().__init__()
        self.file_paths = file_paths
        self.project_path = project_path
        self.is_running = True
        
        # Thread-safe Face Database
        self.face_db = FaceDB(project_path)
        self.db = Database(project_path)
        
        self.match_threshold = 0.6

    def run(self):
        if not HAS_FACENET:
            self.log_signal.emit("❌ CRITICAL: 'facenet-pytorch' missing.")
            self.log_signal.emit("   ➜ Run: pip install facenet-pytorch")
            self.finished_signal.emit()
            return

        # 1. SETUP AI MODELS (Using Singleton Device)
        ai = AIBackend()
        device = ai.device # Use the safe device detected by AIBackend
        
        self.log_signal.emit(f"🚀 Loading Face Models on {device.upper()}...")

        try:
            # MTCNN: Face Detection
            # keep_all=True finds all faces in the frame
            # min_face_size=40 speeds up detection by ignoring tiny background faces
            mtcnn = MTCNN(keep_all=True, device=device, min_face_size=40)
            
            # InceptionResnetV1: Face Recognition (Embeddings)
            # pretrained='vggface2' is standard for generic face recognition
            resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
            
        except Exception as e:
            self.log_signal.emit(f"Model Load Error: {e}")
            self.finished_signal.emit()
            return

        # 2. PREPARE WORKLOAD
        total_files = len(self.file_paths)
        
        for idx, video_path in enumerate(self.file_paths):
            if not self.is_running: break
            
            filename = os.path.basename(video_path)
            self.log_signal.emit(f"Scanning: {filename}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Optimization: Scan 1 frame every 1.5 seconds
            # This is a sweet spot: enough to catch actors entering, but fast enough to scan movies.
            step = int(fps * 1.5) if fps > 0 else 30
            
            unique_faces_in_file = set()
            
            for frame_num in range(0, total_frames, step):
                if not self.is_running: break
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret: break

                # Convert to RGB (PIL) for Facenet
                img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img_rgb)

                try:
                    # A. DETECT FACES 
                    boxes, _ = mtcnn.detect(pil_img)
                    
                    if boxes is not None:
                        # B. EXTRACT TENSORS
                        # Note: We must carefully manage tensors to avoid VRAM leaks
                        face_tensors = mtcnn.extract(pil_img, boxes, save_path=None)
                        
                        if face_tensors is not None:
                            face_tensors = face_tensors.to(device)
                            
                            with torch.no_grad():
                                # C. GENERATE EMBEDDINGS (512-dim vector)
                                embeddings = resnet(face_tensors).detach().cpu().numpy()
                            
                            # Clean up VRAM immediately
                            del face_tensors

                            # D. COMPARE & IDENTIFY
                            for i, embedding in enumerate(embeddings):
                                box = boxes[i]
                                
                                # Use FaceDB to find if we know this person
                                match_id, dist = self.face_db.find_match(embedding, self.match_threshold)

                                # If NEW person, register them
                                if match_id is None:
                                    match_id = self.face_db.get_next_id()
                                    self.face_db.add_face(match_id, embedding)
                                    
                                    # --- Thumbnail Generation ---
                                    x1, y1, x2, y2 = [int(b) for b in box]
                                    h_img, w_img = img_rgb.shape[:2]
                                    
                                    # Padding to make the crop look better
                                    pad_x = int((x2 - x1) * 0.1)
                                    pad_y = int((y2 - y1) * 0.1)
                                    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
                                    x2, y2 = min(w_img, x2 + pad_x), min(h_img, y2 + pad_y)
                                    
                                    if x2 > x1 and y2 > y1:
                                        face_crop = img_rgb[y1:y2, x1:x2]
                                        face_crop = np.ascontiguousarray(face_crop)
                                        
                                        # Save to disk
                                        thumb_path = os.path.join(self.face_db.db_dir, f"{match_id}.jpg")
                                        cv2.imwrite(thumb_path, cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR))
                                        
                                        # Update UI
                                        h_f, w_f, ch_f = face_crop.shape
                                        bpl = ch_f * w_f
                                        q_img = QImage(face_crop.data, w_f, h_f, bpl, QImage.Format.Format_RGB888).copy()
                                        self.new_face_signal.emit(match_id, match_id, q_img)

                                unique_faces_in_file.add(match_id)

                except Exception as e:
                    # MTCNN occasional failure on blurry frames is expected
                    pass 

                # Memory Leak Protection for long loops
                if frame_num % 100 == 0:
                    gc.collect()

            cap.release()

            # Save Results
            if unique_faces_in_file:
                found_ids = list(unique_faces_in_file)
                self.db.update_metadata_key(video_path, "faces", found_ids)
                self.face_count_signal.emit(video_path, len(unique_faces_in_file))
            
            # Global Progress
            global_prog = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(global_prog)

        # Cleanup Models & VRAM
        del mtcnn
        del resnet
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        self.log_signal.emit("Face Scan Complete.")
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False