import os
import json
from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_models import AIBackend
from core.database import Database

class TranscriberWorker(QThread):
    # These signals are REQUIRED by your main_window.py
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()
    file_finished_signal = pyqtSignal(str)

    def __init__(self, file_paths, project_path):
        super().__init__()
        self.file_paths = file_paths
        self.project_path = project_path
        self.is_running = True

    def run(self):
        self.log_signal.emit("Initializing Whisper AI...")
        
        # 1. Reuse the model already loaded in memory (Saves VRAM)
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            # This loads the optimized 'faster-whisper' model
            model = ai.load_whisper()
        except Exception as e:
            self.log_signal.emit(f"CRITICAL: Audio Model Failed - {e}")
            self.finished_signal.emit()
            return

        total_files = len(self.file_paths)
        
        for idx, video_path in enumerate(self.file_paths):
            if not self.is_running: break
            
            filename = os.path.basename(video_path)
            self.log_signal.emit(f"Transcribing: {filename}")
            
            try:
                # 2. Transcribe using faster-whisper
                # This is much faster than the standard 'whisper' library
                segments, info = model.transcribe(video_path, beam_size=5)
                
                segment_list = []
                full_text = ""
                
                # Convert generator to list
                for segment in segments:
                    if not self.is_running: break
                    segment_list.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text.strip()
                    })
                    full_text += segment.text + " "

                if not self.is_running: break

                # 3. Save to Database
                db.save_transcript(video_path, segment_list)
                
                # Update Summary
                current_meta = db.get_video_metadata(video_path)
                if "summary" not in current_meta or not current_meta["summary"]:
                    preview = (full_text[:100] + "...") if len(full_text) > 100 else full_text
                    db.save_summary(video_path, f"Audio: {preview}")

                # Tell UI this file is done (Adds Green Checkmark)
                self.file_finished_signal.emit(video_path)

            except Exception as e:
                self.log_signal.emit(f"Error on {filename}: {str(e)}")

            # Update progress bar
            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        self.log_signal.emit("Transcription Complete.")
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False