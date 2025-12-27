import os
import cv2
import json
import time
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor, QBrush, QDragEnterEvent, QDropEvent
from config import COLORS

# --- NEW WORKER: Offloads file reading to background thread ---
class FileMetadataLoader(QThread):
    # Emits: (file_path, resolution, fps, status_dict, summary)
    data_loaded = pyqtSignal(str, str, str, dict, str)

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths
        self.is_running = True

    def run(self):
        for path in self.file_paths:
            if not self.is_running: break
            
            res_str, fps_str = "Unknown", "--"
            status = {'visuals': False, 'audio': False, 'faces': False}
            summary_str = ""

            # 1. Heavy Video Read
            try:
                cap = cv2.VideoCapture(path)
                if cap.isOpened():
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    res_str = f"{w}x{h}"
                    fps_str = f"{fps:.2f}"
                cap.release()
            except: pass

            # 2. JSON Metadata Read
            json_path = f"{path}.json"
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get("tags"): status['visuals'] = True
                        if data.get("transcript"): status['audio'] = True
                        if data.get("faces"): status['faces'] = True
                        
                        summary_str = data.get("summary", "")
                        if status['audio'] and not summary_str: 
                            summary_str = "Transcript available."
                except: pass
            
            self.data_loaded.emit(path, res_str, fps_str, status, summary_str)
            # Tiny sleep to prevent GUI flooding on fast SSDs
            time.sleep(0.005) 

    def stop(self):
        self.is_running = False

class MediaTree(QTreeWidget):
    files_dropped_signal = pyqtSignal(list)
    clear_data_signal = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.setHeaderLabels(["FILENAME", "RES", "FPS", "👁️", "🔊", "👤", "AI SUMMARY", "FULL_PATH"])
        
        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        
        for col in [3, 4, 5]:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(col, 30)
            
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.setColumnHidden(7, True)
        
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        
        self.is_updating = False
        self.itemClicked.connect(self.handle_click)
        
        # Thread Management
        self.loader_thread = None
        self.pending_files = []

        self.setStyleSheet(f"""
            QTreeWidget {{ background: {COLORS['bg_app']}; border: 1px solid {COLORS['border']}; border-radius: 4px; font-size: 13px; color: #DDD; }}
            QHeaderView::section {{ background: {COLORS['bg_panel']}; padding: 6px; border: none; border-bottom: 1px solid {COLORS['border']}; color: {COLORS['text_dim']}; font-weight: bold; }}
            QTreeWidget::item {{ padding: 4px; }}
            QTreeWidget::item:selected {{ background: {COLORS['selection']}; color: {COLORS['accent']}; border-left: 2px solid {COLORS['accent']}; }}
        """)

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

    def contextMenuEvent(self, event):
        selected_files = self.get_selected_file_paths()
        if not selected_files: return

        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: #252526; color: white; border: 1px solid #444; }} QMenu::item:selected {{ background: {COLORS['accent']}; color: black; }}")
        
        act_clear_vis = menu.addAction("Clear Visual Index")
        act_clear_aud = menu.addAction("Clear Transcription")
        act_clear_face = menu.addAction("Clear Face Data")
        
        action = menu.exec(self.mapToGlobal(event.pos()))
        
        if action == act_clear_vis: self.clear_data_signal.emit(selected_files, 'visuals')
        elif action == act_clear_aud: self.clear_data_signal.emit(selected_files, 'audio')
        elif action == act_clear_face: self.clear_data_signal.emit(selected_files, 'faces')

    def norm(self, path):
        return os.path.normpath(path).lower()

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

    # --- UPDATED: Async Adding ---
    def add_files_flat(self, file_paths):
        # 1. Filter duplicates immediately
        existing_paths = set(self.get_all_file_paths())
        new_files = [p for p in file_paths if self.norm(p) not in existing_paths]
        
        if not new_files: return

        # 2. Create "Pending" items immediately (Main Thread)
        for path in new_files:
            item = QTreeWidgetItem(self)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(0, Qt.CheckState.Checked)
            
            item.setText(0, os.path.basename(path))
            item.setText(1, "...") # Pending Res
            item.setText(2, "...") # Pending FPS
            item.setText(3, "⬜")
            item.setText(4, "⬜")
            item.setText(5, "⬜")
            item.setText(6, "Waiting for scan...")
            item.setText(7, path)
        
        # 3. Queue for background loading
        self._start_loader_thread(new_files)

    def _start_loader_thread(self, files):
        # If thread exists, stop it and merge queues (simple approach: just restart)
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            self.loader_thread.wait()
            # In a real app, you'd merge pending_files, but for now we process the new batch
        
        self.loader_thread = FileMetadataLoader(files)
        self.loader_thread.data_loaded.connect(self._update_item_data)
        self.loader_thread.start()

    def _update_item_data(self, path, res, fps, status, summary):
        # Find the item and update it
        target = self.norm(path)
        root = self.invisibleRootItem()
        
        # Helper to find item
        def find_item(parent):
            for i in range(parent.childCount()):
                it = parent.child(i)
                if self.norm(it.text(7)) == target: return it
            return None

        item = find_item(root)
        if item:
            item.setText(1, res)
            item.setText(2, fps)
            item.setText(6, summary)
            
            self._set_status_icon(item, 3, status['visuals'])
            self._set_status_icon(item, 4, status['audio'])
            self._set_status_icon(item, 5, status['faces'])

    def _set_status_icon(self, item, col, is_done):
        if is_done:
            item.setText(col, "✅")
            item.setForeground(col, QBrush(QColor(COLORS['accent'])))
        else:
            item.setText(col, "⬜")
            item.setForeground(col, QBrush(QColor("#444")))

    # --- NEW: Processing State ---
    def set_processing_icon(self, file_path, data_type):
        """Sets an hourglass icon while AI is working"""
        col_map = {'visuals': 3, 'audio': 4, 'faces': 5}
        if data_type not in col_map: return
        
        self.update_item_status(file_path, col_map[data_type], "⏳")

    def mark_visuals_done(self, file_path, summary_text):
        self.update_item_status(file_path, 3, "✅", summary_text)

    def mark_audio_done(self, file_path):
        self.update_item_status(file_path, 4, "✅")

    def mark_faces_done(self, file_path):
        self.update_item_status(file_path, 5, "✅")
        
    def reset_status(self, file_path, data_type):
        col = 3
        if data_type == 'audio': col = 4
        elif data_type == 'faces': col = 5
        self.update_item_status(file_path, col, "⬜")

    def update_item_status(self, file_path, column_index, icon_text, summary_text=None):
        root = self.invisibleRootItem()
        target_path = self.norm(file_path)

        def _find_and_update(parent):
            for i in range(parent.childCount()):
                it = parent.child(i)
                if self.norm(it.text(7)) == target_path:
                    it.setText(column_index, icon_text)
                    if icon_text == "✅":
                        it.setForeground(column_index, QBrush(QColor(COLORS['accent'])))
                    elif icon_text == "⏳":
                        it.setForeground(column_index, QBrush(QColor("#FFEB3B"))) # Yellow for processing
                    else:
                        it.setForeground(column_index, QBrush(QColor("#444")))
                    
                    if summary_text: it.setText(6, summary_text)
                    return True
                if _find_and_update(it): return True
            return False
        
        _find_and_update(root)

    def get_all_file_paths(self):
        paths = []
        root = self.invisibleRootItem()
        def _recurse(p_item):
            for i in range(p_item.childCount()):
                it = p_item.child(i)
                if it.childCount() == 0: paths.append(it.text(7))
                _recurse(it)
        _recurse(root)
        return paths
    
    def get_selected_file_paths(self):
        return [item.text(7) for item in self.selectedItems() if item.childCount() == 0]