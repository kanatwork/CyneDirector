# [FILE: workers/importer.py]
import os
from PyQt6.QtCore import QThread, pyqtSignal

class FolderImportWorker(QThread):
    progress_signal = pyqtSignal(str) # Emits current folder name being scanned
    finished_signal = pyqtSignal(list) # Emits the full list of found video files

    def __init__(self, folder_path):
        super().__init__()
        self.folder_path = folder_path
        # Extensions to look for
        self.valid_exts = {'.mp4', '.mov', '.mxf', '.braw', '.avi'}

    def run(self):
        found_files = []
        
        # Walk the directory tree
        for root, dirs, files in os.walk(self.folder_path):
            # Emit progress (just the folder name to keep UI clean)
            self.progress_signal.emit(f"Scanning: {os.path.basename(root)}")
            
            for file in files:
                if os.path.splitext(file)[1].lower() in self.valid_exts:
                    full_path = os.path.join(root, file)
                    found_files.append(full_path)
        
        self.finished_signal.emit(found_files)