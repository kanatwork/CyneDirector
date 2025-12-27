# [FILE: gui/search_tab.py]
import os
import cv2
import subprocess 
import sys
import random
import hashlib # <--- Added for Caching
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QListWidget, 
                             QListWidgetItem, QLabel, QHBoxLayout, QPushButton,
                             QAbstractItemView, QLayout, QSizePolicy, QScrollArea)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QMimeData, QUrl, QRect, QPoint
from PyQt6.QtGui import QPixmap, QImage, QDrag, QCursor
from config import COLORS
from core.search_engine import SearchEngine
from core.tags import get_tag_bank 
from gui.player_window import PlayerWindow

# --- HELPER: FLOW LAYOUT (Preserved) ---
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, h_spacing=10, v_spacing=10):
        super(FlowLayout, self).__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self.h_spacing = h_spacing
        self.v_spacing = v_spacing
        self.items = []

    def addItem(self, item): self.items.append(item)
    def count(self): return len(self.items)
    def itemAt(self, index): return self.items[index] if 0 <= index < len(self.items) else None
    def takeAt(self, index): return self.items.pop(index) if 0 <= index < len(self.items) else None
    
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self.do_layout(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect): super(FlowLayout, self).setGeometry(rect); self.do_layout(rect, False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self): 
        size = QSize()
        for item in self.items: size = size.expandedTo(item.minimumSize())
        return size + QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())

    def do_layout(self, rect, test_only):
        x, y = rect.x(), rect.y()
        line_height = 0
        for item in self.items:
            wid = item.widget()
            space_x = self.h_spacing
            space_y = self.v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            if not test_only: item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y()

# --- WORKER THREAD ---
class SearchWorker(QThread):
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    def __init__(self, engine, query):
        super().__init__()
        self.engine = engine; self.query = query
    def run(self):
        try:
            results = self.engine.search(self.query)
            self.results_ready.emit(results)
        except Exception as e: self.error_occurred.emit(str(e))

# --- DRAGGABLE LIST ---
class DraggableListWidget(QListWidget):
    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item: return
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if not file_path: return
        mime_data = QMimeData(); url = QUrl.fromLocalFile(file_path); mime_data.setUrls([url])
        drag = QDrag(self); drag.setMimeData(mime_data); drag.exec(Qt.DropAction.CopyAction)

# --- THUMBNAIL LOADER (OPTIMIZED WITH CACHING) ---
class ThumbnailLoader(QThread):
    thumb_ready = pyqtSignal(QListWidgetItem, QImage)

    def __init__(self, items_to_load, project_path):
        super().__init__()
        self.items = items_to_load
        self.is_running = True
        
        # Setup Cache Directory
        self.cache_dir = None
        if project_path:
            self.cache_dir = os.path.join(project_path, "_cyne_db", "thumbnails")
            os.makedirs(self.cache_dir, exist_ok=True)

    def get_cache_path(self, video_path, timestamp):
        if not self.cache_dir: return None
        # Unique hash based on file + timestamp
        unique_str = f"{video_path}_{timestamp}"
        hash_name = hashlib.md5(unique_str.encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{hash_name}.jpg")

    def run(self):
        for item, path, ts in self.items:
            if not self.is_running: break
            
            # 1. CHECK CACHE
            cache_path = self.get_cache_path(path, ts)
            if cache_path and os.path.exists(cache_path):
                q_img = QImage(cache_path)
                if not q_img.isNull():
                    self.thumb_ready.emit(item, q_img)
                    continue

            # 2. GENERATE NEW
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
                    q_img_full = QImage(frame.data, w, h, c*w, QImage.Format.Format_RGB888)
                    q_thumb = q_img_full.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    
                    # Save to cache
                    if cache_path:
                        q_thumb.save(cache_path, "JPG")
                        
                    self.thumb_ready.emit(item, q_thumb.copy())
            except: pass
            
    def stop(self): self.is_running = False

# --- MAIN TAB ---
class SearchTab(QWidget):
    def __init__(self):
        super().__init__()
        self.project_path = None
        self.player_window = None
        self.engine = None
        self.thumb_loader = None
        self.search_worker = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Header
        lbl = QLabel("SMART B-ROLL FINDER")
        lbl.setStyleSheet(f"color: {COLORS['accent']}; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        layout.addWidget(lbl)
        
        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search visuals (e.g. 'Golden hour', 'Running') or dialogue...")
        self.search_bar.returnPressed.connect(self.run_search)
        self.search_bar.setFixedHeight(50)
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{ 
                padding: 0 15px; font-size: 14px; border-radius: 8px; 
                background: #252526; border: 1px solid #444; color: white;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
            QLineEdit:disabled {{ background: #1a1a1a; color: #777; }}
        """)
        layout.addWidget(self.search_bar)
        
        # --- SUGGESTIONS AREA ---
        self.suggestions_container = QWidget()
        self.suggestions_layout = QVBoxLayout(self.suggestions_container)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_sugg = QLabel("SUGGESTED KEYWORDS")
        lbl_sugg.setStyleSheet("color: #666; font-size: 11px; font-weight: bold; margin-bottom: 5px;")
        self.suggestions_layout.addWidget(lbl_sugg)
        
        self.chips_widget = QWidget()
        self.flow_layout = FlowLayout(self.chips_widget, margin=0, h_spacing=8, v_spacing=8)
        self.suggestions_layout.addWidget(self.chips_widget)
        
        self.populate_suggestions()
        layout.addWidget(self.suggestions_container)
        
        # Info Status
        self.info_lbl = QLabel("")
        self.info_lbl.setStyleSheet("color: #777; font-size: 12px; font-weight: bold;")
        self.info_lbl.hide()
        layout.addWidget(self.info_lbl)
        
        # Results List
        self.results_list = DraggableListWidget()
        self.results_list.hide()
        self.results_list.setStyleSheet(f"""
            QListWidget {{ background: #181818; border: 1px solid #333; border-radius: 8px; outline: none; }}
            QListWidget::item {{ border-bottom: 1px solid #2A2A2A; padding: 10px; }}
            QListWidget::item:hover {{ background: #222; }}
            QListWidget::item:selected {{ background: #2A2A2A; border: 1px solid {COLORS['accent']}; }}
        """)
        layout.addWidget(self.results_list)

    def populate_suggestions(self):
        all_tags = get_tag_bank()
        random.shuffle(all_tags)
        display_tags = all_tags[:15]
        
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        for tag in display_tags:
            btn = QPushButton(tag)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, t=tag: self.search_from_chip(t))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #252526; color: #BBB; border: 1px solid #444;
                    border-radius: 12px; padding: 5px 12px; font-size: 11px; font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {COLORS['accent']}; color: #121212; border-color: {COLORS['accent']};
                }}
            """)
            self.flow_layout.addItem(self.flow_layout.addWidget(btn))

    def search_from_chip(self, text):
        self.search_bar.setText(text)
        self.run_search()

    def set_project_path(self, path):
        self.project_path = path
        if self.project_path: self.engine = SearchEngine(self.project_path)

    def run_search(self):
        query = self.search_bar.text()
        if not query or not self.engine: return
        
        if self.thumb_loader and self.thumb_loader.isRunning():
            self.thumb_loader.stop(); self.thumb_loader.wait()

        self.suggestions_container.hide()
        self.results_list.show()
        self.results_list.clear()
        self.info_lbl.show()
        self.info_lbl.setText(f"Searching for '{query}'...")
        
        self.search_bar.setDisabled(True)
        
        self.search_worker = SearchWorker(self.engine, query)
        self.search_worker.results_ready.connect(self.on_search_finished)
        self.search_worker.error_occurred.connect(self.on_search_error)
        self.search_worker.start()

    def on_search_finished(self, results):
        self.search_bar.setDisabled(False); self.search_bar.setFocus()
        self.info_lbl.setText(f"Found {len(results)} matches for '{self.search_bar.text()}'")
        
        load_queue = []
        for res in results:
            item = self.add_result_item(res)
            load_queue.append((item, res['path'], res.get('timestamp', 0)))

        # Pass project_path for Caching
        self.thumb_loader = ThumbnailLoader(load_queue, self.project_path)
        self.thumb_loader.thumb_ready.connect(self.update_thumbnail)
        self.thumb_loader.start()

    def on_search_error(self, error_msg):
        self.search_bar.setDisabled(False)
        self.info_lbl.setText(f"Search Error: {error_msg}")

    def add_result_item(self, res):
        item = QListWidgetItem(self.results_list)
        item.setSizeHint(QSize(0, 90))
        item.setData(Qt.ItemDataRole.UserRole, res['path'])
        
        widget = QWidget()
        row = QHBoxLayout(widget); row.setContentsMargins(5, 5, 5, 5); row.setSpacing(15)
        
        thumb_lbl = QLabel("Loading...")
        thumb_lbl.setFixedSize(120, 68)
        thumb_lbl.setStyleSheet("background: #111; border: 1px solid #333; color: #444; font-size: 10px;")
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(thumb_lbl); item.thumb_widget = thumb_lbl 
        
        meta_col = QVBoxLayout(); meta_col.setSpacing(4)
        filename = os.path.basename(res['path'])
        lbl_name = QLabel(filename); lbl_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #E0E0E0;")
        meta_col.addWidget(lbl_name)
        
        type_color = COLORS['accent']
        if "DIALOGUE" in res['match_type']: type_color = "#FFD700"
        elif "FILENAME" in res['match_type']: type_color = "#2196F3"
        elif "CAST" in res['match_type']: type_color = "#4CAF50"
        
        lbl_ctx = QLabel(f"<span style='color:{type_color}; font-weight:800'>[{res['match_type']}]</span> {res['context']}")
        lbl_ctx.setStyleSheet("color: #999; font-size: 11px;")
        meta_col.addWidget(lbl_ctx)
        
        score = res.get('score', 0)
        badge_color = "#2E7D32" if score > 80 else "#F57F17" if score > 50 else "#444"
        lbl_score = QLabel(f" {int(score)}% ")
        lbl_score.setFixedSize(40, 16)
        lbl_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_score.setStyleSheet(f"background-color: {badge_color}; color: white; border-radius: 3px; font-size: 9px; font-weight: bold;")
        meta_col.addWidget(lbl_score)
        
        row.addLayout(meta_col); row.addStretch()
        
        btn_col = QVBoxLayout(); btn_col.setSpacing(5)
        ts = res.get('timestamp', 0)
        btn_play = QPushButton(f"▶ {int(ts)}s" if ts > 0 else "▶ PLAY")
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(lambda: self.open_file(res['path'], ts))
        btn_play.setFixedSize(70, 28)
        btn_play.setStyleSheet(f"QPushButton {{ background: transparent; color: {COLORS['accent']}; border: 1px solid {COLORS['accent']}; border-radius: 4px; font-weight: bold; font-size: 11px; }} QPushButton:hover {{ background: {COLORS['accent']}; color: black; }}")
        btn_col.addWidget(btn_play)
        
        btn_explore = QPushButton("📂")
        btn_explore.setCursor(Qt.CursorShape.PointingHandCursor); btn_explore.setToolTip("Show in Explorer")
        btn_explore.clicked.connect(lambda: self.show_in_explorer(res['path']))
        btn_explore.setFixedSize(70, 28)
        btn_explore.setStyleSheet("QPushButton { background: transparent; border: 1px solid #444; border-radius: 4px; color: #AAA; } QPushButton:hover { border-color: #888; color: white; }")
        btn_col.addWidget(btn_explore)
        row.addLayout(btn_col)
        
        self.results_list.setItemWidget(item, widget)
        return item

    def update_thumbnail(self, item, q_image):
        if hasattr(item, 'thumb_widget'):
            item.thumb_widget.setPixmap(QPixmap.fromImage(q_image)); item.thumb_widget.setText("")

    def open_file(self, path, timestamp=0):
        if not self.player_window: self.player_window = PlayerWindow()
        self.player_window.load_video(path, timestamp)

    def show_in_explorer(self, path):
        path = os.path.normpath(path)
        if sys.platform == 'win32': subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == 'darwin': subprocess.Popen(['open', '-R', path])
        else: subprocess.Popen(['xdg-open', os.path.dirname(path)])