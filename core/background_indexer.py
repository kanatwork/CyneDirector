# [FILE: core/background_indexer.py]
import os
import json
import time
from collections import deque
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from core.database import Database

class BackgroundIndexer(QObject):
    """
    Manages background indexing with incremental updates and priority queue.
    """
    indexing_started = pyqtSignal()
    indexing_progress = pyqtSignal(str, int)  # message, percent
    indexing_finished = pyqtSignal()
    file_indexed = pyqtSignal(str)  # video_path
    
    def __init__(self, project_path):
        super().__init__()
        self.project_path = project_path
        self.db = Database(project_path)
        
        # Priority queue: (priority, video_path, timestamp)
        # Higher priority = index sooner
        # Priority factors: file modification time (newer = higher), manual trigger
        self.index_queue = deque()
        self.is_indexing = False
        self.current_worker = None
        
        # Track indexed files to avoid duplicates
        self.indexed_files = set()
        
        # Timer for periodic background indexing
        self.background_timer = QTimer()
        self.background_timer.timeout.connect(self.process_queue)
        self.background_timer.setInterval(30000)  # Check every 30 seconds
        
        # Load indexed files
        self._load_indexed_files()
    
    def _load_indexed_files(self):
        """Load list of already indexed files."""
        index_file = os.path.join(self.project_path, "_cyne_db", "indexed_files.json")
        if os.path.exists(index_file):
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.indexed_files = set(data.get('files', []))
            except:
                self.indexed_files = set()
    
    def _save_indexed_files(self):
        """Save list of indexed files."""
        index_file = os.path.join(self.project_path, "_cyne_db", "indexed_files.json")
        os.makedirs(os.path.dirname(index_file), exist_ok=True)
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump({'files': list(self.indexed_files)}, f, indent=2)
        except:
            pass
    
    def add_file(self, video_path, priority=0, force=False):
        """
        Add file to indexing queue.
        
        Args:
            video_path: Path to video file
            priority: Priority (higher = index sooner). 0 = normal, 1 = high, 2 = urgent
            force: If True, re-index even if already indexed
        """
        if not os.path.exists(video_path):
            return
        
        # Check if already indexed (unless forced)
        if not force and video_path in self.indexed_files:
            # Check if file was modified since last index
            try:
                meta = self.db.get_video_metadata(video_path)
                last_scanned = meta.get('last_scanned', 0)
                file_mtime = os.path.getmtime(video_path)
                
                # Only re-index if file was modified after last scan
                if file_mtime <= last_scanned:
                    return
            except:
                pass
        
        # Calculate priority based on file modification time
        try:
            file_mtime = os.path.getmtime(video_path)
            # Newer files get higher priority
            time_priority = int(file_mtime)
        except:
            time_priority = 0
        
        # Combined priority: manual priority + time priority
        combined_priority = priority * 1000000 + time_priority
        
        # Add to queue (avoid duplicates)
        if not any(item[1] == video_path for item in self.index_queue):
            self.index_queue.append((combined_priority, video_path, time.time()))
            # Sort queue by priority (highest first)
            self.index_queue = deque(sorted(self.index_queue, key=lambda x: x[0], reverse=True))
    
    def add_files(self, video_paths, priority=0, force=False):
        """Add multiple files to indexing queue."""
        for path in video_paths:
            self.add_file(path, priority, force)
    
    def start_background_indexing(self):
        """Start background indexing timer."""
        if not self.background_timer.isActive():
            self.background_timer.start()
            # Process queue immediately
            QTimer.singleShot(1000, self.process_queue)
    
    def stop_background_indexing(self):
        """Stop background indexing timer."""
        self.background_timer.stop()
    
    def process_queue(self):
        """Process next item in indexing queue."""
        if self.is_indexing or not self.index_queue:
            return
        
        # Get highest priority item
        priority, video_path, _ = self.index_queue.popleft()
        
        # Check if file still exists
        if not os.path.exists(video_path):
            return
        
        # Start indexing this file
        self._index_file_incremental(video_path)
    
    def _index_file_incremental(self, video_path):
        """
        Index a single file incrementally (non-blocking).
        This creates a worker thread for the actual indexing.
        """
        self.is_indexing = True
        self.indexing_started.emit()
        
        from workers.indexer import IndexerWorker
        
        # Create worker for single file
        self.current_worker = IndexerWorker([video_path], self.project_path, mode="speed")
        self.current_worker.progress_signal.connect(
            lambda p: self.indexing_progress.emit(f"Indexing {os.path.basename(video_path)}", p)
        )
        self.current_worker.finished_signal.connect(self._on_file_indexed)
        self.current_worker.log_signal.connect(
            lambda msg: self.indexing_progress.emit(msg, -1)  # -1 = indeterminate progress
        )
        self.current_worker.start()
    
    def _on_file_indexed(self):
        """Handle completion of file indexing."""
        if self.current_worker:
            # Get the file that was indexed
            if hasattr(self.current_worker, 'file_paths') and self.current_worker.file_paths:
                video_path = self.current_worker.file_paths[0]
                self.indexed_files.add(video_path)
                self.file_indexed.emit(video_path)
        
        self.current_worker = None
        self.is_indexing = False
        self._save_indexed_files()
        
        # Continue processing queue
        if self.index_queue:
            QTimer.singleShot(1000, self.process_queue)
        else:
            self.indexing_finished.emit()
    
    def scan_for_new_files(self):
        """
        Scan project directory for new or modified files.
        Adds them to the indexing queue.
        """
        if not self.project_path:
            return
        
        video_extensions = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm', '.flv', '.wmv'}
        new_files = []
        
        for root, dirs, files in os.walk(self.project_path):
            # Skip database directory
            if "_cyne_db" in root:
                continue
            
            for file in files:
                _, ext = os.path.splitext(file.lower())
                if ext in video_extensions:
                    video_path = os.path.join(root, file)
                    
                    # Check if needs indexing
                    if video_path not in self.indexed_files:
                        new_files.append(video_path)
                    else:
                        # Check if modified
                        try:
                            meta = self.db.get_video_metadata(video_path)
                            last_scanned = meta.get('last_scanned', 0)
                            file_mtime = os.path.getmtime(video_path)
                            
                            if file_mtime > last_scanned:
                                new_files.append(video_path)
                        except:
                            # If metadata doesn't exist, re-index
                            new_files.append(video_path)
        
        # Add to queue with normal priority
        self.add_files(new_files, priority=0, force=False)
        
        return len(new_files)
    
    def get_queue_status(self):
        """Get current queue status."""
        return {
            'queue_size': len(self.index_queue),
            'is_indexing': self.is_indexing,
            'indexed_count': len(self.indexed_files)
        }





