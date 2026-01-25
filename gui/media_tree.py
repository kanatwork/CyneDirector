# [FILE: gui/media_tree.py]
import os
import json
import time
import cv2
import hashlib
from PyQt6.QtWidgets import (QTreeWidget, QTreeWidgetItem, QAbstractItemView, 
                             QHeaderView, QMenu, QCheckBox, QWidget, QHBoxLayout,
                             QStyledItemDelegate, QStyleOptionViewItem)
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QThreadPool, QObject, QSize, QThread, QRect, QModelIndex
from PyQt6.QtGui import (QColor, QBrush, QDragEnterEvent, QDropEvent, QImage, 
                        QPixmap, QPainter, QIcon)
from config import COLORS
from core.media_engine import MediaEngine 

# --- WORKER SIGNALS ---
class WorkerSignals(QObject):
    finished = pyqtSignal(str, str, str, str, dict, str, str) # path, res, fps, dur, status, summary, shot_type

class ThumbnailSignals(QObject):
    thumbnail_ready = pyqtSignal(str, QImage)  # path, thumbnail image

# --- PARALLEL WORKER ---
class MediaLoaderWorker(QRunnable):
    """
    Runs in a thread pool to load metadata for ONE file at a time.
    This allows multiple files to be processed in parallel.
    """
    def __init__(self, file_path):
        super().__init__()
        self.path = file_path
        self.signals = WorkerSignals()

    def run(self):
        try:
            # 1. Get Technical Metadata (Resolution, FPS, Duration)
            # MediaEngine.get_metadata should satisfy: w, h, fps, duration_sec
            w, h, fps, dur_sec = MediaEngine.get_metadata(self.path)
            
            res_str = f"{w}x{h}" if w > 0 else "Unknown"
            fps_str = f"{fps:.2f}" if fps > 0 else "--"
            
            # Format Duration
            if dur_sec > 0:
                m, s = divmod(dur_sec, 60)
                h_dur, m = divmod(m, 60)
                if h_dur > 0:
                    dur_str = f"{int(h_dur)}:{int(m):02}:{int(s):02}"
                else:
                    dur_str = f"{int(m):02}:{int(s):02}"
            else:
                dur_str = "--:--"

            # 2. Check for Existing JSON Sidecar Data (legacy) or Database
            status = {'visuals': False, 'audio': False, 'translation': False}
            summary_str = ""
            shot_type_str = ""
            
            # Try database first (new system)
            try:
                from core.database import Database
                db = Database()
                if db.project_path:
                    data = db.get_video_metadata(self.path)
                    if data.get("tags"): status['visuals'] = True
                    if data.get("transcript"): status['audio'] = True
                    if data.get("transcript_translated"): status['translation'] = True
                    summary_str = data.get("summary", "")
                    shot_type_str = data.get("shot_type", "")
            except:
                pass
            
            # Fallback to JSON sidecar (legacy)
            if not summary_str:
                json_path = f"{self.path}.json"
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if data.get("tags"): status['visuals'] = True
                            if data.get("transcript"): status['audio'] = True
                            if data.get("transcript_translated"): status['translation'] = True
                            summary_str = data.get("summary", "")
                            shot_type_str = data.get("shot_type", "")
                    except:
                        pass

            # 3. Emit Results (include translation status)
            self.signals.finished.emit(self.path, res_str, fps_str, dur_str, status, summary_str, shot_type_str)

        except Exception as e:
            # On generic failure, emit safe defaults
            self.signals.finished.emit(self.path, "Error", "--", "--:--", 
                                         {'visuals': False, 'audio': False, 'translation': False}, "", "")

# --- THUMBNAIL WORKER ---
class ThumbnailWorker(QRunnable):
    """Worker to generate thumbnails for video files."""
    def __init__(self, file_path, project_path, timestamp=0):
        super().__init__()
        self.path = file_path
        self.project_path = project_path
        self.timestamp = timestamp
        self.signals = ThumbnailSignals()
    
    def get_cache_path(self):
        """Get cache path for thumbnail."""
        if not self.project_path:
            return None
        cache_dir = os.path.join(self.project_path, "_cyne_db", "thumbnails")
        os.makedirs(cache_dir, exist_ok=True)
        
        # Use file path + timestamp for unique cache key
        unique_str = f"{self.path}_{self.timestamp}"
        hash_name = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
        return os.path.join(cache_dir, f"{hash_name}.jpg")
    
    def run(self):
        try:
            # Check cache first
            cache_path = self.get_cache_path()
            if cache_path and os.path.exists(cache_path):
                q_img = QImage(cache_path)
                if not q_img.isNull():
                    self.signals.thumbnail_ready.emit(self.path, q_img)
                    return
            
            # Generate thumbnail
            cap = cv2.VideoCapture(self.path)
            if not cap.isOpened():
                return
            
            # Seek to timestamp or middle of video
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            if self.timestamp > 0 and fps > 0:
                target_frame = int(self.timestamp * fps)
            elif total_frames > 0:
                target_frame = min(100, total_frames // 2)  # Use frame 100 or middle
            else:
                target_frame = 0
            
            if total_frames > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                # Convert BGR to RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, c = frame.shape
                bytes_per_line = c * w
                q_img_full = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                # Scale to thumbnail size (120x68)
                q_thumb = q_img_full.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatio, 
                                           Qt.TransformationMode.SmoothTransformation)
                
                # Save to cache
                if cache_path:
                    q_thumb.save(cache_path, "JPG", quality=85)
                
                self.signals.thumbnail_ready.emit(self.path, q_thumb.copy())
        except Exception as e:
            pass  # Silently fail - thumbnail is optional

# --- THUMBNAIL DELEGATE ---
class ThumbnailDelegate(QStyledItemDelegate):
    """Custom delegate to render thumbnails in tree items."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumbnails = {}  # Cache of loaded thumbnails: {path: QPixmap}
        self.tree_widget = parent  # Reference to tree widget
    
    def paint(self, painter, option, index):
        """Paint thumbnail in the thumbnail column (column 1)."""
        if index.column() != 1:  # Thumbnails are now in column 1
            super().paint(painter, option, index)
            return
        
        # Get item from tree widget
        item = self.tree_widget.itemFromIndex(index) if self.tree_widget else None
        if not item:
            super().paint(painter, option, index)
            return
        
        # Get file path from item (stored in column 10)
        file_path = item.text(10) if item.columnCount() > 10 else None
        
        # Check if this is a file (not folder)
        if not file_path or item.childCount() > 0:
            # For folders, just draw nothing (let default delegate handle it)
            super().paint(painter, option, index)
            return
        
        # For files, draw thumbnail in column 1 (separate from tree structure)
        # Draw thumbnail if available
        if file_path in self.thumbnails:
            pixmap = self.thumbnails[file_path]
            rect = option.rect
            # Center thumbnail in the column
            thumb_rect = QRect(rect.x() + 2, rect.y() + 2, 120, 68)
            
            # Draw thumbnail
            painter.drawPixmap(thumb_rect, pixmap)
        else:
            # Draw placeholder
            rect = option.rect
            placeholder_rect = QRect(rect.x() + 2, rect.y() + 2, 120, 68)
            painter.fillRect(placeholder_rect, QColor(COLORS['bg_input']))
            painter.setPen(QColor(COLORS['text_dim']))
            painter.drawText(placeholder_rect, Qt.AlignmentFlag.AlignCenter, "Loading...")
    
    def sizeHint(self, option, index):
        """Return size hint for thumbnail column."""
        if index.column() == 1:  # Thumbnails are now in column 1
            item = self.tree_widget.itemFromIndex(index) if self.tree_widget else None
            if item and item.columnCount() > 10:
                file_path = item.text(10)
                # Only return larger size for files (not folders)
                if file_path and item.childCount() == 0:
                    return QSize(124, 72)  # 120px width + padding, 68px height + padding
                else:
                    # Folders get standard size
                    return QSize(124, 24)  # Standard row height for folders
        return super().sizeHint(option, index)
    
    def set_thumbnail(self, file_path, image):
        """Set thumbnail for a file path."""
        self.thumbnails[file_path] = QPixmap.fromImage(image)
    
    def clear_thumbnails(self):
        """Clear thumbnail cache."""
        self.thumbnails.clear()

# --- MAIN TREE WIDGET ---
class MediaTree(QTreeWidget):
    files_dropped_signal = pyqtSignal(list)
    clear_data_signal = pyqtSignal(list, str)
    double_clicked_signal = pyqtSignal(str)  # Emits file path when double-clicked

    def __init__(self, project_path=None):
        super().__init__()
        self.project_path = project_path
        
        # COLUMN MAPPING:
        # 0: FILENAME (with checkbox and tree structure) - Main tree column
        # 1: THUMBNAIL (new) - Moved here to avoid conflict with tree structure
        # 2: RES
        # 3: FPS
        # 4: DUR
        # 5: VISUALS (👁️)
        # 5: VISUALS (👁️)
        # 6: AUDIO/TRANSCRIPTION (🔊)
        # 7: TRANSLATION (🌐)
        # 8: SHOT TYPE (📹)
        # 9: AI SUMMARY
        # 10: FULL_PATH (Hidden)
        # Set header labels - Reordered so filename is first (tree column)
        self.setHeaderLabels(["FILENAME", "", "RES", "FPS", "DUR", "👁️", "🔊", "🌐", "📹 SHOT", "AI SUMMARY", "FULL_PATH"])
        
        # Header Styling - Make columns resizable
        header = self.header()
        header.sectionClicked.connect(self.on_header_section_clicked)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Filename - resizable (tree column)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # Thumbnail - fixed width
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # RES - resizable
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # FPS - resizable
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # DUR - resizable
        
        # Status Columns - resizable but with minimum width
        for col in [5, 6]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.resizeSection(col, 30)
            header.setMinimumSectionSize(25)
            
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)  # Shot Type - resizable
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)  # AI Summary - stretches
        # Column 9 (FULL_PATH) should be hidden
        self.setColumnHidden(9, True)  # Full path - hidden
        
        # Set initial column widths
        header.resizeSection(0, 250)  # Filename - tree column (indentation will show here)
        header.resizeSection(1, 124)  # Thumbnail - fixed at 124px (120 + padding)
        header.resizeSection(2, 80)    # RES
        header.resizeSection(3, 60)   # FPS
        header.resizeSection(4, 70)    # DUR
        header.resizeSection(7, 100)   # Shot Type
        
        # Set thumbnail delegate for column 1 (thumbnails)
        self.thumbnail_delegate = ThumbnailDelegate(self)
        self.setItemDelegateForColumn(1, self.thumbnail_delegate) 
        
        # Tree Behavior
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)  # Changed to InternalMove for reordering
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        
        # Set proper indentation for tree hierarchy
        self.setIndentation(20)
        self.setRootIsDecorated(True)
        
        # Use uniform row heights OFF so we can have different heights for folders vs files
        self.setUniformRowHeights(False)
        
        # Ensure all columns respect tree indentation
        self.setAllColumnsShowFocus(True)
        
        # Make sure the first column (thumbnails) doesn't interfere with tree structure
        # The tree structure (expand/collapse) will be in column 0, but we'll position thumbnails correctly
        
        self.is_updating = False
        self.itemClicked.connect(self.handle_click)
        self.itemDoubleClicked.connect(self.handle_double_click)
        
        # Hover tooltip for thumbnails
        self.setMouseTracking(True)
        self._hover_tooltip = None
        self._hover_item = None
        
        # Setup keyboard shortcuts
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        self._delete_shortcut.activated.connect(self.remove_selected_items)
        
        self._select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        self._select_all_shortcut.activated.connect(lambda: self.toggle_all(True))
        
        # --- OPTIMIZATION: ThreadPool & Item Cache ---
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(os.cpu_count() or 4) # Adjust threads automatically
        self.item_map = {} # Dictionary for O(1) lookup: { normalized_path: QTreeWidgetItem }
        self.folder_map = {} # Dictionary for folder items: { normalized_folder_path: QTreeWidgetItem }
        
        # Thumbnail loading
        self.thumbnail_thread_pool = QThreadPool()
        self.thumbnail_thread_pool.setMaxThreadCount(2)  # Limit thumbnail threads to avoid overwhelming
        
        # Connect scroll signal for lazy loading (use QTimer to debounce)
        from PyQt6.QtCore import QTimer
        self._thumbnail_load_timer = QTimer()
        self._thumbnail_load_timer.setSingleShot(True)
        self._thumbnail_load_timer.timeout.connect(self._load_visible_thumbnails)
        
        self.verticalScrollBar().valueChanged.connect(lambda: self._thumbnail_load_timer.start(300))
        self.itemExpanded.connect(lambda: self._thumbnail_load_timer.start(300))
        self.itemCollapsed.connect(lambda: self._thumbnail_load_timer.start(300))
        
        self.setStyleSheet(f"""
            QTreeWidget {{ 
                background: {COLORS['bg_app']}; 
                border: 1px solid {COLORS['border']}; 
                border-radius: 4px; 
                font-size: 13px; 
                color: {COLORS['text_main']}; 
            }}
            QHeaderView::section {{ 
                background: {COLORS['bg_panel']}; 
                padding: 6px; 
                border: none; 
                border-bottom: 1px solid {COLORS['border']}; 
                color: {COLORS['text_dim']}; 
                font-weight: bold; 
            }}
            QTreeWidget::item {{ 
                padding: 4px; 
                color: {COLORS['text_main']} !important;
            }}
            QTreeWidget::item:selected {{ 
                background: {COLORS['selection']}; 
                color: {COLORS['accent']} !important; 
                border-left: 2px solid {COLORS['accent']}; 
            }}
            QTreeWidget::item:has-children {{ 
                font-weight: bold; 
                color: {COLORS['text_main']} !important; 
            }}
            QTreeWidget::item:hover {{
                background: {COLORS['bg_input']};
            }}
        """)
    
    def sizeHintForRow(self, index: int) -> int:
        """Override to provide different row heights for folders vs files."""
        # Find the item at this visual row by iterating through the tree
        def find_item_at_row(parent, target_row, current_row):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if current_row[0] == target_row:
                    return child
                current_row[0] += 1
                if child.childCount() > 0 and child.isExpanded():
                    result = find_item_at_row(child, target_row, current_row)
                    if result:
                        return result
            return None
        
        root = self.invisibleRootItem()
        current = [0]
        item = find_item_at_row(root, index, current)
        
        if item:
            # Check if it's a folder (has children) or a file
            if item.childCount() > 0:
                # Folders get standard compact height
                return 24
            else:
                # Files get larger height to accommodate thumbnails
                return 72
        return 24  # Default to compact height

    # --- DRAG & DROP ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        elif event.source() == self:
            # Internal drag for reordering
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        elif event.source() == self:
            # Internal drag for reordering
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            # External file drop
            event.accept()
            files = [u.toLocalFile() for u in event.mimeData().urls()]
            self.files_dropped_signal.emit(files)
        elif event.source() == self:
            # Internal reorder
            # In PyQt6, QDropEvent uses position() which returns QPointF, convert to QPoint
            drop_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
            item = self.itemAt(drop_pos)
            
            # Get selected items
            selected = self.selectedItems()
            if not selected:
                event.ignore()
                return
            
            if item:
                # Check if dropping on a folder or a file
                if item.childCount() > 0:
                    # Dropping on a folder
                    target_parent = item  # The folder itself is the target parent
                else:
                    # Dropping on a file - use the file's parent as target
                    target_parent = item.parent() or self.invisibleRootItem()
                
                # Move selected items to new position
                moved_any = False
                for selected_item in selected:
                    current_parent = selected_item.parent() or self.invisibleRootItem()
                    
                    # Only move if changing parent or position within same parent
                    if current_parent == target_parent:
                        # Same parent - check if position actually changes
                        old_index = current_parent.indexOfChild(selected_item)
                        
                        if item.childCount() > 0:
                            # Dropping on folder - insert at end of folder
                            new_index = target_parent.childCount()
                        else:
                            # Dropping on file - insert before that file
                            new_index = target_parent.indexOfChild(item)
                        
                        if old_index != new_index:
                            # Actually moving - perform the move
                            current_parent.takeChild(old_index)
                            if new_index > old_index:
                                new_index -= 1
                            current_parent.insertChild(new_index, selected_item)
                            moved_any = True
                        # else: same position, no move needed
                    else:
                        # Different parent - move to new parent
                        old_index = current_parent.indexOfChild(selected_item)
                        
                        if item.childCount() > 0:
                            # Dropping on folder - insert at end
                            new_index = target_parent.childCount()
                        else:
                            # Dropping on file - insert before that file
                            new_index = target_parent.indexOfChild(item)
                        
                        current_parent.takeChild(old_index)
                        target_parent.insertChild(new_index, selected_item)
                        moved_any = True
                
                if moved_any:
                    event.accept()
                else:
                    # No actual move occurred - restore original positions (already in place)
                    event.ignore()
                return
            else:
                # Dropping on empty space - ignore (don't move)
                event.ignore()
                return
        else:
            super().dropEvent(event)

    # --- CONTEXT MENU ---
    def contextMenuEvent(self, event):
        selected_files = self.get_selected_file_paths()
        selected_items = self.selectedItems()
        
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: #252526; color: white; border: 1px solid #444; }} QMenu::item:selected {{ background: {COLORS['accent']}; color: black; }}")
        
        # Batch operations
        if selected_files:
            batch_menu = menu.addMenu("Batch Operations")
            
            # Select operations
            select_menu = batch_menu.addMenu("Select")
            act_select_all_folder = select_menu.addAction("Select All in Folder")
            act_invert_selection = select_menu.addAction("Invert Selection")
            
            batch_menu.addSeparator()
            
            # Tag operations (will be implemented in metadata panel)
            act_copy_tags = batch_menu.addAction("Copy Tags from First Selected")
            act_apply_tags = batch_menu.addAction("Apply Tags to Selected...")
            
            menu.addSeparator()
        
        if selected_files:
            act_clear_vis = menu.addAction("Clear Visual Index")
            act_clear_aud = menu.addAction("Clear Transcription")
            menu.addSeparator()
            act_remove = menu.addAction("Remove from List (Del)")
        else:
            act_clear_vis = None
            act_clear_aud = None
            act_remove = None

        action = menu.exec(self.mapToGlobal(event.pos()))
        
        if action == act_clear_vis: 
            self.clear_data_signal.emit(selected_files, 'visuals')
        elif action == act_clear_aud: 
            self.clear_data_signal.emit(selected_files, 'audio')
        elif action == act_remove: 
            self.remove_selected_items()
        elif action == act_select_all_folder:
            self._select_all_in_folder()
        elif action == act_invert_selection:
            self._invert_selection()
        elif action == act_copy_tags:
            self._copy_tags_from_first()
        elif action == act_apply_tags:
            self._apply_tags_dialog()
    
    def _select_all_in_folder(self):
        """Select all files in the folder of the first selected item."""
        selected = self.selectedItems()
        if not selected:
            return
        
        first_item = selected[0]
        parent = first_item.parent() or self.invisibleRootItem()
        
        # Select all file children
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.childCount() == 0:  # It's a file
                child.setSelected(True)
    
    def _invert_selection(self):
        """Invert the current selection."""
        root = self.invisibleRootItem()
        all_items = []
        
        def collect_all_files(item):
            if item.childCount() == 0:
                all_items.append(item)
            else:
                for i in range(item.childCount()):
                    collect_all_files(item.child(i))
        
        for i in range(root.childCount()):
            collect_all_files(root.child(i))
        
        # Toggle selection
        for item in all_items:
            item.setSelected(not item.isSelected())
    
    def _copy_tags_from_first(self):
        """Copy tags from first selected file (placeholder for metadata panel integration)."""
        selected_files = self.get_selected_file_paths()
        if len(selected_files) < 2:
            return
        # This will be implemented when metadata panel supports bulk operations
        pass
    
    def _apply_tags_dialog(self):
        """Show dialog to apply tags to selected files (placeholder)."""
        # This will be implemented when metadata panel supports bulk operations
        pass

    # --- HELPER: PATH NORMALIZATION ---
    def norm(self, path):
        return os.path.normpath(path).lower()

    def set_project_path(self, project_path):
        """Set project path for thumbnail caching."""
        self.project_path = project_path
    
    def _load_visible_thumbnails(self):
        """Load thumbnails for currently visible items."""
        if not self.project_path:
            return
        
        # Get visible items
        visible_items = []
        viewport_rect = self.viewport().rect()
        
        def collect_visible(item, parent_rect):
            if item.childCount() == 0:  # Only files, not folders
                item_rect = self.visualItemRect(item)
                if viewport_rect.intersects(item_rect):
                    file_path = item.text(10)
                    if file_path and os.path.isfile(file_path):
                        # Check if thumbnail already loaded
                        if file_path not in self.thumbnail_delegate.thumbnails:
                            visible_items.append((item, file_path))
            else:
                # Recurse into folders
                for i in range(item.childCount()):
                    collect_visible(item.child(i), parent_rect)
        
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            collect_visible(root.child(i), viewport_rect)
        
        # Load thumbnails for visible items
        for item, file_path in visible_items:
            worker = ThumbnailWorker(file_path, self.project_path)
            worker.signals.thumbnail_ready.connect(
                lambda path, img, item=item: self._on_thumbnail_ready(path, img, item)
            )
            self.thumbnail_thread_pool.start(worker)
    
    def _on_thumbnail_ready(self, file_path, image, item):
        """Handle thumbnail ready signal."""
        self.thumbnail_delegate.set_thumbnail(file_path, image)
        # Trigger repaint for thumbnail column (column 1)
        index = self.indexFromItem(item, 1)
        if index.isValid():
            self.update(index)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for hover tooltip."""
        item = self.itemAt(event.pos())
        if item and item.childCount() == 0:  # Only for files
            file_path = item.text(9)
            if file_path and file_path in self.thumbnail_delegate.thumbnails:
                if item != self._hover_item:
                    self._hover_item = item
                    # Show larger thumbnail in tooltip
                    pixmap = self.thumbnail_delegate.thumbnails[file_path]
                    # Scale up for tooltip (240x136)
                    large_pixmap = pixmap.scaled(240, 136, Qt.AspectRatioMode.KeepAspectRatio, 
                                                 Qt.TransformationMode.SmoothTransformation)
                    item.setToolTip(0, "")  # Clear text tooltip
                    # Note: QToolTip doesn't support images directly, so we'll use a custom widget
                    # For now, just show filename in tooltip
                    item.setToolTip(0, f"{os.path.basename(file_path)}\nClick to preview")  # Tooltip on filename column
            else:
                self._hover_item = None
        else:
            self._hover_item = None
        super().mouseMoveEvent(event)
    
    # --- CHECKBOX HANDLING ---
    def handle_click(self, item, column):
        if column == 0 and not self.is_updating:  # Filename is now column 0 (tree column)
            self.is_updating = True
            new_state = item.checkState(0)  # Checkbox is in column 0 (tree column)
            
            # If this is a folder, propagate to children
            if item.childCount() > 0:
                self._set_children_state(item, new_state)
            # If this is a file, update parent folder checkbox state
            else:
                self._update_parent_checkbox(item)
            
            self.is_updating = False
            # Update header checkbox after individual item change
            self._update_header_checkbox()
    
    def itemChanged(self, item, column):
        """Override to handle checkbox state changes (including programmatic changes)."""
        if column == 0 and not self.is_updating:  # Filename is now column 0
            # This handles both user clicks and programmatic changes
            # The handle_click method handles the actual logic
            pass
        super().itemChanged(item, column)

    def _set_children_state(self, parent_item, state):
        """Recursively set checkbox state for all children."""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, state)  # Checkbox is in column 0 (tree column)
            # Recursively update children if this is also a folder
            if child.childCount() > 0:
                self._set_children_state(child, state)
    
    def _update_parent_checkbox(self, item):
        """Update parent folder checkbox based on children states."""
        parent = item.parent()
        if not parent:
            return
        
        # Count checked children
        checked_count = 0
        total_count = parent.childCount()
        
        for i in range(total_count):
            child = parent.child(i)
            if child.checkState(0) == Qt.CheckState.Checked:  # Checkbox is in column 0
                checked_count += 1
        
        # Set parent state based on children
        if checked_count == 0:
            parent.setCheckState(0, Qt.CheckState.Unchecked)  # Checkbox is in column 0
        elif checked_count == total_count:
            parent.setCheckState(0, Qt.CheckState.Checked)  # Checkbox is in column 0
        else:
            parent.setCheckState(0, Qt.CheckState.PartiallyChecked)  # Checkbox is in column 0
        
        # Recursively update grandparent
        self._update_parent_checkbox(parent)

    def handle_double_click(self, item, column):
        """Opens the player window when a file is double-clicked."""
        file_path = item.text(10)  # Column 10 contains the full path
        if file_path and os.path.exists(file_path):
            # Emit signal to main window to open player
            self.double_clicked_signal.emit(file_path)

    def toggle_all(self, state=True):
        """Toggle all file checkboxes (not folders, but folders will update based on children)."""
        self.is_updating = True
        root = self.invisibleRootItem()
        target = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        
        def set_all_files(item, target_state):
            """Recursively set all file items to target state."""
            if item.childCount() == 0:
                # This is a file
                item.setCheckState(0, target_state)  # Checkbox is in column 0 (tree column)
            else:
                # This is a folder, set all children
                for i in range(item.childCount()):
                    child = item.child(i)
                    set_all_files(child, target_state)
                # Update folder checkbox based on children
                self._update_folder_checkbox_from_children(item)
        
        for i in range(root.childCount()):
            item = root.child(i)
            set_all_files(item, target)
        
        self.is_updating = False
        # Update header checkbox indicator
        self._update_header_checkbox()
    
    def _update_folder_checkbox_from_children(self, folder_item):
        """Update folder checkbox state based on its children."""
        if folder_item.childCount() == 0:
            return
        
        checked_count = 0
        total_count = folder_item.childCount()
        
        for i in range(total_count):
            child = folder_item.child(i)
            if child.checkState(0) == Qt.CheckState.Checked:  # Checkbox is in column 0 (tree column)
                checked_count += 1
        
        if checked_count == 0:
            folder_item.setCheckState(0, Qt.CheckState.Unchecked)  # Checkbox is in column 0 (tree column)
        elif checked_count == total_count:
            folder_item.setCheckState(0, Qt.CheckState.Checked)  # Checkbox is in column 0 (tree column)
        else:
            folder_item.setCheckState(0, Qt.CheckState.PartiallyChecked)  # Checkbox is in column 0 (tree column)
    
    def _update_folder_display(self, folder_item):
        """Update folder display text with file count."""
        if folder_item.childCount() == 0:
            return
        
        # Count files (not subfolders) recursively
        def count_files_recursive(item):
            count = 0
            for i in range(item.childCount()):
                child = item.child(i)
                if child.childCount() == 0:
                    count += 1
                else:
                    count += count_files_recursive(child)
            return count
        
        file_count = count_files_recursive(folder_item)
        
        # Get original folder name from path stored in column 10
        folder_path = folder_item.text(10)
        if folder_path:
            folder_name = os.path.basename(folder_path)
            if not folder_name:
                # Handle root or drive letter case
                folder_name = folder_path if folder_path else "Root"
        else:
            # Fallback to extracting from text
            original_text = folder_item.text(0)  # Filename is now column 0
            if "📁" in original_text:
                folder_name = original_text.split("📁", 1)[1].strip()
                # Remove existing count if present
                if "(" in folder_name:
                    folder_name = folder_name.split("(")[0].strip()
            else:
                folder_name = original_text
        
        # Update with file count (folder name is in column 0 - tree column)
        if file_count > 0:
            folder_item.setText(0, f"📁 {folder_name} ({file_count})")  # Filename is now column 0
        else:
            folder_item.setText(0, f"📁 {folder_name}")  # Filename is now column 0

    def _update_header_checkbox(self):
        """Updates the header checkbox indicator based on current state."""
        root = self.invisibleRootItem()
        if root.childCount() == 0:
            header_item = self.headerItem()
            if header_item:
                header_item.setText(0, "☐ FILENAME")
            return
        
        # Count all file items (not folders) recursively
        def count_files(item):
            if item.childCount() == 0:
                # This is a file
                return 1, 1 if item.checkState(0) == Qt.CheckState.Checked else 0  # Checkbox is in column 0
            else:
                # This is a folder, count children
                total = 0
                checked = 0
                for i in range(item.childCount()):
                    child = item.child(i)
                    t, c = count_files(child)
                    total += t
                    checked += c
                return total, checked
        
        total_files = 0
        checked_files = 0
        for i in range(root.childCount()):
            item = root.child(i)
            t, c = count_files(item)
            total_files += t
            checked_files += c
        
        header_item = self.headerItem()
        if header_item:
            if total_files == 0:
                header_item.setText(0, "☐ FILENAME")  # Filename is now column 0
            elif checked_files == total_files:
                header_item.setText(0, "☑ FILENAME")  # Filename is now column 0
            elif checked_files > 0:
                header_item.setText(0, "☒ FILENAME")  # Indeterminate, filename is now column 0
            else:
                header_item.setText(0, "☐ FILENAME")  # Filename is now column 0

    def on_header_section_clicked(self, logical_index):
        """Handle clicks on header sections - column 0 (filename/tree column) toggles all."""
        if logical_index == 0:  # Filename is now column 0 (tree column)
            # Toggle all when clicking the FILENAME header
            root = self.invisibleRootItem()
            if root.childCount() == 0:
                return
            
            # Count all files and checked files
            def count_all_files(item):
                if item.childCount() == 0:
                    return 1, 1 if item.checkState(0) == Qt.CheckState.Checked else 0  # Checkbox is in column 0
                else:
                    total = 0
                    checked = 0
                    for i in range(item.childCount()):
                        child = item.child(i)
                        t, c = count_all_files(child)
                        total += t
                        checked += c
                    return total, checked
            
            total_files = 0
            checked_files = 0
            for i in range(root.childCount()):
                item = root.child(i)
                t, c = count_all_files(item)
                total_files += t
                checked_files += c
            
            # Toggle to opposite state
            all_checked = (total_files > 0 and checked_files == total_files)
            self.toggle_all(not all_checked)

    def on_header_checkbox_changed(self, state):
        """Called when header checkbox is toggled directly (if we add a real checkbox widget)."""
        is_checked = (state == Qt.CheckState.Checked.value)
        self.toggle_all(is_checked)

    # --- FILE ADDING (HIERARCHICAL) ---
    def add_files_flat(self, file_paths):
        """Add files in hierarchical folder structure. Kept name for backward compatibility."""
        # 1. Filter existing
        new_files = [p for p in file_paths if self.norm(p) not in self.item_map]
        if not new_files: return

        # 2. Group files by parent directory
        from collections import defaultdict
        files_by_folder = defaultdict(list)
        
        for path in new_files:
            parent_dir = os.path.dirname(path)
            files_by_folder[parent_dir].append(path)
        
        # 3. Create folder structure and add files
        root = self.invisibleRootItem()
        
        for folder_path, files in files_by_folder.items():
            # Get or create folder item
            folder_item = self._get_or_create_folder(folder_path, root)
            
            # Add files to this folder
            for path in files:
                file_item = QTreeWidgetItem(folder_item)
                file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                file_item.setCheckState(0, Qt.CheckState.Checked)  # Checkbox is in column 0 (tree column)
                
                file_item.setText(0, os.path.basename(path))  # Filename (tree column - will show indented)
                file_item.setText(1, "")  # Thumbnail column - empty initially
                file_item.setText(2, "...")  # RES
                file_item.setText(3, "...")  # FPS
                file_item.setText(4, "...")  # DUR
                file_item.setText(5, "⬜")  # Visuals
                file_item.setText(6, "⬜")  # Audio
                file_item.setText(7, "--")  # Shot type
                file_item.setText(8, "Waiting for scan...")  # Summary
                file_item.setText(10, path)  # Full path (column 10)
                
                # Set explicit foreground colors for all text columns to ensure visibility
                for col in [0, 2, 3, 4, 7, 8]:  # Updated column numbers (0 is filename now)
                    file_item.setForeground(col, QBrush(QColor(COLORS['text_main'])))
                
                # Load thumbnail for this file
                if self.project_path:
                    worker = ThumbnailWorker(path, self.project_path)
                    worker.signals.thumbnail_ready.connect(
                        lambda p, img, item=file_item: self._on_thumbnail_ready(p, img, item)
                    )
                    self.thumbnail_thread_pool.start(worker)
                
                # Cache the item for O(1) lookup
                self.item_map[self.norm(path)] = file_item
                
                # Queue Background Worker
                worker = MediaLoaderWorker(path)
                worker.signals.finished.connect(self.update_item_metadata)
                self.thread_pool.start(worker)
            
            # Update folder checkbox based on children
            self._update_folder_checkbox_from_children(folder_item)
            # Update folder display with file count
            self._update_folder_display(folder_item)
        
        # Update header checkbox after adding items
        self._update_header_checkbox()
        
        # Trigger thumbnail loading for visible items (debounced)
        if hasattr(self, '_thumbnail_load_timer'):
            self._thumbnail_load_timer.start(500)
    
    def _get_or_create_folder(self, folder_path, parent_item):
        """Get existing folder item or create it with all parent folders."""
        # Normalize the path
        folder_path = os.path.normpath(folder_path)
        norm_folder = self.norm(folder_path)
        
        # Check if folder already exists
        if norm_folder in self.folder_map:
            return self.folder_map[norm_folder]
        
        # Handle empty or root paths - use PathLib for better cross-platform handling
        if not folder_path or folder_path == '.' or folder_path == os.sep:
            # Create a "Root" folder
            folder_item = QTreeWidgetItem(parent_item)
            folder_item.setFlags(folder_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            folder_item.setCheckState(0, Qt.CheckState.Checked)  # Checkbox is in column 0 (tree column)
            folder_item.setText(0, "📁 Root")  # Filename (tree column - will show indented)
            folder_item.setText(1, "")  # Thumbnail column - empty for folders
            folder_item.setText(10, folder_path if folder_path else ".")
            folder_item.setExpanded(True)
            self.folder_map[norm_folder] = folder_item
            return folder_item
        
        # Use os.path.split to properly handle paths (works on Windows with drive letters)
        parts = []
        current = folder_path
        
        # Build parts list from bottom up
        while True:
            current, tail = os.path.split(current)
            if not tail:
                # Handle drive letters on Windows (e.g., "C:")
                if current and len(current) == 2 and current[1] == ':':
                    parts.insert(0, current)
                break
            parts.insert(0, tail)
            if not current or current == os.sep:
                break
        
        current_item = parent_item
        current_path_parts = []
        
        for part in parts:
            current_path_parts.append(part)
            # Reconstruct path properly
            if len(current_path_parts) == 1:
                current_path = current_path_parts[0]
            else:
                current_path = os.path.join(*current_path_parts)
            norm_current = self.norm(current_path)
            
            # Check if this folder level already exists
            if norm_current in self.folder_map:
                current_item = self.folder_map[norm_current]
                continue
            
            # Create new folder item
            folder_item = QTreeWidgetItem(current_item)
            folder_item.setFlags(folder_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            folder_item.setCheckState(0, Qt.CheckState.Checked)  # Checkbox is in column 0 (tree column)
            
            # Set folder icon and name (in tree column 0 - will show indented)
            folder_item.setText(0, f"📁 {part}")  # Filename (tree column - will show indented)
            folder_item.setText(1, "")  # Thumbnail column - empty for folders
            folder_item.setText(2, "")  # RES
            folder_item.setText(3, "")   # FPS
            folder_item.setText(4, "")  # DUR
            folder_item.setText(5, "")  # Visuals
            folder_item.setText(6, "")   # Audio
            folder_item.setText(7, "")   # Shot type
            folder_item.setText(8, "")   # Summary
            folder_item.setText(10, current_path)  # Store path for reference (column 10)
            
            # Set explicit foreground color for folder name to ensure visibility
            folder_item.setForeground(0, QBrush(QColor(COLORS['text_main'])))  # Filename is now column 0
            
            # Expand folder by default
            folder_item.setExpanded(True)
            
            # Cache folder
            self.folder_map[norm_current] = folder_item
            current_item = folder_item
        
        return current_item

    def update_item_metadata(self, path, res, fps, dur, status, summary, shot_type):
        """Called when a worker finishes analyzing a file."""
        item = self.item_map.get(self.norm(path))
        if not item: return

        item.setText(2, res)  # RES column
        item.setText(3, fps)  # FPS column
        item.setText(4, dur)  # DUR column
        item.setText(8, shot_type if shot_type else "--")  # Shot type column (moved to 8)
        item.setText(9, summary)  # Summary column (moved to 9)
        
        # Ensure text colors are visible for all columns
        for col in [0, 2, 3, 4, 8, 9]:  # Column 0 is filename, others are metadata
            item.setForeground(col, QBrush(QColor(COLORS['text_main'])))
        
        self._set_status_icon(item, 5, status['visuals'])  # Visuals column
        self._set_status_icon(item, 6, status['audio'])  # Audio/transcription column
        self._set_status_icon(item, 7, status.get('translation', False))  # Translation column
        
        # Update integration tooltip
        self._update_integration_tooltip(item)
        
        # Update parent folder display
        parent = item.parent()
        if parent:
            self._update_folder_display(parent)

    def _set_status_icon(self, item, col, is_done):
        if is_done:
            item.setText(col, "✅")
            item.setForeground(col, QBrush(QColor(COLORS['accent'])))
        else:
            item.setText(col, "⬜")
            item.setForeground(col, QBrush(QColor("#444")))
    
    def _get_integration_status(self, item):
        """Get combined integration status for tooltip."""
        status = {
            'visuals': item.text(5) == "✅",
            'audio': item.text(6) == "✅",
            'translation': item.text(7) == "✅"
        }
        return status
    
    def _update_integration_tooltip(self, item):
        """Update tooltip to show integration status."""
        status = self._get_integration_status(item)
        parts = []
        
        if status['visuals']:
            parts.append("Visual Analysis")
        if status['audio']:
            parts.append("Audio Transcription")
        if status['translation']:
            # Get translation method from database if available
            file_path = item.text(10) if item.columnCount() > 10 else None
            translation_method = None
            if file_path:
                try:
                    from core.database import Database
                    db = Database()
                    meta = db.get_video_metadata(file_path)
                    translation_method = meta.get("translation_method", "whisper")
                except:
                    pass
            method_text = "DeepL" if translation_method == "deepl" else "Whisper"
            parts.append(f"Translation ({method_text})")
        
        if parts:
            tooltip = "✓ " + " + ".join(parts)
            if len(parts) > 1:
                tooltip += "\n\nData from multiple sources enhances search accuracy."
        else:
            tooltip = "No analysis data available"
        
        item.setToolTip(0, tooltip)
    
    def _update_item_highlighting(self, item):
        """Highlight items with both video and audio indexed in light green."""
        status = self._get_integration_status(item)
        
        if status['visuals'] and status['audio']:
            # Both indexed - highlight in light green
            light_green = QColor("#90EE90")  # Light green color
            item.setBackground(0, QBrush(light_green))
            # Also highlight other visible columns
            for col in range(1, 10):  # Columns 1-9 (skip hidden column 10)
                item.setBackground(col, QBrush(light_green))
        else:
            # Not fully indexed - remove highlighting
            transparent = QColor(0, 0, 0, 0)  # Transparent
            for col in range(9):
                item.setBackground(col, QBrush(transparent))

    # --- EXTERNAL UPDATES (OPTIMIZED LOOKUP) ---
    def set_processing_icon(self, file_path, data_type):
        col_map = {'visuals': 5, 'audio': 6, 'translation': 7}
        if data_type in col_map:
            self.update_item_status(file_path, col_map[data_type], "⏳")

    def mark_visuals_done(self, file_path, summary_text):
        self.update_item_status(file_path, 5, "✅", summary_text)
        # Also update shot type if available
        try:
            from core.database import Database
            db = Database()
            if db.project_path:
                data = db.get_video_metadata(file_path)
                shot_type = data.get("shot_type", "")
                if shot_type:
                    item = self.item_map.get(self.norm(file_path))
                    if item:
                        item.setText(8, shot_type)  # Shot type is now column 8
        except:
            pass

    def mark_audio_done(self, file_path):
        self.update_item_status(file_path, 6, "✅")
    
    def mark_translation_done(self, file_path):
        """Mark translation as complete for a file."""
        self.update_item_status(file_path, 7, "✅")
        
    def reset_status(self, file_path, data_type):
        col_map = {'visuals': 5, 'audio': 6, 'translation': 7}
        if data_type in col_map:
            self.update_item_status(file_path, col_map[data_type], "⬜")

    def update_item_status(self, file_path, column_index, icon_text, summary_text=None):
        # O(1) Lookup - No more looping!
        item = self.item_map.get(self.norm(file_path))
        if not item: return

        item.setText(column_index, icon_text)
        
        if icon_text == "✅":
            item.setForeground(column_index, QBrush(QColor(COLORS['accent'])))
        elif icon_text == "⏳":
            item.setForeground(column_index, QBrush(QColor("#FFEB3B"))) # Yellow
        else:
            item.setForeground(column_index, QBrush(QColor("#444")))
        
        if summary_text is not None:
            item.setText(8, summary_text)  # AI Summary is column 8 (unchanged)
        
        # Update integration tooltip when status changes
        self._update_integration_tooltip(item)
        
        # Highlight items with both video and audio indexed
        self._update_item_highlighting(item)
        
        # Highlight items with both video and audio indexed
        self._update_item_highlighting(item)

    def remove_selected_items(self):
        """Remove selected items. If folder is selected, remove all children files."""
        root = self.invisibleRootItem()
        items_to_remove = []
        
        for item in self.selectedItems():
            path = item.text(9)
            norm_p = self.norm(path)
            
            if item.childCount() == 0:
                # This is a file
                if norm_p in self.item_map:
                    del self.item_map[norm_p]
                items_to_remove.append((item, item.parent() or root))
            else:
                # This is a folder - remove all file children
                def remove_all_files(folder_item):
                    for i in range(folder_item.childCount() - 1, -1, -1):
                        child = folder_item.child(i)
                        if child.childCount() == 0:
                            # It's a file
                            child_path = child.text(10)
                            child_norm = self.norm(child_path)
                            if child_norm in self.item_map:
                                del self.item_map[child_norm]
                            folder_item.removeChild(child)
                        else:
                            # It's a subfolder
                            remove_all_files(child)
                            folder_norm = self.norm(child.text(10))
                            if folder_norm in self.folder_map:
                                del self.folder_map[folder_norm]
                            folder_item.removeChild(child)
                    # Remove folder from map if empty
                    if folder_item.childCount() == 0:
                        folder_norm = self.norm(folder_item.text(10))
                        if folder_norm in self.folder_map:
                            del self.folder_map[folder_norm]
                        parent = folder_item.parent() or root
                        parent.removeChild(folder_item)
                
                remove_all_files(item)
        
        # Remove items
        for item, parent in items_to_remove:
            parent.removeChild(item)
        
        self._update_header_checkbox()

    # --- GETTERS ---
    def get_all_file_paths(self):
        """Get all file paths (not folders) recursively."""
        paths = []
        root = self.invisibleRootItem()
        
        def collect_files(item):
            if item.childCount() == 0:
                # This is a file
                path = item.text(10)
                if path and os.path.isfile(path):  # Verify it's actually a file
                    paths.append(path)
            else:
                # This is a folder, recurse
                for i in range(item.childCount()):
                    collect_files(item.child(i))
        
        for i in range(root.childCount()):
            collect_files(root.child(i))
        
        return paths
    
    def get_selected_file_paths(self):
        """Get selected file paths (not folders)."""
        paths = []
        for item in self.selectedItems():
            if item.childCount() == 0:
                # This is a file
                path = item.text(10)
                if path and os.path.isfile(path):
                    paths.append(path)
            else:
                # This is a folder - collect all file children
                def collect_files(folder_item):
                    for i in range(folder_item.childCount()):
                        child = folder_item.child(i)
                        if child.childCount() == 0:
                            path = child.text(9)
                            if path and os.path.isfile(path):
                                paths.append(path)
                        else:
                            collect_files(child)
                collect_files(item)
        return paths
    
    def get_checked_file_paths(self):
        """Get checked file paths (not folders) recursively."""
        paths = []
        root = self.invisibleRootItem()
        
        def collect_checked_files(item):
            if item.childCount() == 0:
                # This is a file
                if item.checkState(0) == Qt.CheckState.Checked:  # Checkbox is in column 0
                    path = item.text(10)
                    if path and os.path.isfile(path):
                        paths.append(path)
            else:
                # This is a folder, recurse to children
                for i in range(item.childCount()):
                    collect_checked_files(item.child(i))
        
        for i in range(root.childCount()):
            collect_checked_files(root.child(i))
        
        return paths