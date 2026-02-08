# [FILE: core/workflow_manager.py]
from PyQt6.QtCore import QObject, pyqtSignal
from enum import Enum
from typing import List, Dict, Optional
from core.database import Database

class OperationType(Enum):
    INDEX_VISUALS = "index_visuals"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    TRANSLATE_AUDIO = "translate_audio"

class OperationStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class WorkflowOperation:
    """Represents a single operation in the workflow queue."""
    def __init__(self, op_type: OperationType, file_paths: List[str], priority: str = "normal"):
        self.op_type = op_type
        self.file_paths = file_paths
        self.status = OperationStatus.PENDING
        self.progress = 0
        self.current_file = None
        self.error_message = None
        self.priority = priority  # "high", "normal", "low"
        self.is_paused = False

class WorkflowManager(QObject):
    """
    Manages workflow queue and sequential processing of operations.
    Handles smart detection of what's needed per file.
    """
    # Signals
    operation_started = pyqtSignal(OperationType, list)  # op_type, file_paths
    operation_progress = pyqtSignal(OperationType, int, str)  # op_type, progress, current_file
    operation_finished = pyqtSignal(OperationType, bool, str)  # op_type, success, error_msg
    workflow_started = pyqtSignal()
    workflow_finished = pyqtSignal()
    workflow_paused = pyqtSignal()
    workflow_resumed = pyqtSignal()
    
    def __init__(self, project_path: str):
        super().__init__()
        self.project_path = project_path
        self.queue: List[WorkflowOperation] = []
        self.current_operation: Optional[WorkflowOperation] = None
        self.is_running = False
        self.is_paused = False
        self.current_mode = "speed"  # Default mode: "speed" or "accuracy"
        self.db = Database()
        if not self.db.project_path:
            self.db.initialize(project_path)
    
    def add_operation(self, op_type: OperationType, file_paths: List[str], 
                     smart_filter: bool = True, priority: str = "normal") -> bool:
        """
        Add an operation to the queue.
        
        Args:
            op_type: Type of operation to add
            file_paths: List of file paths to process
            smart_filter: If True, filter out files that already have this data
            priority: Priority level ("high", "normal", "low")
        
        Returns:
            True if operation was added, False if all files were filtered out
        """
        if not file_paths:
            return False
        
        # Smart filtering: remove files that already have this data
        if smart_filter:
            filtered_paths = self._filter_files_needing_operation(op_type, file_paths)
            if not filtered_paths:
                return False
            file_paths = filtered_paths
        
        operation = WorkflowOperation(op_type, file_paths, priority)
        
        # Insert based on priority (high first, then normal, then low)
        if priority == "high":
            # Insert at beginning, but after other high priority items
            insert_index = 0
            for i, op in enumerate(self.queue):
                if op.priority != "high":
                    insert_index = i
                    break
                insert_index = i + 1
            self.queue.insert(insert_index, operation)
        elif priority == "low":
            # Insert at end, but before other low priority items
            insert_index = len(self.queue)
            for i in range(len(self.queue) - 1, -1, -1):
                if self.queue[i].priority != "low":
                    insert_index = i + 1
                    break
            self.queue.insert(insert_index, operation)
        else:
            # Normal priority - insert after high, before low
            insert_index = 0
            for i, op in enumerate(self.queue):
                if op.priority == "low":
                    insert_index = i
                    break
                insert_index = i + 1
            self.queue.insert(insert_index, operation)
        
        return True
    
    def _filter_files_needing_operation(self, op_type: OperationType, 
                                        file_paths: List[str]) -> List[str]:
        """Filter files to only include those that need this operation.
        Uses incremental indexing: only re-indexes files that have been modified
        since last scan or don't have the required data."""
        import os
        filtered = []
        
        for path in file_paths:
            if not os.path.exists(path):
                continue
                
            meta = self.db.get_video_metadata(path)
            
            # Check if file was modified since last scan
            try:
                file_mtime = os.path.getmtime(path)
                last_scanned = meta.get('last_scanned', 0)
                file_modified = file_mtime > last_scanned if last_scanned > 0 else True
            except OSError:
                file_modified = True  # If we can't get mtime, assume modified
            
            if op_type == OperationType.INDEX_VISUALS:
                # Need indexing if: no tags OR file was modified since last scan
                if not meta.get('tags') or file_modified:
                    filtered.append(path)
            elif op_type == OperationType.TRANSCRIBE_AUDIO:
                # Need transcription if: no transcript OR file was modified since last scan
                if not meta.get('transcript') or file_modified:
                    filtered.append(path)
            elif op_type == OperationType.TRANSLATE_AUDIO:
                # Need translation if: has transcript but no translation OR file was modified since last translation
                has_transcript = bool(meta.get('transcript'))
                has_translation = bool(meta.get('transcript_translated'))
                # Check if translation was done after last file modification
                translation_timestamp = meta.get('translation_timestamp', 0)
                translation_outdated = file_mtime > translation_timestamp if translation_timestamp > 0 else True
                
                if has_transcript and (not has_translation or translation_outdated):
                    filtered.append(path)
        
        return filtered
    
    def remove_operation(self, index: int) -> bool:
        """Remove an operation from the queue by index."""
        if 0 <= index < len(self.queue):
            # Don't allow removing the current operation
            if self.queue[index] == self.current_operation:
                return False
            self.queue.pop(index)
            return True
        return False
    
    def clear_queue(self):
        """Clear all pending operations from the queue."""
        # Only clear pending operations, not the current one
        self.queue = [op for op in self.queue if op == self.current_operation]
        if not self.is_running:
            self.queue = []
    
    def reorder_operation(self, from_index: int, to_index: int) -> bool:
        """Reorder operations in the queue."""
        if (0 <= from_index < len(self.queue) and 
            0 <= to_index < len(self.queue) and
            from_index != to_index):
            # Don't allow reordering the current operation
            if self.queue[from_index] == self.current_operation:
                return False
            
            op = self.queue.pop(from_index)
            self.queue.insert(to_index, op)
            return True
        return False
    
    def get_queue_status(self) -> List[Dict]:
        """Get current queue status for UI display."""
        status_list = []
        for i, op in enumerate(self.queue):
            # Calculate ETR (Estimated Time Remaining) if available
            etr_seconds = None
            if op == self.current_operation and op.progress > 0 and op.progress < 100:
                # Simple linear estimation
                elapsed_estimate = op.progress / 100.0  # Assume 100% = 1 unit of time
                if elapsed_estimate > 0:
                    total_estimate = 1.0 / elapsed_estimate
                    remaining = total_estimate - 1.0
                    etr_seconds = max(0, int(remaining * 60))  # Convert to seconds (rough estimate)
            
            status_list.append({
                'index': i,
                'type': op.op_type.value,
                'type_display': op.op_type.value.replace('_', ' ').title(),
                'file_count': len(op.file_paths),
                'status': op.status.value,
                'progress': op.progress,
                'current_file': op.current_file,
                'is_current': (op == self.current_operation),
                'etr_seconds': etr_seconds,
                'priority': op.priority,
                'is_paused': op.is_paused
            })
        return status_list
    
    def pause_operation(self, index: int) -> bool:
        """Pause a specific operation by index."""
        if 0 <= index < len(self.queue):
            op = self.queue[index]
            if op.status == OperationStatus.RUNNING:
                op.is_paused = True
                return True
            elif op.status == OperationStatus.PENDING:
                op.is_paused = True
                return True
        return False
    
    def resume_operation(self, index: int) -> bool:
        """Resume a paused operation by index."""
        if 0 <= index < len(self.queue):
            op = self.queue[index]
            if op.is_paused:
                op.is_paused = False
                # If workflow is running and this was the current operation, continue
                if self.is_running and op == self.current_operation:
                    self._process_next()
                return True
        return False
    
    def set_operation_priority(self, index: int, priority: str) -> bool:
        """Set priority for an operation."""
        if 0 <= index < len(self.queue) and priority in ["high", "normal", "low"]:
            op = self.queue[index]
            if op.status == OperationStatus.PENDING:
                op.priority = priority
                # Reorder queue based on new priority
                self._reorder_by_priority()
                return True
        return False
    
    def _reorder_by_priority(self):
        """Reorder queue by priority (high -> normal -> low)."""
        high_ops = [op for op in self.queue if op.priority == "high"]
        normal_ops = [op for op in self.queue if op.priority == "normal"]
        low_ops = [op for op in self.queue if op.priority == "low"]
        self.queue = high_ops + normal_ops + low_ops
    
    def start_workflow(self):
        """Start processing the workflow queue."""
        if self.is_running:
            return
        
        if not self.queue:
            return
        
        self.is_running = True
        self.is_paused = False
        self.workflow_started.emit()
        self._process_next()
    
    def pause_workflow(self):
        """Pause the current workflow."""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.workflow_paused.emit()
    
    def resume_workflow(self):
        """Resume a paused workflow."""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.workflow_resumed.emit()
            # Continue processing
            if self.current_operation:
                # Signal the worker to continue (workers handle pause internally)
                pass
    
    def cancel_workflow(self):
        """Cancel the current workflow and clear queue."""
        self.is_running = False
        self.is_paused = False
        if self.current_operation:
            self.current_operation.status = OperationStatus.CANCELLED
        self.queue = []
        self.current_operation = None
    
    def _process_next(self):
        """Process the next operation in the queue."""
        if not self.is_running or self.is_paused:
            return
        
        # Find next pending operation (skip paused ones)
        next_op = None
        for op in self.queue:
            if op.status == OperationStatus.PENDING and not op.is_paused:
                next_op = op
                break
        
        if not next_op:
            # No more operations
            self.is_running = False
            self.workflow_finished.emit()
            return
        
        self.current_operation = next_op
        self.current_operation.status = OperationStatus.RUNNING
        self.operation_started.emit(next_op.op_type, next_op.file_paths)
    
    def on_operation_progress(self, op_type: OperationType, progress: int, 
                             current_file: Optional[str] = None):
        """Update progress for the current operation."""
        if self.current_operation and self.current_operation.op_type == op_type:
            self.current_operation.progress = progress
            self.current_operation.current_file = current_file
            self.operation_progress.emit(op_type, progress, current_file or "")
    
    def on_operation_finished(self, op_type: OperationType, success: bool, 
                             error_msg: Optional[str] = None):
        """Mark the current operation as finished and process next."""
        if self.current_operation and self.current_operation.op_type == op_type:
            if success:
                self.current_operation.status = OperationStatus.COMPLETED
                self.current_operation.progress = 100
            else:
                self.current_operation.status = OperationStatus.FAILED
                self.current_operation.error_message = error_msg
            
            self.operation_finished.emit(op_type, success, error_msg or "")
            self.current_operation = None
            
            # Process next operation
            if self.is_running:
                self._process_next()
    
    def get_files_needing_operations(self, file_paths: List[str]) -> Dict[OperationType, List[str]]:
        """
        Smart detection: returns which files need which operations.
        Uses incremental indexing: checks file modification times.
        Useful for UI to show what operations are needed.
        """
        import os
        result = {
            OperationType.INDEX_VISUALS: [],
            OperationType.TRANSCRIBE_AUDIO: [],
            OperationType.TRANSLATE_AUDIO: []
        }
        
        for path in file_paths:
            if not os.path.exists(path):
                continue
                
            meta = self.db.get_video_metadata(path)
            
            # Check if file was modified since last scan
            try:
                file_mtime = os.path.getmtime(path)
                last_scanned = meta.get('last_scanned', 0)
                file_modified = file_mtime > last_scanned if last_scanned > 0 else True
            except OSError:
                file_modified = True  # If we can't get mtime, assume modified
            
            # Need indexing if: no tags OR file was modified
            if not meta.get('tags') or file_modified:
                result[OperationType.INDEX_VISUALS].append(path)
            
            # Need transcription if: no transcript OR file was modified
            if not meta.get('transcript') or file_modified:
                result[OperationType.TRANSCRIBE_AUDIO].append(path)
            
            # Need translation if: has transcript but no translation OR translation is outdated
            has_transcript = bool(meta.get('transcript'))
            has_translation = bool(meta.get('transcript_translated'))
            translation_timestamp = meta.get('translation_timestamp', 0)
            translation_outdated = file_mtime > translation_timestamp if translation_timestamp > 0 else True
            
            if has_transcript and (not has_translation or translation_outdated):
                result[OperationType.TRANSLATE_AUDIO].append(path)
        
        return result


