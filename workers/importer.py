# [FILE: workers/importer.py]
import os
from PyQt6.QtCore import QThread, pyqtSignal

class FolderImportWorker(QThread):
    progress_signal = pyqtSignal(str) # Emits current folder name
    finished_signal = pyqtSignal(list) # Emits result list

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
        self.is_running = True
        # Expanded extension list
        self.valid_exts = {'.mp4', '.mov', '.mxf', '.braw', '.avi', '.mkv', '.webm', '.ts'}

    def run(self):
        found_files = []
        
        # topdown=True allows us to modify 'dirs' in-place to skip subdirectories
        for root, dirs, files in os.walk(self.folder_path, topdown=True):
            if not self.is_running: break
            
            # --- OPTIMIZATION: SKIP HIDDEN & SYSTEM FOLDERS ---
            # Modifying 'dirs' in-place prevents os.walk from visiting them.
            # We filter out folders starting with '.' (hidden) or the app's own DB folder
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != "_cyne_db"]
            
            self.progress_signal.emit(f"Scanning: {os.path.basename(root)}")
            
            for file in files:
                if not self.is_running: break
                
                # Check extension (case-insensitive)
                if os.path.splitext(file)[1].lower() in self.valid_exts:
                    full_path = os.path.normpath(os.path.join(root, file))
                    found_files.append(full_path)
        
        self.finished_signal.emit(found_files)

    def stop(self):
        """Stops the worker immediately."""
        self.is_running = False