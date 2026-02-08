# [FILE: gui/search_tab.py]
import os
import cv2
import subprocess
import sys
import random
import hashlib
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLineEdit, QListWidget,
                             QListWidgetItem, QLabel, QHBoxLayout, QPushButton,
                             QAbstractItemView, QLayout, QSizePolicy, QScrollArea,
                             QCheckBox, QSlider, QSplitter, QGroupBox, QComboBox)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal, QMimeData, QUrl, QRect, QPoint
from PyQt6.QtGui import QPixmap, QImage, QDrag, QCursor, QColor
from config import COLORS
from core.search_engine import SearchEngine
from core.tags import get_tag_bank
from gui.player_window import PlayerWindow
from gui.theme import ANIM_FAST, ANIM_NORMAL
from gui.animations import fade_in, fade_out

# Domain-specific match-type colors (not theme tokens)
MATCH_COLOR_DIALOGUE = "#FFD700"
MATCH_COLOR_SEMANTIC = "#FFA500"
MATCH_COLOR_FILENAME = "#2196F3"
MATCH_COLOR_EMOTION  = "#E91E63"
MATCH_COLOR_OBJECT   = "#9C27B0"
MATCH_COLOR_SHOT     = "#00BCD4"

# --- HELPER: FLOW LAYOUT ---
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
    results_ready = pyqtSignal(dict)  # Changed to dict for paginated results
    error_occurred = pyqtSignal(str)
    def __init__(self, engine, query, page=1, page_size=50):
        super().__init__()
        self.engine = engine
        self.query = query
        self.page = page
        self.page_size = page_size
    def run(self):
        try:
            result = self.engine.search(self.query, page=self.page, page_size=self.page_size)
            self.results_ready.emit(result)
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

# --- THUMBNAIL LOADER ---
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
        self.current_results = []  # Store current search results
        self.current_page = 1
        self.page_size = 50
        self.total_results = 0
        self.total_pages = 0
        self.current_query = ""
        self._results_anim = None  # animation ref
        self._suggestions_anim = None  # animation ref
        self.filter_state = {
            'match_types': set(),  # Selected match types
            'score_threshold': 0,  # Minimum score (0-100)
            'duration_filter': 'all'  # 'all', 'short', 'medium', 'long'
        }
        self.saved_searches = []  # List of saved searches
        self.recent_searches = []  # Last 10 searches
        self.popular_searches = []  # Popular/frequent searches
        self.query_examples = [
            "person running",
            "golden hour",
            "close-up",
            "happy face",
            "person talking",
            "car driving",
            "sunset",
            "crowd",
            "person AND running NOT walking",
            'dialogue:"hello world"',
            "score:>80"
        ]
        self.setup_ui()
        self.load_saved_searches()
        self.load_popular_searches()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # Left side: Main content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)

        # Header
        lbl = QLabel("SMART B-ROLL FINDER")
        lbl.setStyleSheet(f"color: {COLORS['accent']}; font-size: 18px; font-weight: 900; letter-spacing: 1px;")
        content_layout.addWidget(lbl)

        # Search Bar with Save button
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search visuals (e.g. 'Golden hour', 'Running') or dialogue...")
        self.search_bar.returnPressed.connect(self.run_search)
        self.search_bar.textChanged.connect(self.on_query_changed)
        self.search_bar.setFixedHeight(50)
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{
                padding: 0 15px; font-size: 14px; border-radius: 8px;
                background: {COLORS['bg_input']}; border: 1px solid {COLORS['border']}; color: white;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
            QLineEdit:disabled {{ background: {COLORS['bg_panel']}; color: {COLORS['text_dim']}; }}
        """)
        search_row.addWidget(self.search_bar)

        # Autocomplete dropdown
        self.autocomplete_list = QListWidget()
        self.autocomplete_list.setMaximumHeight(200)
        self.autocomplete_list.hide()
        self.autocomplete_list.setStyleSheet(f"""
            QListWidget {{
                background: {COLORS['bg_input']}; border: 1px solid {COLORS['accent']};
                border-radius: 4px; color: white; font-size: 12px;
            }}
            QListWidget::item {{
                padding: 5px 10px; border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:hover {{
                background: {COLORS['surface_hover']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['accent']}; color: {COLORS['text_on_accent']};
            }}
        """)
        self.autocomplete_list.itemClicked.connect(self.select_autocomplete)
        content_layout.addWidget(self.autocomplete_list)

        # Saved searches dropdown
        self.saved_searches_combo = QComboBox()
        self.saved_searches_combo.setFixedWidth(150)
        self.saved_searches_combo.setPlaceholderText("Saved Searches")
        self.saved_searches_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 5px 10px;
                color: {COLORS['text_main']};
                font-size: 12px;
            }}
            QComboBox:hover {{
                border-color: {COLORS['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        self.saved_searches_combo.currentIndexChanged.connect(self.load_saved_search)
        search_row.addWidget(self.saved_searches_combo)

        # Save search button
        self.btn_save_search = QPushButton("\U0001f4be Save")
        self.btn_save_search.setFixedSize(80, 50)
        self.btn_save_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_search.clicked.connect(self.save_current_search)
        self.btn_save_search.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        search_row.addWidget(self.btn_save_search)

        # Query builder button
        self.btn_query_builder = QPushButton("\U0001f527 Builder")
        self.btn_query_builder.setFixedSize(90, 50)
        self.btn_query_builder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_query_builder.clicked.connect(self.open_query_builder)
        self.btn_query_builder.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 8px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        search_row.addWidget(self.btn_query_builder)

        content_layout.addLayout(search_row)

        # --- SUGGESTIONS AREA ---
        self.suggestions_container = QWidget()
        self.suggestions_layout = QVBoxLayout(self.suggestions_container)
        self.suggestions_layout.setContentsMargins(0, 0, 0, 0)

        lbl_sugg = QLabel("SUGGESTED KEYWORDS")
        lbl_sugg.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; font-weight: bold; margin-bottom: 5px;")
        self.suggestions_layout.addWidget(lbl_sugg)

        self.chips_widget = QWidget()
        self.flow_layout = FlowLayout(self.chips_widget, margin=0, h_spacing=8, v_spacing=8)
        self.suggestions_layout.addWidget(self.chips_widget)

        self.populate_suggestions()
        content_layout.addWidget(self.suggestions_container)

        # Results toolbar
        results_toolbar = QHBoxLayout()
        results_toolbar.setSpacing(10)

        # Info Status
        self.info_lbl = QLabel("")
        self.info_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px; font-weight: bold;")
        self.info_lbl.hide()
        results_toolbar.addWidget(self.info_lbl)

        # Pagination controls
        self.pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(self.pagination_widget)
        pagination_layout.setContentsMargins(0, 0, 0, 0)
        pagination_layout.setSpacing(5)

        self.btn_prev_page = QPushButton("\u25c0 Prev")
        self.btn_prev_page.setFixedSize(70, 30)
        self.btn_prev_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev_page.clicked.connect(self.go_to_prev_page)
        self.btn_prev_page.setEnabled(False)
        self.btn_prev_page.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover:enabled {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                color: {COLORS['text_disabled']};
                background: {COLORS['bg_panel']};
            }}
        """)
        pagination_layout.addWidget(self.btn_prev_page)

        self.page_label = QLabel("Page 1/1")
        self.page_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; padding: 0 10px;")
        pagination_layout.addWidget(self.page_label)

        self.btn_next_page = QPushButton("Next \u25b6")
        self.btn_next_page.setFixedSize(70, 30)
        self.btn_next_page.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_page.clicked.connect(self.go_to_next_page)
        self.btn_next_page.setEnabled(False)
        self.btn_next_page.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover:enabled {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                color: {COLORS['text_disabled']};
                background: {COLORS['bg_panel']};
            }}
        """)
        pagination_layout.addWidget(self.btn_next_page)

        self.pagination_widget.hide()  # Hide until search is performed
        results_toolbar.addWidget(self.pagination_widget)

        results_toolbar.addStretch()

        # View toggle
        self.view_toggle = QPushButton("\u2630 List")
        self.view_toggle.setCheckable(True)
        self.view_toggle.setFixedSize(80, 30)
        self.view_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_toggle.clicked.connect(self.toggle_view_mode)
        self.view_toggle.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
            }}
            QPushButton:checked {{
                background: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
            }}
        """)
        results_toolbar.addWidget(self.view_toggle)

        # Sort dropdown
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Score (High)", "Score (Low)", "Filename"])
        self.sort_combo.setFixedWidth(150)
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 5px;
                color: {COLORS['text_main']};
            }}
        """)
        self.sort_combo.currentIndexChanged.connect(self.apply_sorting)
        results_toolbar.addWidget(self.sort_combo)

        content_layout.addLayout(results_toolbar)

        # Results List/Grid
        self.results_list = DraggableListWidget()
        self.results_list.hide()
        self.results_list.setStyleSheet(f"""
            QListWidget {{ background: {COLORS['bg_app']}; border: 1px solid {COLORS['border']}; border-radius: 8px; outline: none; }}
            QListWidget::item {{ border-bottom: 1px solid {COLORS['border']}; padding: 10px; }}
            QListWidget::item:hover {{ background: {COLORS['surface_hover']}; }}
            QListWidget::item:selected {{ background: {COLORS['selection']}; border: 1px solid {COLORS['accent']}; }}
        """)
        self.is_grid_view = False
        content_layout.addWidget(self.results_list)

        main_layout.addWidget(content_widget, stretch=3)

        # Right side: Filters panel
        self.filters_panel = self.create_filters_panel()
        main_layout.addWidget(self.filters_panel, stretch=1)

    def populate_suggestions(self):
        # Combine recent searches, popular searches, and examples
        suggestions = []

        # Add recent searches (up to 5)
        suggestions.extend(self.recent_searches[:5])

        # Add popular searches (up to 5)
        suggestions.extend(self.popular_searches[:5])

        # Add query examples if we don't have enough
        if len(suggestions) < 10:
            suggestions.extend(self.query_examples[:10 - len(suggestions)])

        # Remove duplicates while preserving order
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        # Also add some tags
        all_tags = get_tag_bank()
        random.shuffle(all_tags)
        display_tags = all_tags[:max(0, 15 - len(unique_suggestions))]

        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # Add query suggestions
        for query in unique_suggestions[:10]:
            btn = QPushButton(query)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, q=query: self.search_from_chip(q))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_input']}; color: {COLORS['text_main']}; border: 1px solid {COLORS['border']};
                    border-radius: 12px; padding: 5px 12px; font-size: 11px; font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {COLORS['accent']}; color: {COLORS['text_on_accent']}; border-color: {COLORS['accent']};
                }}
            """)
            self.flow_layout.addWidget(btn)

        # Add tag chips
        for tag in display_tags:
            btn = QPushButton(tag)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, t=tag: self.search_from_chip(t))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {COLORS['bg_input']}; color: {COLORS['text_main']}; border: 1px solid {COLORS['border']};
                    border-radius: 12px; padding: 5px 12px; font-size: 11px; font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {COLORS['accent']}; color: {COLORS['text_on_accent']}; border-color: {COLORS['accent']};
                }}
            """)
            self.flow_layout.addWidget(btn)

    def search_from_chip(self, text):
        self.search_bar.setText(text)
        self.run_search()

    def set_project_path(self, path):
        self.project_path = path
        if self.project_path: self.engine = SearchEngine(self.project_path)

    def run_search(self):
        query = self.search_bar.text()
        if not query or not self.engine: return

        # Add to recent searches
        if query not in self.recent_searches:
            self.recent_searches.insert(0, query)
            self.recent_searches = self.recent_searches[:10]  # Keep last 10
            self.save_recent_searches()

        # Update popular searches (simple frequency tracking)
        if query in self.popular_searches:
            # Move to front (more popular)
            self.popular_searches.remove(query)
            self.popular_searches.insert(0, query)
        else:
            self.popular_searches.insert(0, query)
            self.popular_searches = self.popular_searches[:20]  # Keep top 20
        self.save_popular_searches()

        if self.thumb_loader and self.thumb_loader.isRunning():
            self.thumb_loader.stop(); self.thumb_loader.wait()

        # Fade out suggestions before hiding
        if self.suggestions_container.isVisible():
            self._suggestions_anim = fade_out(self.suggestions_container, duration=ANIM_FAST,
                callback=lambda: self.suggestions_container.hide())
        else:
            self.suggestions_container.hide()

        self.results_list.show()
        self.results_list.clear()
        self.info_lbl.show()
        self.info_lbl.setText(f"Searching for '{query}'...")

        self.search_bar.setDisabled(True)

        # Reset to page 1 for new search
        if query != self.current_query:
            self.current_page = 1

        self.current_query = query
        self.search_worker = SearchWorker(self.engine, query, page=self.current_page, page_size=self.page_size)
        self.search_worker.results_ready.connect(self.on_search_finished)
        self.search_worker.error_occurred.connect(self.on_search_error)
        self.search_worker.start()

    def on_search_finished(self, result_data):
        self.search_bar.setDisabled(False); self.search_bar.setFocus()

        # Handle new paginated response format
        if isinstance(result_data, dict) and 'results' in result_data:
            results = result_data['results']
            self.total_results = result_data.get('total', len(results))
            self.total_pages = result_data.get('total_pages', 1)
            self.current_page = result_data.get('page', 1)
            cache_status = " (cached)" if result_data.get('cached', False) else ""
        else:
            # Fallback for old format (backward compatibility)
            results = result_data if isinstance(result_data, list) else []
            self.total_results = len(results)
            self.total_pages = 1
            cache_status = ""

        self.current_results = results  # Store results for filtering
        self.info_lbl.setText(f"Found {self.total_results} matches for '{self.search_bar.text()}' (Page {self.current_page}/{self.total_pages}){cache_status}")

        # Apply filters and display
        self.apply_filters()

        # Update pagination controls if they exist
        self.update_pagination_controls()

    def on_search_error(self, error_msg):
        self.search_bar.setDisabled(False)
        self.info_lbl.setText(f"Search Error: {error_msg}")
        self.pagination_widget.hide()

    def update_pagination_controls(self):
        """Update pagination button states and labels."""
        if self.total_pages <= 1:
            self.pagination_widget.hide()
            return

        self.pagination_widget.show()
        self.page_label.setText(f"Page {self.current_page}/{self.total_pages}")
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < self.total_pages)

    def go_to_next_page(self):
        """Navigate to next page of results."""
        if self.current_page < self.total_pages and self.current_query:
            self.current_page += 1
            self.run_search()

    def go_to_prev_page(self):
        """Navigate to previous page of results."""
        if self.current_page > 1 and self.current_query:
            self.current_page -= 1
            self.run_search()

    def add_result_item(self, res):
        item = QListWidgetItem(self.results_list)
        item.setSizeHint(QSize(0, 90))
        item.setData(Qt.ItemDataRole.UserRole, res['path'])

        widget = QWidget()
        row = QHBoxLayout(widget); row.setContentsMargins(5, 5, 5, 5); row.setSpacing(15)

        thumb_lbl = QLabel("Loading...")
        thumb_lbl.setFixedSize(120, 68)
        thumb_lbl.setStyleSheet(f"background: {COLORS['bg_app']}; border: 1px solid {COLORS['border']}; color: {COLORS['text_disabled']}; font-size: 10px;")
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(thumb_lbl); item.thumb_widget = thumb_lbl

        meta_col = QVBoxLayout(); meta_col.setSpacing(4)
        filename = os.path.basename(res['path'])
        lbl_name = QLabel(filename); lbl_name.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {COLORS['text_main']};")
        meta_col.addWidget(lbl_name)

        type_color = COLORS['accent']
        if "DIALOGUE" in res['match_type']: type_color = MATCH_COLOR_DIALOGUE
        elif "SEMANTIC" in res['match_type']: type_color = MATCH_COLOR_SEMANTIC
        elif "FILENAME" in res['match_type']: type_color = MATCH_COLOR_FILENAME
        elif "EMOTION" in res['match_type']: type_color = MATCH_COLOR_EMOTION
        elif "OBJECT" in res['match_type']: type_color = MATCH_COLOR_OBJECT
        elif "SHOT_TYPE" in res['match_type']: type_color = MATCH_COLOR_SHOT

        # Enhanced context with match highlighting
        context_text = res.get('context', '')
        match_type_text = res.get('match_type', '')

        # Highlight match type and key terms
        context_html = f"<span style='color:{type_color}; font-weight:800'>[{match_type_text}]</span> "

        # Highlight query terms in context (if available)
        query = self.search_bar.text() if hasattr(self, 'search_bar') else ""
        if query and context_text:
            query_terms = query.lower().split()
            context_lower = context_text.lower()
            highlighted_context = context_text
            for term in query_terms:
                if len(term) > 2 and term in context_lower:
                    # Highlight term
                    import re
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    highlighted_context = pattern.sub(
                        f"<span style='background-color: {COLORS['accent']}40; font-weight: bold;'>{term}</span>",
                        highlighted_context
                    )
            context_html += highlighted_context
        else:
            context_html += context_text

        lbl_ctx = QLabel(context_html)
        lbl_ctx.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        lbl_ctx.setWordWrap(True)
        meta_col.addWidget(lbl_ctx)

        score = res.get('score', 0)
        badge_color = COLORS['success'] if score > 80 else COLORS['warning'] if score > 50 else COLORS['border']
        lbl_score = QLabel(f" {int(score)}% ")
        lbl_score.setFixedSize(40, 16)
        lbl_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_score.setStyleSheet(f"background-color: {badge_color}; color: white; border-radius: 3px; font-size: 9px; font-weight: bold;")
        meta_col.addWidget(lbl_score)

        row.addLayout(meta_col); row.addStretch()

        btn_col = QVBoxLayout(); btn_col.setSpacing(5)
        ts = res.get('timestamp', 0)
        btn_play = QPushButton(f"\u25b6 {int(ts)}s" if ts > 0 else "\u25b6 PLAY")
        btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_play.clicked.connect(lambda: self.open_file(res['path'], ts))
        btn_play.setFixedSize(70, 28)
        btn_play.setStyleSheet(f"QPushButton {{ background: transparent; color: {COLORS['accent']}; border: 1px solid {COLORS['accent']}; border-radius: 4px; font-weight: bold; font-size: 11px; }} QPushButton:hover {{ background: {COLORS['accent']}; color: {COLORS['text_on_accent']}; }}")
        btn_col.addWidget(btn_play)

        btn_explore = QPushButton("\U0001f4c2")
        btn_explore.setCursor(Qt.CursorShape.PointingHandCursor); btn_explore.setToolTip("Show in Explorer")
        btn_explore.clicked.connect(lambda: self.show_in_explorer(res['path']))
        btn_explore.setFixedSize(70, 28)
        btn_explore.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid {COLORS['border']}; border-radius: 4px; color: {COLORS['text_dim']}; }} QPushButton:hover {{ border-color: {COLORS['accent']}; color: white; }}")
        btn_col.addWidget(btn_explore)
        row.addLayout(btn_col)

        self.results_list.setItemWidget(item, widget)
        return item

    def update_thumbnail(self, item, q_image):
        if hasattr(item, 'thumb_widget'):
            item.thumb_widget.setPixmap(QPixmap.fromImage(q_image)); item.thumb_widget.setText("")

    def open_file(self, path, timestamp=0):
        """Open file in player. If main window has embedded player, use that instead."""
        # Try to use main window's embedded player if available
        if hasattr(self.parent(), 'embedded_player'):
            try:
                self.parent().embedded_player.load_video(path, timestamp)
                self.parent().embedded_player.show()
                return
            except:
                pass

        # Fallback to separate player window
        if not self.player_window:
            self.player_window = PlayerWindow()
        self.player_window.load_video(path, timestamp)
        self.player_window.show()

    def show_in_explorer(self, path):
        path = os.path.normpath(path)
        if sys.platform == 'win32': subprocess.Popen(f'explorer /select,"{path}"')
        elif sys.platform == 'darwin': subprocess.Popen(['open', '-R', path])
        else: subprocess.Popen(['xdg-open', os.path.dirname(path)])

    def create_filters_panel(self):
        """Create the filters sidebar panel."""
        panel = QWidget()
        panel.setFixedWidth(250)
        panel.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_panel']};
                border-left: 1px solid {COLORS['border']};
                padding: 15px;
            }}
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Header
        filter_header = QLabel("FILTERS")
        filter_header.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(filter_header)

        # Match Type Filters
        match_group = QGroupBox("Match Type")
        match_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: {COLORS['text_main']};
                font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """)
        match_layout = QVBoxLayout(match_group)
        match_layout.setContentsMargins(10, 15, 10, 10)

        self.match_type_checks = {}
        match_types = [
            ("VISUAL (AI)", "VISUAL (AI)"),
            ("DIALOGUE", "DIALOGUE"),
            ("DIALOGUE (SEMANTIC)", "DIALOGUE (SEMANTIC)"),
            ("FILENAME", "FILENAME"),
            ("EMOTION", "EMOTION"),
            ("OBJECT", "OBJECT"),
            ("OBJECT (YOLO)", "OBJECT (YOLO)"),
            ("SHOT_TYPE", "SHOT_TYPE"),
            ("TAG", "TAG"),
            ("DESCRIPTION", "DESCRIPTION"),
            ("CAST", "CAST"),
            ("TEMPORAL SEQUENCE", "TEMPORAL SEQUENCE"),
        ]

        for key, label in match_types:
            checkbox = QCheckBox(label)
            checkbox.setStyleSheet(f"""
                QCheckBox {{
                    color: {COLORS['text_main']};
                    font-size: 11px;
                }}
                QCheckBox::indicator {{
                    width: 16px;
                    height: 16px;
                    border: 2px solid {COLORS['border']};
                    border-radius: 3px;
                    background: {COLORS['bg_input']};
                }}
                QCheckBox::indicator:checked {{
                    background: {COLORS['accent']};
                    border-color: {COLORS['accent']};
                }}
            """)
            checkbox.stateChanged.connect(self.apply_filters)
            match_layout.addWidget(checkbox)
            self.match_type_checks[key] = checkbox

        layout.addWidget(match_group)

        # Score Threshold
        score_group = QGroupBox("Score Threshold")
        score_group.setStyleSheet(match_group.styleSheet())
        score_layout = QVBoxLayout(score_group)
        score_layout.setContentsMargins(10, 15, 10, 10)

        self.score_slider = QSlider(Qt.Orientation.Horizontal)
        self.score_slider.setRange(0, 100)
        self.score_slider.setValue(0)
        self.score_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: {COLORS['bg_input']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['accent']};
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS['accent']};
                border-radius: 3px;
            }}
        """)
        self.score_slider.valueChanged.connect(self.on_score_changed)
        score_layout.addWidget(self.score_slider)

        self.score_label = QLabel("Minimum: 0%")
        self.score_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        score_layout.addWidget(self.score_label)

        layout.addWidget(score_group)

        # Duration Filter
        duration_group = QGroupBox("Duration")
        duration_group.setStyleSheet(match_group.styleSheet())
        duration_layout = QVBoxLayout(duration_group)
        duration_layout.setContentsMargins(10, 15, 10, 10)

        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["All", "Short (< 30s)", "Medium (30s - 5m)", "Long (> 5m)"])
        self.duration_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 5px;
                color: {COLORS['text_main']};
            }}
            QComboBox:hover {{
                border-color: {COLORS['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
        """)
        self.duration_combo.currentIndexChanged.connect(self.apply_filters)
        duration_layout.addWidget(self.duration_combo)

        layout.addWidget(duration_group)

        layout.addStretch()

        # Clear Filters button
        btn_clear = QPushButton("Clear Filters")
        btn_clear.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                padding: 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        btn_clear.clicked.connect(self.clear_filters)
        layout.addWidget(btn_clear)

        return panel

    def on_score_changed(self, value):
        """Update score label when slider changes."""
        self.score_label.setText(f"Minimum: {value}%")
        self.filter_state['score_threshold'] = value
        self.apply_filters()

    def clear_filters(self):
        """Clear all filters."""
        # Clear match type checkboxes
        for checkbox in self.match_type_checks.values():
            checkbox.setChecked(False)

        # Reset score slider
        self.score_slider.setValue(0)

        # Reset duration
        self.duration_combo.setCurrentIndex(0)

        # Clear filter state
        self.filter_state = {
            'match_types': set(),
            'score_threshold': 0,
            'duration_filter': 'all'
        }

        # Reapply filters (which will show all results)
        self.apply_filters()

    def apply_filters(self):
        """Apply current filters to search results."""
        # Update filter state from UI
        self.filter_state['match_types'] = {
            key for key, checkbox in self.match_type_checks.items()
            if checkbox.isChecked()
        }

        duration_map = {0: 'all', 1: 'short', 2: 'medium', 3: 'long'}
        self.filter_state['duration_filter'] = duration_map.get(
            self.duration_combo.currentIndex(), 'all'
        )

        # Filter results
        if not self.current_results:
            return

        filtered = []
        for result in self.current_results:
            # Match type filter
            if self.filter_state['match_types']:
                match_type = result.get('match_type', '')
                # For MULTI-MODAL results, check if any constituent type is selected
                match_types_list = result.get('match_types', [match_type])
                if not (match_type in self.filter_state['match_types'] or
                        any(mt in self.filter_state['match_types'] for mt in match_types_list)):
                    continue

            # Score filter
            score = result.get('score', 0)
            if score < self.filter_state['score_threshold']:
                continue

            filtered.append(result)

        # Update display
        self.display_results(filtered)

    def toggle_view_mode(self):
        """Toggle between list and grid view."""
        self.is_grid_view = self.view_toggle.isChecked()
        if self.is_grid_view:
            self.view_toggle.setText("\u2630 Grid")
            self.results_list.setViewMode(QListWidget.ViewMode.IconMode)
            self.results_list.setSpacing(10)
            self.results_list.setGridSize(QSize(200, 180))
        else:
            self.view_toggle.setText("\u2630 List")
            self.results_list.setViewMode(QListWidget.ViewMode.ListMode)
            self.results_list.setSpacing(0)

        # Redisplay current results
        if self.current_results:
            self.apply_filters()

    def apply_sorting(self):
        """Apply sorting to current results."""
        if not self.current_results:
            return

        sort_mode = self.sort_combo.currentIndex()
        sorted_results = self.current_results.copy()

        if sort_mode == 0:  # Score High
            sorted_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        elif sort_mode == 1:  # Score Low
            sorted_results.sort(key=lambda x: x.get('score', 0))
        elif sort_mode == 2:  # Filename
            sorted_results.sort(key=lambda x: os.path.basename(x.get('path', '')))

        # Apply filters to sorted results
        self.current_results = sorted_results
        self.apply_filters()

    def display_results(self, results):
        """Display filtered results with grouping."""
        self.results_list.clear()

        if not results:
            self.info_lbl.setText("No results match the current filters.")
            return

        self.info_lbl.setText(f"Showing {len(results)} of {len(self.current_results)} results")

        # Group results by video for better organization
        results_by_video = {}
        for res in results:
            path = res['path']
            if path not in results_by_video:
                results_by_video[path] = []
            results_by_video[path].append(res)

        # Sort videos by number of results (most matches first)
        sorted_videos = sorted(results_by_video.items(), key=lambda x: len(x[1]), reverse=True)

        load_queue = []
        for video_path, video_results in sorted_videos:
            # Add group header if multiple results from same video
            if len(video_results) > 1:
                header_item = QListWidgetItem(f"\U0001f4c1 {os.path.basename(video_path)} ({len(video_results)} matches)")
                header_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Non-selectable
                header_item.setBackground(QColor(40, 40, 40))
                header_item.setForeground(QColor(COLORS['accent']))
                self.results_list.addItem(header_item)

            # Add results for this video
            for res in video_results:
                item = self.add_result_item(res)
                load_queue.append((item, res['path'], res.get('timestamp', 0)))

        if self.thumb_loader and self.thumb_loader.isRunning():
            self.thumb_loader.stop()
            self.thumb_loader.wait()

        self.thumb_loader = ThumbnailLoader(load_queue, self.project_path)
        self.thumb_loader.thumb_ready.connect(self.update_thumbnail)
        self.thumb_loader.start()

        # Fade-in results list after populating
        self._results_anim = fade_in(self.results_list, duration=ANIM_NORMAL)

    def save_current_search(self):
        """Save the current search query and filters."""
        query = self.search_bar.text()
        if not query:
            return

        # Get current filter state
        search_data = {
            'query': query,
            'match_types': list(self.filter_state['match_types']),
            'score_threshold': self.filter_state['score_threshold'],
            'duration_filter': self.filter_state['duration_filter']
        }

        # Check if already saved
        for i, saved in enumerate(self.saved_searches):
            if saved['query'] == query:
                # Update existing
                self.saved_searches[i] = search_data
                self.save_saved_searches()
                return

        # Add new
        self.saved_searches.append(search_data)
        self.save_saved_searches()
        self.update_saved_searches_combo()

    def load_saved_search(self, index):
        """Load a saved search."""
        if index < 0 or index >= len(self.saved_searches):
            return

        saved = self.saved_searches[index]
        self.search_bar.setText(saved['query'])

        # Restore filters
        for key, checkbox in self.match_type_checks.items():
            checkbox.setChecked(key in saved.get('match_types', []))

        self.score_slider.setValue(saved.get('score_threshold', 0))

        duration_map = {'all': 0, 'short': 1, 'medium': 2, 'long': 3}
        self.duration_combo.setCurrentIndex(duration_map.get(saved.get('duration_filter', 'all'), 0))

        # Run search
        self.run_search()

    def load_saved_searches(self):
        """Load saved searches from project database."""
        if not self.project_path:
            return

        import json
        search_file = os.path.join(self.project_path, "_cyne_db", "saved_searches.json")
        if os.path.exists(search_file):
            try:
                with open(search_file, 'r', encoding='utf-8') as f:
                    self.saved_searches = json.load(f)
            except:
                self.saved_searches = []
        else:
            self.saved_searches = []

        # Load recent searches
        recent_file = os.path.join(self.project_path, "_cyne_db", "recent_searches.json")
        if os.path.exists(recent_file):
            try:
                with open(recent_file, 'r', encoding='utf-8') as f:
                    self.recent_searches = json.load(f)
            except:
                self.recent_searches = []
        else:
            self.recent_searches = []

        self.update_saved_searches_combo()

    def save_saved_searches(self):
        """Save searches to project database."""
        if not self.project_path:
            return

        import json
        search_file = os.path.join(self.project_path, "_cyne_db", "saved_searches.json")
        os.makedirs(os.path.dirname(search_file), exist_ok=True)

        try:
            with open(search_file, 'w', encoding='utf-8') as f:
                json.dump(self.saved_searches, f, indent=2)
        except:
            pass

    def save_recent_searches(self):
        """Save recent searches to project database."""
        if not self.project_path:
            return

        import json
        recent_file = os.path.join(self.project_path, "_cyne_db", "recent_searches.json")
        os.makedirs(os.path.dirname(recent_file), exist_ok=True)

        try:
            with open(recent_file, 'w', encoding='utf-8') as f:
                json.dump(self.recent_searches, f, indent=2)
        except:
            pass

    def open_query_builder(self):
        """Open visual query builder dialog."""
        from gui.query_builder_dialog import QueryBuilderDialog
        dialog = QueryBuilderDialog(self, self.recent_searches, self.saved_searches)
        if dialog.exec():
            query = dialog.get_query()
            if query:
                self.search_bar.setText(query)
                self.run_search()

    def on_query_changed(self, text):
        """Handle query text changes for autocomplete."""
        if not text or len(text) < 2:
            self.autocomplete_list.hide()
            return

        # Get suggestions based on current text
        suggestions = []
        text_lower = text.lower()

        # Check recent searches
        for recent in self.recent_searches:
            if text_lower in recent.lower() and recent not in suggestions:
                suggestions.append(recent)

        # Check popular searches
        for popular in self.popular_searches:
            if text_lower in popular.lower() and popular not in suggestions:
                suggestions.append(popular)

        # Check query examples
        for example in self.query_examples:
            if text_lower in example.lower() and example not in suggestions:
                suggestions.append(example)

        # Check tags
        all_tags = get_tag_bank()
        for tag in all_tags:
            if text_lower in tag.lower() and tag not in suggestions:
                suggestions.append(tag)
                if len(suggestions) >= 8:
                    break

        # Update autocomplete list
        self.autocomplete_list.clear()
        if suggestions:
            for suggestion in suggestions[:8]:
                item = QListWidgetItem(suggestion)
                self.autocomplete_list.addItem(item)

            # Position and show autocomplete
            self.autocomplete_list.show()
            self.autocomplete_list.raise_()
        else:
            self.autocomplete_list.hide()

    def select_autocomplete(self, item):
        """Select an autocomplete suggestion."""
        query = item.text()
        self.search_bar.setText(query)
        self.autocomplete_list.hide()
        self.run_search()

    def load_popular_searches(self):
        """Load popular searches from project database."""
        if not self.project_path:
            return

        import json
        popular_file = os.path.join(self.project_path, "_cyne_db", "popular_searches.json")
        if os.path.exists(popular_file):
            try:
                with open(popular_file, 'r', encoding='utf-8') as f:
                    self.popular_searches = json.load(f)
            except:
                self.popular_searches = []
        else:
            self.popular_searches = []

    def save_popular_searches(self):
        """Save popular searches to project database."""
        if not self.project_path:
            return

        import json
        popular_file = os.path.join(self.project_path, "_cyne_db", "popular_searches.json")
        os.makedirs(os.path.dirname(popular_file), exist_ok=True)

        try:
            with open(popular_file, 'w', encoding='utf-8') as f:
                json.dump(self.popular_searches, f, indent=2)
        except:
            pass

    def update_saved_searches_combo(self):
        """Update the saved searches dropdown."""
        self.saved_searches_combo.clear()
        self.saved_searches_combo.addItem("-- Saved Searches --", None)

        for saved in self.saved_searches:
            query = saved.get('query', '')
            self.saved_searches_combo.addItem(query[:40] + ('...' if len(query) > 40 else ''), saved)
