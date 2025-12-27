# [FILE: workers/transcriber.py]
import os
import json
from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_models import AIBackend
from core.database import Database

class TranscriberWorker(QThread):
    # Signals matching MainWindow requirements
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
        
        # 1. Load the shared AI Backend
        # This respects the hardware detection logic we fixed in ai_models.py
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            # 
            # Loads Faster-Whisper (Large-v3) with FP16 optimization
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
                # 2. Transcribe with VAD (Voice Activity Detection)
                # vad_filter=True skips silence, speeding up processing significantly.
                segments, info = model.transcribe(
                    video_path, 
                    beam_size=5, 
                    vad_filter=True, 
                    vad_parameters=dict(min_silence_duration_ms=500)
                )
                
                segment_list = []
                full_text = ""
                
                # Convert generator to list
                for segment in segments:
                    if not self.is_running: break
                    
                    text = segment.text.strip()
                    if not text: continue

                    segment_list.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": text
                    })
                    full_text += text + " "

                if not self.is_running: break

                # 3. Save Transcript to Database
                db.save_transcript(video_path, segment_list)
                
                # 4. Smart Summary Update
                # If we already have a Visual summary, we APPEND the audio context
                # instead of ignoring it or overwriting it.
                current_meta = db.get_video_metadata(video_path)
                existing_summary = current_meta.get("summary", "")
                
                audio_preview = (full_text[:100] + "...") if len(full_text) > 100 else full_text
                
                if audio_preview:
                    if existing_summary:
                        # Don't duplicate if already there
                        if "Audio:" not in existing_summary:
                            new_summary = f"{existing_summary} | Audio: \"{audio_preview}\""
                            db.save_summary(video_path, new_summary)
                    else:
                        db.save_summary(video_path, f"Audio: \"{audio_preview}\"")

                # Tell UI this file is done (Adds Green Checkmark)
                self.file_finished_signal.emit(video_path)

            except Exception as e:
                self.log_signal.emit(f"Error on {filename}: {str(e)}")

            # Update progress bar
            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        # 5. Cleanup Resources
        # Critical: Release VRAM so the user can switch to Visual Search/Indexing immediately
        ai.unload_models()
        
        self.log_signal.emit("Transcription Complete.")
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False