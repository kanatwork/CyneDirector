import os
import cv2
import face_recognition
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
from core.face_db import FaceDB
from core.database import Database
from core.ai_models import AIBackend

def sanitize_image(image):
    if image is None: return None
    if not image.flags['C_CONTIGUOUS']:
        image = np.ascontiguousarray(image)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

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
        
        self.known_encodings = self.face_db.known_encodings
        self.known_ids = self.face_db.known_ids
        
        # --- SMART MODEL SELECTION (Crash Fix) ---
        # Default to CPU (Safe)
        self.model_type = "hog" 
        
        # Only try CNN if we are sure dlib supports it
        if AIBackend().device == "cuda":
            try:
                import dlib
                if dlib.DLIB_USE_CUDA:
                    self.model_type = "cnn"
                    print("✅ CUDA Detected & Dlib supports it. Using CNN.")
                else:
                    print("⚠️ CUDA available but Dlib not compiled with it. Using HOG.")
            except ImportError:
                print("⚠️ Dlib not found directly. Using HOG.")
                self.model_type = "hog"

    def run(self):
        self.log_signal.emit(f"Loaded {len(self.known_ids)} known faces.")
        self.log_signal.emit(f"Using Detection Model: {self.model_type.upper()}")
        
        file_steps = []
        total_steps_global = 0
        
        for video_path in self.file_paths:
            if not self.is_running: break
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                step = int(fps * 0.8) if fps > 0 else 30 # Slightly slower scan for accuracy
                if frames > 0:
                    steps = frames // step
                    file_steps.append((video_path, step, frames))
                    total_steps_global += steps
            cap.release()
            
        if total_steps_global == 0:
            self.finished_signal.emit()
            return

        current_step_global = 0
        faces_dir = self.face_db.db_dir 

        for (video_path, step, total_frames) in file_steps:
            if not self.is_running: break
            
            self.log_signal.emit(f"Scanning: {os.path.basename(video_path)}")
            cap = cv2.VideoCapture(video_path)
            unique_faces_in_file = set() 
            
            for i in range(0, total_frames, step):
                if not self.is_running: break
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if not ret or frame is None: continue
                
                try:
                    h, w = frame.shape[:2]
                    if w > 1080:
                        scale = 1080 / w
                        frame = cv2.resize(frame, (0,0), fx=scale, fy=scale)
                    
                    clean_image = sanitize_image(frame)

                    # Use selected model type
                    face_locations = face_recognition.face_locations(clean_image, model=self.model_type)
                    
                    if face_locations:
                        face_encodings = face_recognition.face_encodings(clean_image, face_locations)
                        
                        for (top, right, bottom, left), encoding in zip(face_locations, face_encodings):
                            matches = face_recognition.compare_faces(self.known_encodings, encoding, tolerance=0.55)
                            person_id = None
                            
                            if True in matches:
                                first_match_index = matches.index(True)
                                person_id = self.known_ids[first_match_index]
                            else:
                                person_id = self.face_db.get_next_id()
                                self.face_db.add_face(person_id, encoding)
                                self.known_encodings = self.face_db.known_encodings
                                self.known_ids = self.face_db.known_ids
                    
                                face_slice = clean_image[top:bottom, left:right]
                                face_slice = np.ascontiguousarray(face_slice)
                                
                                thumb_path = os.path.join(faces_dir, f"{person_id}.jpg")
                                cv2.imwrite(thumb_path, cv2.cvtColor(face_slice, cv2.COLOR_RGB2BGR))
                                
                                h_f, w_f, ch_f = face_slice.shape
                                bytes_per_line = ch_f * w_f
                                q_img = QImage(face_slice.data.tobytes(), w_f, h_f, bytes_per_line, QImage.Format.Format_RGB888).copy()
                                
                                self.new_face_signal.emit(person_id, person_id, q_img)
                            
                            unique_faces_in_file.add(person_id)

                except Exception as e:
                    pass 

                current_step_global += 1
                percent = int((current_step_global / total_steps_global) * 100)
                self.progress_signal.emit(percent)
            
            cap.release()
            
            if unique_faces_in_file:
                found_ids = list(unique_faces_in_file)
                self.db.update_metadata_key(video_path, "faces", found_ids)
                self.log_signal.emit(f"   Saved {len(found_ids)} faces to metadata.")

            self.face_count_signal.emit(video_path, len(unique_faces_in_file))
            
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False