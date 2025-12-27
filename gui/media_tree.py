# [FILE: gui/media_tree.py]
import os
import json
import time
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QRunnable, QThreadPool, QObject
from PyQt6.QtGui import QColor, QBrush, QDragEnterEvent, QDropEvent
from config import COLORS
from core.media_engine import MediaEngine 

# --- WORKER SIGNALS ---
class WorkerSignals(QObject):
    finished = pyqtSignal(str, str, str, str, dict, str) # path, res, fps, dur, status, summary

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

            # 2. Check for Existing JSON Sidecar Data
            status = {'visuals': False, 'audio': False, 'faces': False}
            summary_str = ""
            
            json_path = f"{self.path}.json"
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("tags"): status['visuals'] = True
                        if data.get("transcript"): status['audio'] = True
                        if data.get("faces"): status['faces'] = True
                        summary_str = data.get("summary", "")
                except:
                    pass

            # 3. Emit Results
            self.signals.finished.emit(self.path, res_str, fps_str, dur_str, status, summary_str)

        except Exception as e:
            # On generic failure, emit safe defaults
            self.signals.finished.emit(self.path, "Error", "--", "--:--", 
                                     {'visuals': False, 'audio': False, 'faces': False}, "")

# --- MAIN TREE WIDGET ---
class MediaTree(QTreeWidget):
    files_dropped_signal = pyqtSignal(list)
    clear_data_signal = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        
        # COLUMN MAPPING:
        # 0: FILENAME
        # 1: RES
        # 2: FPS
        # 3: DUR
        # 4: VISUALS (👁️)
        # 5: AUDIO (🔊)
        # 6: FACES (👤)
        # 7: AI SUMMARY
        # 8: FULL_PATH (Hidden)
        self.setHeaderLabels(["FILENAME", "RES", "FPS", "DUR", "👁️", "🔊", "👤", "AI SUMMARY", "FULL_PATH"])
        
        # Header Styling
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        
        # Status Columns Fixed Width
        for col in [4, 5, 6]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(col, 30)
            
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.setColumnHidden(8, True) 
        
        # Tree Behavior
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        
        self.is_updating = False
        self.itemClicked.connect(self.handle_click)
        
        # --- OPTIMIZATION: ThreadPool & Item Cache ---
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(os.cpu_count() or 4) # Adjust threads automatically
        self.item_map = {} # Dictionary for O(1) lookup: { normalized_path: QTreeWidgetItem }
        
        self.setStyleSheet(f"""
            QTreeWidget {{ background: {COLORS['bg_app']}; border: 1px solid {COLORS['border']}; border-radius: 4px; font-size: 13px; color: #DDD; }}
            QHeaderView::section {{ background: {COLORS['bg_panel']}; padding: 6px; border: none; border-bottom: 1px solid {COLORS['border']}; color: {COLORS['text_dim']}; font-weight: bold; }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:selected {{ background: {COLORS['selection']}; color: {COLORS['accent']}; border-left: 2px solid {COLORS['accent']}; }}
        """)

    # --- DRAG & DROP ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.accept()
            files = [u.toLocalFile() for u in event.mimeData().urls()]
            self.files_dropped_signal.emit(files)
        else:
            super().dropEvent(event)

    # --- CONTEXT MENU ---
    def contextMenuEvent(self, event):
        selected_files = self.get_selected_file_paths()
        if not selected_files: return
        
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: #252526; color: white; border: 1px solid #444; }} QMenu::item:selected {{ background: {COLORS['accent']}; color: black; }}")
        
        act_clear_vis = menu.addAction("Clear Visual Index")
        act_clear_aud = menu.addAction("Clear Transcription")
        act_clear_face = menu.addAction("Clear Face Data")
        menu.addSeparator()
        act_remove = menu.addAction("Remove from List")

        action = menu.exec(self.mapToGlobal(event.pos()))
        
        if action == act_clear_vis: self.clear_data_signal.emit(selected_files, 'visuals')
        elif action == act_clear_aud: self.clear_data_signal.emit(selected_files, 'audio')
        elif action == act_clear_face: self.clear_data_signal.emit(selected_files, 'faces')
        elif action == act_remove: self.remove_selected_items()

    # --- HELPER: PATH NORMALIZATION ---
    def norm(self, path):
        return os.path.normpath(path).lower()

    # --- CHECKBOX HANDLING ---
    def handle_click(self, item, column):
        if column == 0 and not self.is_updating:
            self.is_updating = True
            new_state = item.checkState(0)
            self._set_children_state(item, new_state)
            self.is_updating = False

    def _set_children_state(self, parent_item, state):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child.setCheckState(0, state)
            self._set_children_state(child, state)

    def toggle_all(self, state=True):
        self.is_updating = True
        root = self.invisibleRootItem()
        target = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        for i in range(root.childCount()):
            item = root.child(i)
            item.setCheckState(0, target)
            self._set_children_state(item, target)
        self.is_updating = False

    # --- FILE ADDING (OPTIMIZED) ---
    def add_files_flat(self, file_paths):
        # 1. Filter existing
        new_files = [p for p in file_paths if self.norm(p) not in self.item_map]
        if not new_files: return

        # 2. Add placeholders instantly
        for path in new_files:
            item = QTreeWidgetItem(self)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(0, Qt.CheckState.Checked)
            
            item.setText(0, os.path.basename(path))
            item.setText(1, "...") 
            item.setText(2, "...") 
            item.setText(3, "...") 
            item.setText(4, "⬜")
            item.setText(5, "⬜")
            item.setText(6, "⬜")
            item.setText(7, "Waiting for scan...")
            item.setText(8, path) 
            
            # Cache the item for O(1) lookup
            self.item_map[self.norm(path)] = item

            # 3. Queue Background Worker
            worker = MediaLoaderWorker(path)
            worker.signals.finished.connect(self.update_item_metadata)
            self.thread_pool.start(worker)

    def update_item_metadata(self, path, res, fps, dur, status, summary):
        """Called when a worker finishes analyzing a file."""
        item = self.item_map.get(self.norm(path))
        if not item: return

        item.setText(1, res)
        item.setText(2, fps)
        item.setText(3, dur)
        item.setText(7, summary)
        
        self._set_status_icon(item, 4, status['visuals'])
        self._set_status_icon(item, 5, status['audio'])
        self._set_status_icon(item, 6, status['faces'])

    def _set_status_icon(self, item, col, is_done):
        if is_done:
            item.setText(col, "✅")
            item.setForeground(col, QBrush(QColor(COLORS['accent'])))
        else:
            item.setText(col, "⬜")
            item.setForeground(col, QBrush(QColor("#444")))

    # --- EXTERNAL UPDATES (OPTIMIZED LOOKUP) ---
    def set_processing_icon(self, file_path, data_type):
        col_map = {'visuals': 4, 'audio': 5, 'faces': 6}
        if data_type in col_map:
            self.update_item_status(file_path, col_map[data_type], "⏳")

    def mark_visuals_done(self, file_path, summary_text):
        self.update_item_status(file_path, 4, "✅", summary_text)

    def mark_audio_done(self, file_path):
        self.update_item_status(file_path, 5, "✅")

    def mark_faces_done(self, file_path):
        self.update_item_status(file_path, 6, "✅")
        
    def reset_status(self, file_path, data_type):
        col_map = {'visuals': 4, 'audio': 5, 'faces': 6}
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
            item.setText(7, summary_text)

    def remove_selected_items(self):
        root = self.invisibleRootItem()
        for item in self.selectedItems():
            path = item.text(8)
            norm_p = self.norm(path)
            if norm_p in self.item_map:
                del self.item_map[norm_p]
            (item.parent() or root).removeChild(item)

    # --- GETTERS ---
    def get_all_file_paths(self):
        # We can just return the keys from our map, but to preserve order 
        # (in case sorting changed), we iterate the tree.
        paths = []
        root = self.invisibleRootItem()
        # Flat iteration for top-level items
        for i in range(root.childCount()):
            item = root.child(i)
            paths.append(item.text(8))
        return paths
    
    def get_selected_file_paths(self):
        return [item.text(8) for item in self.selectedItems()]
    
    def get_checked_file_paths(self):
        paths = []
        root = self.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                paths.append(item.text(8))
        return paths