import os
import cv2
import torch
import numpy as np
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
        
        self.face_db = FaceDB(project_path)
        self.db = Database(project_path)
        
        # Load known data
        self.known_encodings = self.face_db.known_encodings
        self.known_ids = self.face_db.known_ids

        # Threshold for Cosine Similarity (0.6 is standard for Facenet)
        self.match_threshold = 0.6

    def run(self):
        if not HAS_FACENET:
            self.log_signal.emit("❌ CRITICAL: 'facenet-pytorch' missing.")
            self.log_signal.emit("   ➜ Run: pip install facenet-pytorch")
            self.finished_signal.emit()
            return

        # 1. SETUP AI MODELS
        device = AIBackend().device
        self.log_signal.emit(f"🚀 Loading Face Models on {device.upper()}...")

        try:
            # MTCNN for Detection (keep_all=True finds all faces)
            mtcnn = MTCNN(keep_all=True, device=device, min_face_size=40)
            
            # InceptionResnetV1 for Embeddings (pretrained on vggface2)
            resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
        except Exception as e:
            self.log_signal.emit(f"Model Load Error: {e}")
            self.finished_signal.emit()
            return

        # 2. PREPARE WORKLOAD
        total_files = len(self.file_paths)
        
        # Check for DB Version Mismatch (Dlib uses 128D, Facenet uses 512D)
        if self.known_encodings:
            if len(self.known_encodings[0]) == 128:
                self.log_signal.emit("⚠️ Database mismatch (Dlib detected). Clearing old face DB...")
                # In a production app, we might migrate. For now, we reset to prevent crashes.
                self.known_encodings = []
                self.known_ids = []
                # (Optional: You could trigger self.face_db.clear() here)

        for idx, video_path in enumerate(self.file_paths):
            if not self.is_running: break
            
            filename = os.path.basename(video_path)
            self.log_signal.emit(f"Scanning: {filename}")
            
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened(): continue

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Optimization: Scan 1 frame every 1.5 seconds (Balance speed/accuracy)
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
                    # A. DETECT FACES (Get bounding boxes)
                    boxes, _ = mtcnn.detect(pil_img)
                    
                    if boxes is not None:
                        # B. EXTRACT TENSORS (Pre-processed for Resnet)
                        # mtcnn.extract returns a tensor of shape [N, 3, 160, 160]
                        face_tensors = mtcnn.extract(pil_img, boxes, save_path=None)
                        
                        if face_tensors is not None:
                            # C. GENERATE EMBEDDINGS (Batch process on GPU)
                            face_tensors = face_tensors.to(device)
                            with torch.no_grad():
                                embeddings = resnet(face_tensors).detach().cpu().numpy()

                            # D. COMPARE & IDENTIFY
                            for i, embedding in enumerate(embeddings):
                                box = boxes[i]
                                
                                # Find best match
                                match_id = None
                                min_dist = 100.0 # Arbitrary high start
                                
                                if self.known_encodings:
                                    # Calculate Euclidean distances to all known faces
                                    # (Facenet embeddings are roughly normalized)
                                    dists = np.linalg.norm(self.known_encodings - embedding, axis=1)
                                    min_index = np.argmin(dists)
                                    min_dist = dists[min_index]
                                    
                                    if min_dist < self.match_threshold:
                                        match_id = self.known_ids[min_index]

                                # Logic: New Person or Known?
                                if match_id is None:
                                    match_id = self.face_db.get_next_id()
                                    self.face_db.add_face(match_id, embedding)
                                    
                                    # Update local cache
                                    self.known_encodings.append(embedding)
                                    self.known_ids.append(match_id)
                                    
                                    # Generate Thumbnail from Original Image (Not the whitened tensor)
                                    x1, y1, x2, y2 = [int(b) for b in box]
                                    # Clamp to image bounds
                                    h_img, w_img = img_rgb.shape[:2]
                                    x1, y1 = max(0, x1), max(0, y1)
                                    x2, y2 = min(w_img, x2), min(h_img, y2)
                                    
                                    if x2 > x1 and y2 > y1:
                                        face_crop = img_rgb[y1:y2, x1:x2]
                                        face_crop = np.ascontiguousarray(face_crop)
                                        
                                        # Save thumbnail to disk
                                        thumb_path = os.path.join(self.face_db.db_dir, f"{match_id}.jpg")
                                        cv2.imwrite(thumb_path, cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR))
                                        
                                        # Send to UI
                                        h_f, w_f, ch_f = face_crop.shape
                                        bpl = ch_f * w_f
                                        q_img = QImage(face_crop.data, w_f, h_f, bpl, QImage.Format.Format_RGB888).copy()
                                        self.new_face_signal.emit(match_id, match_id, q_img)

                                unique_faces_in_file.add(match_id)

                except Exception as e:
                    pass # Skip frame on error

                # Progress Update
                percent = int((frame_num / total_frames) * 100)
                # (Optional: emit percent if you want granular progress)

            cap.release()

            # Save results for this file
            if unique_faces_in_file:
                found_ids = list(unique_faces_in_file)
                self.db.update_metadata_key(video_path, "faces", found_ids)
                self.face_count_signal.emit(video_path, len(unique_faces_in_file))
            
            # Global Progress
            global_prog = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(global_prog)

        self.log_signal.emit("Face Scan Complete.")
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False