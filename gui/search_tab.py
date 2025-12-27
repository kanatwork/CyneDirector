import os
import cv2
import subprocess 
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QListWidget, 
                             QListWidgetItem, QLabel, QHBoxLayout, QPushButton,
                             QAbstractItemView)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QMimeData, QUrl
from PyQt6.QtGui import QPixmap, QImage, QDrag
from config import COLORS
from core.search_engine import SearchEngine
from gui.player_window import PlayerWindow

# --- CUSTOM DRAGGABLE LIST ---
class DraggableListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item: return

        # Retrieve the hidden file path from the item
        file_path = item.data(Qt.ItemDataRole.UserRole)
        
        if not file_path: return

        # Create standard MIME data (File URL)
        # This is what allows Premiere Pro / Windows Explorer to accept the drop
        mime_data = QMimeData()
        url = QUrl.fromLocalFile(file_path)
        mime_data.setUrls([url])

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        
        # Execute Drag
        drag.exec(Qt.DropAction.CopyAction)

# --- THUMBNAIL LOADER THREAD ---
class ThumbnailLoader(QThread):
    thumb_ready = pyqtSignal(QListWidgetItem, QImage)

    def __init__(self, items_to_load):
        super().__init__()
        self.items = items_to_load
        self.is_running = True

    def run(self):
        for item, path, ts in self.items:
            if not self.is_running: break
            try:
                cap = cv2.VideoCapture(path)
                if ts > 0:
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    if fps > 0: cap.set(cv2.CAP_PROP_POS_FRAMES, int(ts * fps))
                
                ret, frame = cap.read()
                cap.release()
            
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, c = frame.shape
                    
                    # --- CRITICAL OPTIMIZATION HERE ---
                    # Resize IN THE THREAD before sending to UI.
                    # This drastically reduces memory overhead and prevents UI lag.
                    q_img_full = QImage(frame.data, w, h, c*w, QImage.Format.Format_RGB888)
                    q_thumb = q_img_full.scaled(100, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    
                    # Send only the tiny thumbnail
                    self.thumb_ready.emit(item, q_thumb.copy())
            except:
                pass

    def stop(self):
        self.is_running = False

class SearchTab(QWidget):
    def __init__(self):
        super().__init__()
        self.project_path = None
        self.player_window = None
        self.engine = None
        self.thumb_loader = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        lbl = QLabel("SMART B-ROLL FINDER")
        lbl.setStyleSheet(f"color: {COLORS['accent']}; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        layout.addWidget(lbl)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search visuals (e.g. 'Golden hour', 'Running') or dialogue...")
        self.search_bar.returnPressed.connect(self.run_search)
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{ 
                padding: 12px; font-size: 14px; border-radius: 6px; 
                background: #252526; border: 1px solid #444; color: white;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
        """)
        layout.addWidget(self.search_bar)
        
        self.info_lbl = QLabel("Enter keywords to find footage.")
        self.info_lbl.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(self.info_lbl)
        
        # CHANGED: Use our custom DraggableListWidget
        self.results_list = DraggableListWidget()
        self.results_list.setStyleSheet(f"""
            QListWidget {{ background: #1E1E1E; border: 1px solid #333; border-radius: 6px; outline: none; }}
            QListWidget::item {{ border-bottom: 1px solid #2A2A2A; padding: 5px; }}
            QListWidget::item:hover {{ background: #2A2A2A; }}
            QListWidget::item:selected {{ background: #333; border: 1px solid {COLORS['accent']}; }}
        """)
        layout.addWidget(self.results_list)

    def set_project_path(self, path):
        self.project_path = path
        if self.project_path:
            self.engine = SearchEngine(self.project_path)

    def run_search(self):
        query = self.search_bar.text()
        if not query or not self.engine: return
        
        if self.thumb_loader and self.thumb_loader.isRunning():
            self.thumb_loader.stop()
            self.thumb_loader.wait()

        self.results_list.clear()
        self.info_lbl.setText("Thinking...")
        self.info_lbl.repaint()
        
        results = self.engine.search(query)
        self.info_lbl.setText(f"Found {len(results)} clips for '{query}' (Drag to Premiere to import)")
        
        load_queue = []
        for res in results:
            item = self.add_result_item_placeholder(res)
            load_queue.append((item, res['path'], res.get('timestamp', 0)))

        self.thumb_loader = ThumbnailLoader(load_queue)
        self.thumb_loader.thumb_ready.connect(self.update_thumbnail)
        self.thumb_loader.start()

    def add_result_item_placeholder(self, res):
        item = QListWidgetItem(self.results_list)
        item.setSizeHint(QSize(0, 80))
        
        # CRITICAL: Attach the file path to the item so Drag-and-Drop can find it
        item.setData(Qt.ItemDataRole.UserRole, res['path'])
        
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(5, 5, 5, 5)
        row.setSpacing(15)
        
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(100, 56)
        thumb_lbl.setStyleSheet("background: #111; border: 1px solid #333; color: #555;")
        thumb_lbl.setText("Loading...")
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(thumb_lbl)
        
        item.thumb_widget = thumb_lbl 
        
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        filename = os.path.basename(res['path'])
        lbl_name = QLabel(filename)
        lbl_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #E0E0E0;")
        
        type_color = COLORS['accent'] if "VISUAL" in res['match_type'] else "#2196F3"
        if "DIALOGUE" in res['match_type']: type_color = "#FFC107"
            
        lbl_ctx = QLabel(f"<span style='color:{type_color}; font-weight:bold'>[{res['match_type']}]</span> {res['context']}")
        lbl_ctx.setStyleSheet("color: #888; font-size: 11px;")
        
        info_layout.addWidget(lbl_name)
        info_layout.addWidget(lbl_ctx)
        row.addLayout(info_layout)
        
        row.addStretch()
        
        ts = res.get('timestamp', 0)
        btn_text = f" ▶ {int(ts)}s " if ts > 0 else " ▶ PLAY "
        
        # --- PLAY BUTTON ---
        btn_play = QPushButton(btn_text)
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(lambda: self.open_file(res['path'], ts))
        btn_play.setFixedSize(80, 30)
        btn_play.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_app']}; color: {COLORS['accent']}; 
                border: 1px solid {COLORS['accent']}; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {COLORS['accent']}; color: black; }}
        """)
        row.addWidget(btn_play)
        
        # --- SHOW IN EXPLORER BUTTON ---
        btn_explore = QPushButton("📂")
        btn_explore.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_explore.setToolTip("Show in Explorer")
        btn_explore.clicked.connect(lambda: self.show_in_explorer(res['path']))
        btn_explore.setFixedSize(30, 30)
        btn_explore.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_app']}; color: #AAA; 
                border: 1px solid #444; border-radius: 4px;
            }}
            QPushButton:hover {{ border-color: white; color: white; }}
        """)
        row.addWidget(btn_explore)

        self.results_list.setItemWidget(item, widget)
        return item

    def update_thumbnail(self, item, q_image):
        if hasattr(item, 'thumb_widget'):
            # The image is already scaled by the thread, so we just set it directly
            item.thumb_widget.setPixmap(QPixmap.fromImage(q_image))
            item.thumb_widget.setText("")

    def open_file(self, path, timestamp=0):
        if not self.player_window:
            self.player_window = PlayerWindow()
        self.player_window.load_video(path, timestamp)

    def show_in_explorer(self, path):
        path = os.path.normpath(path)
        if sys.platform == 'win32':
            subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', path])
        else:
            subprocess.Popen(['xdg-open', os.path.dirname(path)])