# [FILE: gui/main_window.py]
import os
import json
import cv2
import sys
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QProgressBar, QSplitter,
                             QFileDialog, QMessageBox, QFrame,
                             QProgressDialog, QStackedWidget, QButtonGroup,
                             QMenu, QListWidget, QListWidgetItem, QCheckBox,
                             QRadioButton, QAbstractItemView, QComboBox,
                             QScrollArea, QSizePolicy,
                             QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer
from PyQt6.QtGui import QAction, QPixmap, QImage, QIcon, QColor, QShortcut, QKeySequence

from config import APP_NAME, VERSION, COLORS, FILE_EXT
from gui.media_tree import MediaTree
from gui.search_tab import SearchTab, FlowLayout
from gui.metadata_panel import MetadataPanel
from gui.activity_log import ActivityLog, LogLevel
from gui.toast_notification import ToastManager
from gui.animations import slide_width, slide_height, fade_in, fade_out, pulse_glow, scale_bounce
from gui.widgets.search_bar import SearchBar
from gui.widgets.thumbnail_card import ThumbnailCard
from gui.widgets.animated_toggle import AnimatedToggle
from gui.widgets.status_indicator import StatusIndicator
from gui.theme import (ANIM_FAST, ANIM_NORMAL, ANIM_SLOW,
                        SIDEBAR_EXPANDED, SIDEBAR_COLLAPSED)
from core.ai_models import AIBackend
from core.workflow_manager import WorkflowManager, OperationType, OperationStatus
from core.logger import get_logger

logger = get_logger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, project_path, project_name):
        super().__init__()
        logger.debug(f"Initializing MainWindow: {project_name} at {project_path}")
        self.project_path = project_path
        self.project_name = project_name
        self.project_file = os.path.join(self.project_path, f"{self.project_name}{FILE_EXT}")
        self.is_dirty = False
        
        # State tracking
        self.current_preview_path = None 
        self.worker = None
        self.import_worker = None
        self.player_window = None
        
        # Background indexing
        from core.background_indexer import BackgroundIndexer
        self.background_indexer = BackgroundIndexer(self.project_path)
        self.background_indexer.indexing_progress.connect(self.on_background_indexing_progress)
        self.background_indexer.file_indexed.connect(self.on_file_indexed)
        self.background_indexer.indexing_finished.connect(self.on_background_indexing_finished) 

        self.setWindowTitle(f"{APP_NAME} - {project_name}")
        self.resize(1600, 950)
        
        # Initialize Core Systems
        logger.debug("Initializing Database")
        from core.database import Database
        self.db = Database()
        self.db.initialize(self.project_path)
        logger.debug("Database initialized")

        # Load per-project settings
        import config as _cfg
        _cfg.load_project_settings(self.project_path)

        # Initialize Workflow Manager
        logger.debug("Initializing WorkflowManager")
        self.workflow_manager = WorkflowManager(self.project_path)
        self.workflow_manager.operation_started.connect(self.on_workflow_operation_started)
        self.workflow_manager.operation_progress.connect(self.on_workflow_operation_progress)
        self.workflow_manager.operation_finished.connect(self.on_workflow_operation_finished)
        self.workflow_manager.workflow_started.connect(self.on_workflow_started)
        self.workflow_manager.workflow_finished.connect(self.on_workflow_finished)
        logger.debug("WorkflowManager initialized and connected")
        
        # Build UI
        logger.debug("Setting up UI")
        self.setup_ui()
        logger.debug("UI setup complete, creating menu bar")
        self.create_menu_bar()
        logger.debug("Menu bar created")
        
        # Link Project Path to Tabs
        self.search_tab.set_project_path(self.project_path)
        logger.debug("Loading project")
        self.load_project()

        # File watcher — monitors project dir for new/modified videos
        self.file_watcher = None
        try:
            from workers.file_watcher import FileWatcherWorker
            self.file_watcher = FileWatcherWorker(self.project_path)
            self.file_watcher.new_file_signal.connect(self._on_watched_new_file)
            self.file_watcher.file_modified_signal.connect(self._on_watched_file_modified)
            self.file_watcher.start()
        except Exception as e:
            logger.warning(f"File watcher unavailable: {e}")

        logger.debug("MainWindow initialization complete")

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. COLLAPSIBLE SIDEBAR ───────────────────────────────────
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(SIDEBAR_EXPANDED)
        self.sidebar.setMaximumWidth(SIDEBAR_EXPANDED)
        self.sidebar_collapsed = False
        self._sidebar_anim = None  # prevent GC on animation

        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(8, 12, 8, 12)
        sb_layout.setSpacing(6)

        # Hamburger toggle button
        self.btn_toggle_sidebar = QPushButton("\u2630")  # ≡
        self.btn_toggle_sidebar.setFixedSize(40, 32)
        self.btn_toggle_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidebar.setToolTip("Toggle sidebar (Ctrl+B)")
        self.btn_toggle_sidebar.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS['text_dim']};
                font-size: 18px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_input']};
                color: {COLORS['accent']};
            }}
        """)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)
        sb_layout.addWidget(self.btn_toggle_sidebar, alignment=Qt.AlignmentFlag.AlignLeft)

        # Project name label (below hamburger)
        self.sidebar_project_label = QLabel(self.project_name)
        self.sidebar_project_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_dim']};
                font-size: 10px;
                font-weight: 600;
                background: transparent;
                padding: 0 4px;
            }}
        """)
        self.sidebar_project_label.setWordWrap(False)
        from PyQt6.QtCore import Qt as _Qt
        self.sidebar_project_label.setTextFormat(_Qt.TextFormat.PlainText)
        sb_layout.addWidget(self.sidebar_project_label)

        sb_layout.addSpacing(8)

        # Navigation buttons
        self.nav_group = QButtonGroup()
        self.nav_group.setExclusive(True)

        def create_nav_btn(icon, text, shortcut, id):
            """Create navigation button with icon and label."""
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedHeight(48)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(10, 4, 10, 4)
            btn_layout.setSpacing(10)

            icon_label = QLabel(icon)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setFixedWidth(24)
            icon_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text_dim']};
                    font-size: 20px;
                    background: transparent;
                    padding: 0px;
                }}
            """)
            btn_layout.addWidget(icon_label)

            text_label = QLabel(text.replace("\n", " "))
            text_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text_dim']};
                    font-size: 11px;
                    font-weight: 600;
                    background: transparent;
                    letter-spacing: 0.5px;
                }}
            """)
            btn_layout.addWidget(text_label, stretch=1)

            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-radius: 8px;
                }}
                QPushButton:hover {{
                    background: {COLORS['bg_input']};
                }}
                QPushButton:checked {{
                    background: {COLORS['selection']};
                    border-left: 3px solid {COLORS['accent']};
                }}
            """)

            btn.setToolTip(f"{text.replace(chr(10), ' ')} ({shortcut})")
            btn.icon_label = icon_label
            btn.text_label = text_label

            self.nav_group.addButton(btn, id)
            sb_layout.addWidget(btn)
            return btn

        self.btn_nav_media = create_nav_btn("\U0001f4c1", "MEDIA\nLIBRARY", "Ctrl+1", 0)
        self.btn_nav_search = create_nav_btn("\U0001f50d", "SMART\nSEARCH", "Ctrl+2", 1)
        self.btn_nav_faces = create_nav_btn("\U0001f464", "FACES", "Ctrl+3", 2)
        self.btn_nav_tags = create_nav_btn("\U0001f3f7\ufe0f", "TAGS", "Ctrl+4", 3)

        self._nav_buttons = [self.btn_nav_media, self.btn_nav_search,
                             self.btn_nav_faces, self.btn_nav_tags]

        # Update icon/text colors on state change
        def update_btn_style(btn, checked):
            color = COLORS['accent'] if checked else COLORS['text_dim']
            weight = 700 if checked else 600
            btn.icon_label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-size: 20px;
                    background: transparent;
                    padding: 0px;
                }}
            """)
            btn.text_label.setStyleSheet(f"""
                QLabel {{
                    color: {color};
                    font-size: 11px;
                    font-weight: {weight};
                    background: transparent;
                    letter-spacing: 0.5px;
                }}
            """)

        for nav_btn in self._nav_buttons:
            nav_btn.toggled.connect(lambda checked, b=nav_btn: update_btn_style(b, checked))

        self.nav_group.buttonClicked.connect(self.switch_tab)

        sb_layout.addStretch()

        self.version_label = QLabel(VERSION)
        self.version_label.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 9px;")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sb_layout.addWidget(self.version_label)

        main_layout.addWidget(self.sidebar)

        # ── 2. MAIN CONTENT AREA ────────────────────────────────────
        content_area = QWidget()
        ca_layout = QVBoxLayout(content_area)
        ca_layout.setContentsMargins(0, 0, 0, 0)
        ca_layout.setSpacing(0)

        # A. Command Bar (52px) — replaces old 60px top_bar
        self.top_bar = QWidget()
        self.top_bar.setStyleSheet(f"background: {COLORS['bg_app']}; border-bottom: 1px solid {COLORS['border']};")
        self.top_bar.setFixedHeight(52)
        tb_layout = QHBoxLayout(self.top_bar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(12)

        # --- LEFT: Project Info ---
        left_zone = QWidget()
        left_layout = QHBoxLayout(left_zone)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        project_icon = QLabel("\U0001f4c1")
        project_icon.setStyleSheet(f"color: {COLORS['accent']}; font-size: 14px;")
        left_layout.addWidget(project_icon)

        self.lbl_title = QLabel(self.project_name.upper())
        self.lbl_title.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-weight: 900;
            font-size: 13px;
            letter-spacing: 1.5px;
            padding: 3px 10px;
            background: {COLORS['bg_input']};
            border-radius: 6px;
            border: 1px solid {COLORS['border']};
        """)
        left_layout.addWidget(self.lbl_title)
        left_layout.addStretch()

        tb_layout.addWidget(left_zone, stretch=2)

        # --- CENTER: SearchBar ---
        self.command_search = SearchBar(placeholder="Search files or semantic query...", shortcut_key="Ctrl+K")
        self.command_search.search_submitted.connect(self._on_command_search)
        tb_layout.addWidget(self.command_search, stretch=3)

        # --- RIGHT: Workflow controls ---
        right_zone = QWidget()
        right_layout = QHBoxLayout(right_zone)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.checkbox_video = QCheckBox("Video")
        right_layout.addWidget(self.checkbox_video)

        self.checkbox_audio = QCheckBox("Audio")
        right_layout.addWidget(self.checkbox_audio)

        self.checkbox_translate = QCheckBox("Translate")
        self.checkbox_translate.setToolTip("Translate transcripts to English (requires existing transcript)")
        right_layout.addWidget(self.checkbox_translate)

        # Divider
        div1 = QFrame()
        div1.setFrameShape(QFrame.Shape.VLine)
        div1.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        div1.setFixedHeight(26)
        right_layout.addWidget(div1)

        # Speed/Accuracy toggle — AnimatedToggle + label
        self._mode_toggle = AnimatedToggle()
        self._mode_toggle.setToolTip("Speed (off) / Accuracy (on)")
        right_layout.addWidget(self._mode_toggle)

        mode_lbl = QLabel("Accuracy")
        mode_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: 600;")
        right_layout.addWidget(mode_lbl)

        # Preserve radio_speed / radio_accuracy as property aliases
        self.radio_speed = QRadioButton("Speed")
        self.radio_accuracy = QRadioButton("Accuracy")
        self.radio_speed.setChecked(True)
        self.radio_speed.hide()
        self.radio_accuracy.hide()

        # Sync toggle ↔ hidden radios
        def _sync_mode_toggle(state):
            if state:
                self.radio_accuracy.setChecked(True)
                mode_lbl.setText("Accuracy")
                mode_lbl.setStyleSheet(f"color: {COLORS['accent']}; font-size: 10px; font-weight: 600;")
            else:
                self.radio_speed.setChecked(True)
                mode_lbl.setText("Speed")
                mode_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: 600;")
        self._mode_toggle.stateChanged.connect(_sync_mode_toggle)

        # Divider
        div2 = QFrame()
        div2.setFrameShape(QFrame.Shape.VLine)
        div2.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        div2.setFixedHeight(26)
        right_layout.addWidget(div2)

        self.btn_start_indexing = QPushButton("\u25b6 START INDEXING")
        self.btn_start_indexing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_indexing.clicked.connect(self.start_indexing_from_checkboxes)
        self.btn_start_indexing.setToolTip("Start processing selected operations")
        self.btn_start_indexing.setStyleSheet(self._success_btn_style())
        right_layout.addWidget(self.btn_start_indexing)

        self.btn_start_workflow_top = QPushButton("\u25b6 START WORKFLOW")
        self.btn_start_workflow_top.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_workflow_top.clicked.connect(self.start_workflow)
        self.btn_start_workflow_top.setToolTip("Start processing queued operations")
        self.btn_start_workflow_top.hide()
        self.btn_start_workflow_top.setStyleSheet(self._success_btn_style())
        right_layout.addWidget(self.btn_start_workflow_top)

        self.workflow_badge = QLabel("")
        self.workflow_badge.setStyleSheet(f"""
            QLabel {{
                background: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
                padding: 3px 8px;
                border-radius: 10px;
                font-size: 10px;
                font-weight: bold;
                min-width: 16px;
            }}
        """)
        self.workflow_badge.hide()
        right_layout.addWidget(self.workflow_badge)

        self.btn_activity_log = QPushButton("\U0001f4cb LOG")
        self.btn_activity_log.setCheckable(True)
        self.btn_activity_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_activity_log.toggled.connect(self.toggle_activity_log)
        self.btn_activity_log.setToolTip("Toggle activity log panel")
        self.btn_activity_log.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_dim']};
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
            QPushButton:checked {{
                background: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
                border: none;
            }}
        """)
        right_layout.addWidget(self.btn_activity_log)

        self.btn_cancel = QPushButton("\u2715 CANCEL")
        self.btn_cancel.clicked.connect(self.cancel_workflow_handler)
        self.btn_cancel.hide()
        self.btn_cancel.setStyleSheet(self._error_btn_style())
        right_layout.addWidget(self.btn_cancel)

        tb_layout.addWidget(right_zone, stretch=5)

        ca_layout.addWidget(self.top_bar)

        # Workflow Queue Panel (initially hidden)
        self.workflow_panel = self.create_workflow_panel()
        ca_layout.addWidget(self.workflow_panel)

        # B. Stacked Pages
        self.pages = QStackedWidget()

        self.media_page = QWidget()
        self.setup_media_page()
        self.pages.addWidget(self.media_page)

        self.search_tab = SearchTab()
        self.pages.addWidget(self.search_tab)

        # Faces placeholder page
        self.faces_page = QWidget()
        faces_layout = QVBoxLayout(self.faces_page)
        faces_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        faces_icon = QLabel("\U0001f464")
        faces_icon.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 48px; background: transparent;")
        faces_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        faces_layout.addWidget(faces_icon)
        faces_lbl = QLabel("Faces (Coming Soon)")
        faces_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 16px; font-weight: 600; background: transparent;")
        faces_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        faces_layout.addWidget(faces_lbl)
        self.pages.addWidget(self.faces_page)

        # Tags placeholder page
        self.tags_page = QWidget()
        tags_layout = QVBoxLayout(self.tags_page)
        tags_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tags_icon = QLabel("\U0001f3f7\ufe0f")
        tags_icon.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 48px; background: transparent;")
        tags_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tags_layout.addWidget(tags_icon)
        tags_lbl = QLabel("Tags (Coming Soon)")
        tags_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 16px; font-weight: 600; background: transparent;")
        tags_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tags_layout.addWidget(tags_lbl)
        self.pages.addWidget(self.tags_page)

        ca_layout.addWidget(self.pages)

        # C. Enhanced Status Bar (32px)
        self.status_bar = QWidget()
        self.status_bar.setFixedHeight(32)
        self.status_bar.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-top: 1px solid {COLORS['border']};
        """)
        stat_layout = QHBoxLayout(self.status_bar)
        stat_layout.setContentsMargins(16, 4, 16, 4)
        stat_layout.setSpacing(10)

        self.status_icon = QLabel("\u25cf")
        self.status_icon.setStyleSheet(f"color: {COLORS['success']}; font-size: 10px;")
        stat_layout.addWidget(self.status_icon)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"""
            color: {COLORS['text_main']};
            font-weight: 600;
            font-size: 12px;
        """)
        stat_layout.addWidget(self.status_label)

        stat_layout.addStretch()

        # GPU indicator
        self.gpu_indicator = StatusIndicator("", COLORS['success'])
        self._init_gpu_indicator()
        stat_layout.addWidget(self.gpu_indicator)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        sep.setFixedHeight(16)
        stat_layout.addWidget(sep)

        # RAM indicator
        self.ram_indicator = StatusIndicator("", COLORS['accent'])
        stat_layout.addWidget(self.ram_indicator)
        self._update_ram_indicator()

        self.ram_timer = QTimer(self)
        self.ram_timer.timeout.connect(self._update_ram_indicator)
        self.ram_timer.start(30000)  # every 30s

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {COLORS['border']};
                background: {COLORS['bg_input']};
                border-radius: 8px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {COLORS['accent']}, stop:1 {COLORS['accent_hover']});
                border-radius: 7px;
            }}
        """)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        stat_layout.addWidget(self.progress_bar)

        ca_layout.addWidget(self.status_bar)

        # Activity Log Panel (initially collapsed)
        self.activity_log = ActivityLog()
        self.activity_log.hide()
        ca_layout.addWidget(self.activity_log)

        # Toast Notification Manager
        self.toast_manager = ToastManager(self)

        main_layout.addWidget(content_area)

        self.btn_nav_media.setChecked(True)
        self.pages.setCurrentIndex(0)

    def switch_tab(self, btn):
        id = self.nav_group.id(btn)
        self.pages.setCurrentIndex(id)

    # ── Sidebar collapse / expand ────────────────────────────────
    def toggle_sidebar(self):
        """Toggle sidebar between collapsed (56px) and expanded (180px)."""
        if self.sidebar_collapsed:
            target = SIDEBAR_EXPANDED
            self.sidebar_collapsed = False
        else:
            target = SIDEBAR_COLLAPSED
            self.sidebar_collapsed = True

        current_w = self.sidebar.maximumWidth()
        self._sidebar_anim = slide_width(self.sidebar, current_w, target,
                                          duration=ANIM_NORMAL,
                                          callback=self._on_sidebar_anim_done)

    def _on_sidebar_anim_done(self):
        """Update nav button labels visibility after sidebar animation."""
        collapsed = self.sidebar_collapsed
        for btn in self._nav_buttons:
            btn.text_label.setVisible(not collapsed)
        self.version_label.setVisible(not collapsed)
        self.sidebar_project_label.setVisible(not collapsed)

    # ── Command bar search ───────────────────────────────────────
    def _on_command_search(self, text):
        """Handle search from the command bar SearchBar."""
        if self.pages.currentIndex() == 0:
            # Media page: quick-filter tree by filename
            self.tree.filter_by_text(text) if hasattr(self.tree, 'filter_by_text') else None
        else:
            # Search page: delegate to search tab
            if hasattr(self.search_tab, 'search_bar'):
                self.search_tab.search_bar.setText(text)
                self.search_tab.search_bar.setFocus()
                if hasattr(self.search_tab, 'run_search'):
                    self.search_tab.run_search(text)

    # ── Grid / List view toggle ──────────────────────────────────
    def _set_media_view(self, mode):
        """Switch between 'list' and 'grid' view on the media page with crossfade."""
        if mode == self.media_view_mode:
            return
        old_index = self._left_stack.currentIndex()
        self.media_view_mode = mode
        if mode == "grid":
            if not self._grid_populated:
                self._populate_grid()
            new_index = 1
        else:
            new_index = 0

        # Crossfade: fade out old widget, switch, fade in new widget
        old_widget = self._left_stack.widget(old_index)
        new_widget = self._left_stack.widget(new_index)

        def _do_switch():
            self._left_stack.setCurrentIndex(new_index)
            self._view_anim = fade_in(new_widget, duration=ANIM_FAST)

        self._view_anim = fade_out(old_widget, duration=ANIM_FAST, callback=_do_switch)
        self._update_view_toggle_style()

    def _update_view_toggle_style(self):
        """Highlight the active view toggle button."""
        active_style = f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }}
        """
        inactive_style = f"""
            QPushButton {{
                background: transparent;
                color: {COLORS['text_dim']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """
        if self.media_view_mode == "list":
            self.btn_list_view.setStyleSheet(active_style)
            self.btn_grid_view.setStyleSheet(inactive_style)
        else:
            self.btn_grid_view.setStyleSheet(active_style)
            self.btn_list_view.setStyleSheet(inactive_style)

    def _populate_grid(self):
        """Build thumbnail cards from the tree's file list."""
        # Clear existing cards
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        files = self.tree.get_all_file_paths()
        thumb_dir = os.path.join(self.project_path, "_cyne_db", "thumbnails")

        if not files:
            # Show empty state instead of grid
            if self.media_view_mode == "grid":
                self._left_stack.setCurrentIndex(2)
            self._grid_populated = True
            return

        # Ensure grid scroll is visible (not empty state)
        if self.media_view_mode == "grid":
            self._left_stack.setCurrentIndex(1)

        for fpath in files:
            # Try to find thumbnail
            basename = os.path.splitext(os.path.basename(fpath))[0]
            thumb_path = os.path.join(thumb_dir, f"{basename}.jpg")
            if not os.path.isfile(thumb_path):
                thumb_path = None

            # Get duration from metadata
            duration = None
            status_icons = []
            try:
                data = self.db.get_video_metadata(fpath)
                if data.get("tags"):
                    status_icons.append(("\U0001f4f7", COLORS['success']))  # indexed
                if data.get("transcript"):
                    status_icons.append(("\U0001f3a4", COLORS['success']))  # transcribed
                duration = data.get("duration")
            except Exception:
                pass

            card = ThumbnailCard(fpath, thumbnail_path=thumb_path,
                                  status_icons=status_icons if status_icons else None,
                                  duration=duration)
            card.clicked.connect(self._on_grid_card_clicked)
            card.double_clicked.connect(self.open_player_from_tree)
            self.grid_layout.addWidget(card)

        self._grid_populated = True

    def _on_grid_card_clicked(self, video_path):
        """Handle grid card click — select in tree and update preview."""
        # Select the matching item in the tree
        if hasattr(self.tree, 'select_file'):
            self.tree.select_file(video_path)
        self.update_preview_panel()

    def refresh_grid(self):
        """Force grid repopulation on next switch."""
        self._grid_populated = False
        if self.media_view_mode == "grid":
            self._populate_grid()

    # ── Detail panel slide-in / collapse ─────────────────────────
    def _collapse_detail_panel(self):
        """Fade out then collapse the detail/preview panel."""
        sizes = self.media_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self._saved_splitter_sizes = list(sizes)

            def _do_collapse():
                self.media_splitter.setSizes([sizes[0] + sizes[1], 0])

            self._detail_anim = fade_out(self.preview_panel, duration=ANIM_FAST,
                                          callback=_do_collapse)

    def _expand_detail_panel(self):
        """Restore and fade in the detail/preview panel."""
        if hasattr(self, '_saved_splitter_sizes'):
            self.media_splitter.setSizes(self._saved_splitter_sizes)
        else:
            total = sum(self.media_splitter.sizes())
            self.media_splitter.setSizes([int(total * 0.65), int(total * 0.35)])
        self._detail_anim = fade_in(self.preview_panel, duration=ANIM_NORMAL)

    # ── GPU / RAM status indicators ──────────────────────────────
    def _init_gpu_indicator(self):
        """Detect GPU and set the indicator."""
        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                self.gpu_indicator.set_status(name, COLORS['success'])
                self.gpu_indicator.set_active(True)
            else:
                self.gpu_indicator.set_status("CPU Only", COLORS['warning'])
                self.gpu_indicator.set_active(False)
        except Exception:
            self.gpu_indicator.set_status("CPU Only", COLORS['warning'])
            self.gpu_indicator.set_active(False)

    def _update_ram_indicator(self):
        """Update RAM usage in status bar."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            pct = mem.percent
            color = COLORS['success'] if pct < 70 else (COLORS['warning'] if pct < 90 else COLORS['error'])
            self.ram_indicator.set_status(f"RAM {used_gb:.1f}/{total_gb:.0f} GB", color)
            self.ram_indicator.set_active(pct > 70)
        except Exception:
            self.ram_indicator.set_status("RAM N/A", COLORS['text_disabled'])

    def create_action_btn(self, text, func):
        btn = QPushButton(text)
        btn.clicked.connect(func)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{ 
                background: transparent;
                border: 1px solid {COLORS['border']}; 
                color: {COLORS['text_dim']}; padding: 6px 12px; font-size: 11px; font-weight: bold;
            }}
            QPushButton:hover {{ 
                border-color: {COLORS['accent']};
                color: {COLORS['accent']}; 
            }}
            QPushButton:disabled {{ color: {COLORS['text_disabled']}; border-color: {COLORS['border']}; }}
        """)
        return btn
    
    def create_secondary_btn(self, text, func):
        """Create a secondary action button (outlined style)."""
        btn = QPushButton(text)
        btn.clicked.connect(func)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(f"Process selected files immediately")
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_input']};
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                color: {COLORS['text_disabled']};
                border-color: {COLORS['border']};
                background: transparent;
            }}
        """)
        return btn

    @staticmethod
    def _success_btn_style():
        """Shared stylesheet for success/start buttons."""
        return f"""
            QPushButton {{
                background: {COLORS['success']};
                color: white;
                border: none;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: 800;
                border-radius: 6px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: {COLORS['success_hover']};
            }}
            QPushButton:disabled {{
                background: {COLORS['text_disabled']};
                color: {COLORS['text_dim']};
            }}
        """

    @staticmethod
    def _error_btn_style():
        """Shared stylesheet for error/cancel/stop buttons."""
        return f"""
            QPushButton {{
                background: {COLORS['error']};
                color: white;
                border: none;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 6px;
                font-size: 12px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{
                background: {COLORS['error_hover']};
            }}
        """

    def create_workflow_panel(self):
        """Create the workflow queue panel."""
        panel = QWidget()
        panel.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-bottom: 1px solid {COLORS['border']};
        """)
        panel.hide()  # Hidden by default
        panel.setMaximumHeight(0)  # Start collapsed
        
        # Store max height for animation
        panel._max_height = 180
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)
        
        # Header with status
        header_layout = QHBoxLayout()
        header_left = QHBoxLayout()
        
        header_icon = QLabel("⚙")
        header_icon.setStyleSheet(f"color: {COLORS['accent']}; font-size: 16px;")
        header_left.addWidget(header_icon)
        
        header_label = QLabel("Workflow Queue")
        header_label.setStyleSheet(f"color: {COLORS['text_main']}; font-weight: bold; font-size: 13px;")
        header_left.addWidget(header_label)
        
        self.workflow_status_label = QLabel("")
        self.workflow_status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_dim']};
                font-size: 11px;
                padding-left: 8px;
            }}
        """)
        header_left.addWidget(self.workflow_status_label)
        
        header_layout.addLayout(header_left)
        header_layout.addStretch()
        
        # Queue controls
        self.btn_start_workflow = QPushButton("▶ Start Workflow")
        self.btn_start_workflow.clicked.connect(self.start_workflow)
        self.btn_start_workflow.setToolTip("Begin processing all queued operations")
        self.btn_start_workflow.setStyleSheet(self._success_btn_style())
        header_layout.addWidget(self.btn_start_workflow)
        
        self.btn_pause_workflow = QPushButton("⏸ Pause")
        self.btn_pause_workflow.clicked.connect(self.pause_workflow)
        self.btn_pause_workflow.setToolTip("Pause current workflow")
        self.btn_pause_workflow.hide()
        self.btn_pause_workflow.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['warning']};
                color: white;
                border: none;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background: {COLORS['warning_hover']};
            }}
        """)
        header_layout.addWidget(self.btn_pause_workflow)
        
        self.btn_clear_queue = QPushButton("Clear")
        self.btn_clear_queue.clicked.connect(self.clear_workflow_queue)
        self.btn_clear_queue.setToolTip("Remove all queued operations")
        self.btn_clear_queue.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_dim']};
                padding: 6px 14px;
                font-size: 11px;
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['error']};
                color: {COLORS['error']};
            }}
        """)
        header_layout.addWidget(self.btn_clear_queue)
        
        layout.addLayout(header_layout)
        
        # Queue list with empty state (enable drag-drop for reordering)
        self.queue_list = QListWidget()
        self.queue_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.queue_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.queue_list.setStyleSheet(f"""
            QListWidget {{
                background: {COLORS['bg_app']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px;
            }}
            QListWidget::item {{
                padding: 10px;
                border-radius: 4px;
                margin: 2px;
                background: {COLORS['bg_input']};
            }}
            QListWidget::item:hover {{
                background: {COLORS['selection']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['selection']};
            }}
        """)
        self.queue_list.setMaximumHeight(150)
        self.queue_list.model().rowsMoved.connect(self.on_queue_reordered)
        layout.addWidget(self.queue_list)
        
        # Empty state message (initially hidden)
        self.empty_state_label = QLabel("No operations in queue. Select Video/Audio checkboxes and click Start Indexing.")
        self.empty_state_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_dim']};
                font-size: 11px;
                padding: 10px;
                background: {COLORS['bg_app']};
                border: 1px dashed {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state_label.hide()
        layout.addWidget(self.empty_state_label)
        
        return panel
    
    def start_indexing_from_checkboxes(self):
        """Start indexing based on checked boxes."""
        # Check if workflow is running - if so, cancel it
        if self.workflow_manager.is_running:
            self.cancel_workflow_handler()
            return
        
        files = self.tree.get_checked_file_paths()
        if not files:
            QMessageBox.warning(self, "No Selection", "Please select files using the checkboxes.")
            return
        
        # Get mode (speed or accuracy)
        mode = "accuracy" if self.radio_accuracy.isChecked() else "speed"
        
        # Clear existing queue
        self.workflow_manager.clear_queue()
        
        # Add operations based on checkboxes
        added_any = False
        if self.checkbox_video.isChecked():
            needed_ops = self.workflow_manager.get_files_needing_operations(files)
            if len(needed_ops[OperationType.INDEX_VISUALS]) > 0:
                self.workflow_manager.add_operation(OperationType.INDEX_VISUALS, 
                                                    needed_ops[OperationType.INDEX_VISUALS], 
                                                    smart_filter=False)
                added_any = True
        
        if self.checkbox_audio.isChecked():
            needed_ops = self.workflow_manager.get_files_needing_operations(files)
            if len(needed_ops[OperationType.TRANSCRIBE_AUDIO]) > 0:
                self.workflow_manager.add_operation(OperationType.TRANSCRIBE_AUDIO,
                                                   needed_ops[OperationType.TRANSCRIBE_AUDIO],
                                                   smart_filter=False)
                added_any = True
        
        if self.checkbox_translate.isChecked():
            needed_ops = self.workflow_manager.get_files_needing_operations(files)
            if len(needed_ops[OperationType.TRANSLATE_AUDIO]) > 0:
                self.workflow_manager.add_operation(OperationType.TRANSLATE_AUDIO,
                                                   needed_ops[OperationType.TRANSLATE_AUDIO],
                                                   smart_filter=False)
                added_any = True
        
        if not added_any:
            self.toast_manager.show_toast("All selected files already have the requested data.", "info")
            return
        
        # Store mode in workflow manager for workers to access
        self.workflow_manager.current_mode = mode
        
        # Start workflow
        self.start_workflow()
    
    def show_workflow_menu(self):
        """Show workflow operation menu."""
        files = self.tree.get_checked_file_paths()
        if not files:
            QMessageBox.warning(self, "No Selection", "Please select files using the checkboxes.")
            return
        
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {COLORS['bg_panel']};
                border: 1px solid {COLORS['border']};
                padding: 5px;
            }}
            QMenu::item {{
                padding: 8px 20px;
                color: {COLORS['text_main']};
            }}
            QMenu::item:selected {{
                background: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
            }}
        """)
        
        # Check what operations are needed
        needed_ops = self.workflow_manager.get_files_needing_operations(files)
        
        act_index = menu.addAction("📷 Index Visuals")
        act_index.setEnabled(len(needed_ops[OperationType.INDEX_VISUALS]) > 0)
        act_index.triggered.connect(lambda: self.add_to_workflow(OperationType.INDEX_VISUALS, files))
        
        act_transcribe = menu.addAction("🎤 Transcribe Audio")
        act_transcribe.setEnabled(len(needed_ops[OperationType.TRANSCRIBE_AUDIO]) > 0)
        act_transcribe.triggered.connect(lambda: self.add_to_workflow(OperationType.TRANSCRIBE_AUDIO, files))
        
        act_translate = menu.addAction("🌐 Translate to English")
        act_translate.setEnabled(len(needed_ops[OperationType.TRANSLATE_AUDIO]) > 0)
        act_translate.triggered.connect(lambda: self.add_to_workflow(OperationType.TRANSLATE_AUDIO, files))
        
        menu.addSeparator()
        
        act_all = menu.addAction("➕ Add All Needed")
        has_any = (len(needed_ops[OperationType.INDEX_VISUALS]) > 0 or
                   len(needed_ops[OperationType.TRANSCRIBE_AUDIO]) > 0 or
                   len(needed_ops[OperationType.TRANSLATE_AUDIO]) > 0)
        act_all.setEnabled(has_any)
        act_all.triggered.connect(lambda: self.add_all_needed_to_workflow(files, needed_ops))
        
        # This method is kept for backward compatibility but is no longer used
        # The workflow menu has been replaced with checkboxes
        # Show menu at cursor position instead
        from PyQt6.QtGui import QCursor
        menu.exec(QCursor.pos())
    
    def add_to_workflow(self, op_type: OperationType, files: list):
        """Add an operation to the workflow queue."""
        if self.workflow_manager.add_operation(op_type, files, smart_filter=True):
            self.update_workflow_queue_display()
            self._show_workflow_panel()
            self._update_start_button_visibility()
            self.activity_log.log_info(f"Added {op_type.value.replace('_', ' ').title()} to workflow queue ({len(files)} files)")
        else:
            self.toast_manager.show_toast(f"All selected files already have {op_type.value.replace('_', ' ')} data.", "info")
    
    def _update_start_button_visibility(self):
        """Update START WORKFLOW button visibility and badge."""
        
        queue_count = len(self.workflow_manager.queue)
        is_running = self.workflow_manager.is_running
        
        if queue_count > 0 and not is_running:
            self.btn_start_workflow_top.show()
            self.workflow_badge.setText(str(queue_count))
            self.workflow_badge.show()
            self.btn_start_workflow_top.setEnabled(True)
        elif is_running:
            self.btn_start_workflow_top.show()
            self.btn_start_workflow_top.setText("⏸ RUNNING...")
            self.btn_start_workflow_top.setEnabled(False)
            self.workflow_badge.hide()
        else:
            self.btn_start_workflow_top.hide()
            self.workflow_badge.hide()
            self.btn_start_workflow_top.setText("▶ START WORKFLOW")
    
    def add_all_needed_to_workflow(self, files: list, needed_ops: dict):
        """Add all needed operations to workflow."""
        added_count = 0
        # Process in order: visuals, transcription, then translation
        operation_order = [OperationType.INDEX_VISUALS, OperationType.TRANSCRIBE_AUDIO, OperationType.TRANSLATE_AUDIO]
        for op_type in operation_order:
            if op_type in needed_ops:
                op_files = needed_ops[op_type]
                if op_files and self.workflow_manager.add_operation(op_type, op_files, smart_filter=False):
                    added_count += 1
        
        if added_count > 0:
            self.update_workflow_queue_display()
            self._show_workflow_panel()
            self._update_start_button_visibility()
            self.activity_log.log_success(f"Added {added_count} operation(s) to workflow queue")
            self.toast_manager.show_toast(f"Added {added_count} operation(s) to workflow queue", "success")
        else:
            self.toast_manager.show_toast("All selected files are already fully processed.", "info")
    
    def update_workflow_queue_display(self):
        """Update the workflow queue list display."""
        
        self.queue_list.clear()
        queue_status = self.workflow_manager.get_queue_status()
        
        # Update status label
        if self.workflow_manager.is_running:
            self.workflow_status_label.setText("⏸ Running...")
            self.workflow_status_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['warning']};
                    font-size: 11px;
                    padding-left: 8px;
                    font-weight: bold;
                }}
            """)
        elif len(queue_status) > 0:
            self.workflow_status_label.setText(f"({len(queue_status)} queued)")
            self.workflow_status_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text_dim']};
                    font-size: 11px;
                    padding-left: 8px;
                }}
            """)
        else:
            self.workflow_status_label.setText("")
        
        # Show/hide empty state
        if len(queue_status) == 0:
            self.empty_state_label.show()
            self.queue_list.hide()
        else:
            self.empty_state_label.hide()
            self.queue_list.show()
        
        # Add queue items with progress bars
        for item_data in queue_status:
            # Create custom widget for rich display
            item_widget = QWidget()
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(8, 6, 8, 6)
            item_layout.setSpacing(4)
            
            # Top row: Icon, type, file count, status
            top_row = QHBoxLayout()
            
            icon_map = {
                'Index Visuals': '📷',
                'Transcribe Audio': '🎤',
                'Translate Audio': '🌐'
            }
            icon = icon_map.get(item_data['type_display'], '⚙')
            
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 16px;")
            top_row.addWidget(icon_label)
            
            type_label = QLabel(f"{item_data['type_display']} ({item_data['file_count']} files)")
            type_label.setStyleSheet(f"font-weight: bold; color: {COLORS['text_main']}; font-size: 12px;")
            top_row.addWidget(type_label)
            
            top_row.addStretch()
            
            # Status badge
            if item_data['is_current']:
                status_label = QLabel("RUNNING")
                status_label.setStyleSheet(f"""
                    background: {COLORS['warning']};
                    color: white;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 9px;
                    font-weight: bold;
                """)
            elif item_data['status'] == 'completed':
                status_label = QLabel("✓ DONE")
                status_label.setStyleSheet(f"""
                    background: {COLORS['success']};
                    color: white;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 9px;
                    font-weight: bold;
                """)
            elif item_data['status'] == 'failed':
                status_label = QLabel("✗ FAILED")
                status_label.setStyleSheet(f"""
                    background: {COLORS['error']};
                    color: white;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 9px;
                    font-weight: bold;
                """)
            else:
                status_label = QLabel("PENDING")
                status_label.setStyleSheet(f"""
                    background: {COLORS['bg_input']};
                    color: {COLORS['text_dim']};
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 9px;
                """)
            top_row.addWidget(status_label)
            
            item_layout.addLayout(top_row)
            
            # Progress bar (for current operation)
            if item_data['is_current']:
                progress_bar = QProgressBar()
                progress_bar.setRange(0, 100)
                progress_bar.setValue(item_data.get('progress', 0))
                progress_bar.setFormat(f"{item_data.get('progress', 0)}%")
                progress_bar.setStyleSheet(f"""
                    QProgressBar {{
                        border: 1px solid {COLORS['border']};
                        background: {COLORS['bg_app']};
                        border-radius: 4px;
                        height: 16px;
                        text-align: center;
                    }}
                    QProgressBar::chunk {{
                        background: {COLORS['accent']};
                        border-radius: 3px;
                    }}
                """)
                item_layout.addWidget(progress_bar)
                
                # Info row: Current file and ETR
                info_row = QHBoxLayout()
                
                current_file = item_data.get('current_file', '')
                if current_file:
                    file_label = QLabel(f"Processing: {os.path.basename(current_file)}")
                    file_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
                    info_row.addWidget(file_label)
                
                info_row.addStretch()
                
                # ETR (Estimated Time Remaining)
                etr = item_data.get('etr_seconds')
                if etr is not None:
                    etr_label = QLabel(f"~{etr}s remaining")
                    etr_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 9px; font-style: italic;")
                    info_row.addWidget(etr_label)
                
                item_layout.addLayout(info_row)
            
            # Priority indicator and controls
            if not item_data['is_current']:
                controls_row = QHBoxLayout()
                
                # Priority dropdown
                priority_combo = QComboBox()
                priority_combo.addItems(["High", "Normal", "Low"])
                priority_combo.setCurrentText(item_data.get('priority', 'normal').title())
                priority_combo.setStyleSheet(f"""
                    QComboBox {{
                        background: {COLORS['bg_app']};
                        border: 1px solid {COLORS['border']};
                        border-radius: 3px;
                        padding: 2px 5px;
                        font-size: 9px;
                        max-width: 60px;
                    }}
                """)
                priority_combo.currentTextChanged.connect(
                    lambda text, idx=item_data['index']: self.set_operation_priority(idx, text.lower())
                )
                controls_row.addWidget(priority_combo)
                
                controls_row.addStretch()
                
                # Pause/Resume button
                if item_data.get('is_paused', False):
                    pause_btn = QPushButton("▶ Resume")
                    pause_btn.clicked.connect(lambda checked, idx=item_data['index']: self.resume_operation(idx))
                else:
                    pause_btn = QPushButton("⏸ Pause")
                    pause_btn.clicked.connect(lambda checked, idx=item_data['index']: self.pause_operation(idx))
                
                pause_btn.setStyleSheet(f"""
                    QPushButton {{
                        background: transparent;
                        border: 1px solid {COLORS['border']};
                        color: {COLORS['text_main']};
                        padding: 3px 8px;
                        border-radius: 3px;
                        font-size: 9px;
                    }}
                    QPushButton:hover {{
                        border-color: {COLORS['accent']};
                        color: {COLORS['accent']};
                    }}
                """)
                controls_row.addWidget(pause_btn)
                
                item_layout.addLayout(controls_row)
            
            # Create list item
            item = QListWidgetItem()
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, item_data['index'])  # Store original index
            self.queue_list.addItem(item)
            self.queue_list.setItemWidget(item, item_widget)
        
        # Update start button state
        btn_enabled = len(queue_status) > 0 and not self.workflow_manager.is_running
        self.btn_start_workflow.setEnabled(btn_enabled)
    
    def on_queue_reordered(self, parent, start, end, destination, row):
        """Handle queue reordering via drag-drop."""
        # Get the operation index from the moved item
        moved_item = self.queue_list.item(row)
        if moved_item:
            old_index = moved_item.data(Qt.ItemDataRole.UserRole)
            # Reorder in workflow manager
            if 0 <= old_index < len(self.workflow_manager.queue):
                self.workflow_manager.reorder_operation(old_index, row)
                self.update_workflow_queue_display()
    
    def pause_workflow(self):
        """Pause the current workflow."""
        if self.workflow_manager.is_running:
            self.workflow_manager.pause_workflow()
            self.btn_pause_workflow.setText("▶ Resume")
            self.btn_pause_workflow.clicked.disconnect()
            self.btn_pause_workflow.clicked.connect(self.resume_workflow)
    
    def resume_workflow(self):
        """Resume a paused workflow."""
        if self.workflow_manager.is_running and self.workflow_manager.is_paused:
            self.workflow_manager.resume_workflow()
            self.btn_pause_workflow.setText("⏸ Pause")
            self.btn_pause_workflow.clicked.disconnect()
            self.btn_pause_workflow.clicked.connect(self.pause_workflow)
    
    def pause_operation(self, index):
        """Pause a specific operation."""
        if self.workflow_manager.pause_operation(index):
            self.update_workflow_queue_display()
    
    def resume_operation(self, index):
        """Resume a paused operation."""
        if self.workflow_manager.resume_operation(index):
            self.update_workflow_queue_display()
    
    def set_operation_priority(self, index, priority):
        """Set priority for an operation."""
        if self.workflow_manager.set_operation_priority(index, priority):
            self.update_workflow_queue_display()
    
    def start_workflow(self):
        """Start processing the workflow queue."""
        if not self.workflow_manager.queue:
            self.toast_manager.show_toast("No operations in the workflow queue.", "warning")
            return
        
        self.workflow_manager.start_workflow()
        self.btn_start_workflow.setEnabled(False)
        self.btn_start_workflow_top.setEnabled(False)
        self.btn_cancel.show()
        self.btn_pause_workflow.show()
        self._update_start_button_visibility()
    
    def clear_workflow_queue(self):
        """Clear the workflow queue."""
        if self.workflow_manager.is_running:
            QMessageBox.warning(self, "Workflow Running", "Cannot clear queue while workflow is running.")
            return
        
        reply = QMessageBox.question(self, "Clear Queue", "Clear all queued operations?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.workflow_manager.clear_queue()
            self.update_workflow_queue_display()
            self._update_start_button_visibility()
            if not self.workflow_manager.queue:
                self._hide_workflow_panel()
            self.activity_log.log_info("Workflow queue cleared")
    
    def _show_workflow_panel(self):
        """Show workflow panel with smooth animation."""
        
        if not self.workflow_panel.isVisible():
            self.workflow_panel.setMaximumHeight(0)
            self.workflow_panel.show()
            # Use QPropertyAnimation on maximumHeight
            anim = QPropertyAnimation(self.workflow_panel, b"maximumHeight")
            anim.setDuration(250)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(0)
            anim.setEndValue(self.workflow_panel._max_height)
            anim.start()
    
    def _hide_workflow_panel(self):
        """Hide workflow panel with smooth animation."""
        if self.workflow_panel.isVisible():
            current_height = self.workflow_panel.maximumHeight()
            anim = QPropertyAnimation(self.workflow_panel, b"maximumHeight")
            anim.setDuration(250)
            anim.setEasingCurve(QEasingCurve.Type.InCubic)
            anim.setStartValue(current_height)
            anim.setEndValue(0)
            anim.finished.connect(lambda: self.workflow_panel.hide())
            anim.start()
    
    def toggle_activity_log(self, checked):
        """Toggle activity log visibility with smooth animation."""
        if checked:
            self.activity_log.show()
            self.activity_log.expand(300)
        else:
            self.activity_log.collapse()
            # Note: We could hide after animation, but keeping it visible at 200px is better UX
    
    def cancel_workflow_handler(self):
        """Cancel the current workflow."""
        if self.worker and self.worker.isRunning():
            self.activity_log.log_warning("Cancelling current operation...")
            self.worker.stop()
        self.workflow_manager.cancel_workflow()
        self.btn_start_workflow.setEnabled(True)
        self.btn_cancel.hide()
        
        # Restore START INDEXING button
        self.btn_start_indexing.setText("▶ START INDEXING")
        self.btn_start_indexing.setStyleSheet(self._success_btn_style())

        self.update_workflow_queue_display()
        self._update_start_button_visibility()
        self.activity_log.log_warning("Workflow cancelled")
    
    # Workflow Manager Signal Handlers
    def on_workflow_started(self):
        """Called when workflow starts."""
        self.activity_log.log_info("Workflow started", timestamp=True)
        self.btn_start_workflow.setEnabled(False)
        self.btn_pause_workflow.show()
        self.btn_pause_workflow.setText("⏸ Pause")
        self.btn_pause_workflow.clicked.disconnect()
        self.btn_pause_workflow.clicked.connect(self.pause_workflow)

        # Change START INDEXING button to STOP
        self.btn_start_indexing.setText("⏹ STOP")
        self.btn_start_indexing.setStyleSheet(self._error_btn_style())

        self._update_start_button_visibility()

        # Pulsing glow on progress bar
        self._progress_glow = QGraphicsDropShadowEffect(self.progress_bar)
        self._progress_glow.setBlurRadius(5)
        self._progress_glow.setOffset(0, 0)
        self._progress_glow.setColor(QColor(COLORS['accent']))
        self.progress_bar.setGraphicsEffect(self._progress_glow)
        self._progress_glow_anim = pulse_glow(self._progress_glow, duration=2000)
    
    def on_workflow_finished(self):
        """Called when workflow completes."""
        self.activity_log.log_success("Workflow completed", timestamp=True)
        self.btn_start_workflow.setEnabled(True)
        self.btn_cancel.hide()
        self.btn_pause_workflow.hide()

        # Restore START INDEXING button
        self.btn_start_indexing.setText("▶ START INDEXING")
        self.btn_start_indexing.setStyleSheet(self._success_btn_style())

        self.update_workflow_queue_display()
        self._update_start_button_visibility()
        self.mark_dirty()
        self.toast_manager.show_toast("Workflow completed successfully", "success")

        # Stop progress glow
        if hasattr(self, '_progress_glow_anim') and self._progress_glow_anim:
            self._progress_glow_anim.stop()
            self._progress_glow_anim = None
        if hasattr(self, '_progress_glow'):
            self.progress_bar.setGraphicsEffect(None)

        # Success checkmark bounce near progress bar
        self._success_check = QLabel("\u2713")
        self._success_check.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['success']};
                font-size: 18px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        self._success_check.setParent(self.status_bar)
        self._success_check.move(self.progress_bar.x() + self.progress_bar.width() + 8,
                                  self.progress_bar.y() - 2)
        self._success_check.show()
        self._success_check_anim = scale_bounce(self._success_check, duration=300)
        QTimer.singleShot(1500, self._remove_success_check)
        
        # Refresh tree highlighting for all items
        self._refresh_tree_highlighting()
    
    def _remove_success_check(self):
        """Remove the success checkmark label after animation."""
        if hasattr(self, '_success_check') and self._success_check:
            self._success_check_anim2 = fade_out(self._success_check, duration=ANIM_FAST,
                callback=lambda: self._success_check.deleteLater() if self._success_check else None)

    def _refresh_tree_highlighting(self):
        """Refresh highlighting for all tree items."""
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            folder = root.child(i)
            for j in range(folder.childCount()):
                item = folder.child(j)
                if hasattr(self.tree, '_update_item_highlighting'):
                    self.tree._update_item_highlighting(item)
        
        # Refresh tree to update highlighting
        self.tree.refresh_all_statuses()
    
    def on_workflow_operation_started(self, op_type: OperationType, file_paths: list):
        """Called when an operation starts."""
        op_name = op_type.value.replace('_', ' ').title()
        self.activity_log.log_info(f"Starting {op_name} on {len(file_paths)} file(s)", timestamp=True)
        self.update_workflow_queue_display()
        self._start_worker_for_operation(op_type, file_paths)
    
    def on_workflow_operation_progress(self, op_type: OperationType, progress: int, current_file: str):
        """Called when operation progress updates."""
        if current_file:
            filename = os.path.basename(current_file)
            self.activity_log.log_info(f"Processing: {filename} ({progress}%)", timestamp=False)
        # Pass from_workflow=True to prevent recursion: this prevents update_progress from calling back into workflow_manager
        self.update_progress(progress, from_workflow=True)
        self.update_workflow_queue_display()
    
    def on_workflow_operation_finished(self, op_type: OperationType, success: bool, error_msg: str):
        """Called when an operation finishes."""
        op_name = op_type.value.replace('_', ' ').title()
        if success:
            self.activity_log.log_success(f"{op_name} completed", timestamp=True)
            self.toast_manager.show_toast(f"{op_name} completed successfully", "success")
        else:
            error_detail = f"{op_name} failed: {error_msg}" if error_msg else f"{op_name} failed"
            # Log with full error details if available
            self.activity_log.log_error(f"{op_name} failed", timestamp=True, error_details=error_msg)
            self.toast_manager.show_toast(error_detail, "error")
        self.update_workflow_queue_display()
    
    def _start_worker_for_operation(self, op_type: OperationType, file_paths: list):
        """Start the appropriate worker for the operation type."""
        if self.worker and self.worker.isRunning():
            return
        
        if op_type == OperationType.INDEX_VISUALS:
            self._start_indexer_worker(file_paths)
        elif op_type == OperationType.TRANSCRIBE_AUDIO:
            self._start_transcriber_worker(file_paths)
        elif op_type == OperationType.TRANSLATE_AUDIO:
            self._start_translate_worker(file_paths)
    
    def on_translation_complete(self, translated_segments: list):
        """Handle translation completion."""
        # Update UI to show translation is complete
        if hasattr(self, 'worker') and self.worker:
            # Get the file path from the worker
            if hasattr(self.worker, 'video_path'):
                self.tree.mark_translation_done(self.worker.video_path)
        self._refresh_tree_highlighting()

    def setup_media_page(self):
        layout = QVBoxLayout(self.media_page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        tbar = QHBoxLayout()

        btn_add = QPushButton(" + ADD FILE ")
        btn_add.setProperty("class", "accent")
        btn_add.clicked.connect(self.add_files)

        btn_folder = QPushButton(" + ADD FOLDER ")
        btn_folder.setStyleSheet(f"background: {COLORS['bg_input']}; color: white;")
        btn_folder.clicked.connect(self.add_folder)

        tbar.addWidget(btn_add)
        tbar.addWidget(btn_folder)

        tbar.addStretch()

        # Grid / List toggle buttons
        self.media_view_mode = "list"

        self.btn_list_view = QPushButton("\u2630")  # list icon
        self.btn_list_view.setFixedSize(30, 28)
        self.btn_list_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_list_view.setToolTip("List view")
        self.btn_list_view.clicked.connect(lambda: self._set_media_view("list"))
        tbar.addWidget(self.btn_list_view)

        self.btn_grid_view = QPushButton("\u25a6")  # grid icon
        self.btn_grid_view.setFixedSize(30, 28)
        self.btn_grid_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_grid_view.setToolTip("Grid view")
        self.btn_grid_view.clicked.connect(lambda: self._set_media_view("grid"))
        tbar.addWidget(self.btn_grid_view)

        self._update_view_toggle_style()

        layout.addLayout(tbar)

        # Splitter: left (tree or grid) | right (detail panel)
        self.media_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.media_splitter.setHandleWidth(1)
        self.media_splitter.setStyleSheet(f"QSplitter::handle {{ background: {COLORS['border']}; }}")

        # --- Left side: tree (list mode) ---
        self.tree = MediaTree(project_path=self.project_path)
        self.tree.itemSelectionChanged.connect(self.update_preview_panel)
        self.tree.files_dropped_signal.connect(self.handle_dropped_files)
        self.tree.clear_data_signal.connect(self.handle_clear_data)
        self.tree.double_clicked_signal.connect(self.open_player_from_tree)

        # --- Left side: grid (grid mode) ---
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {COLORS['bg_app']}; }}")
        self.grid_container = QWidget()
        self.grid_layout = FlowLayout(self.grid_container, margin=12, h_spacing=12, v_spacing=12)
        self.grid_scroll.setWidget(self.grid_container)
        self.grid_scroll.hide()  # hidden by default (list mode)
        self._grid_populated = False

        # Grid empty state
        self.grid_empty_state = QWidget()
        empty_layout = QVBoxLayout(self.grid_empty_state)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("\U0001f4c1")
        empty_icon.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 48px; background: transparent;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = QLabel("Import media to get started")
        empty_title.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 15px; font-weight: 600; background: transparent;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_sub = QLabel("Drag files or use + Add File")
        empty_sub.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 12px; background: transparent;")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_sub)
        self.grid_empty_state.hide()

        # Container to hold tree and grid (swap visibility)
        self._left_stack = QStackedWidget()
        self._left_stack.addWidget(self.tree)             # index 0 — list
        self._left_stack.addWidget(self.grid_scroll)      # index 1 — grid
        self._left_stack.addWidget(self.grid_empty_state)  # index 2 — empty state
        self._left_stack.setCurrentIndex(0)
        self._view_anim = None  # prevent GC on crossfade

        self.media_splitter.addWidget(self._left_stack)

        # --- Right side: detail / preview panel ---
        self.preview_panel = QWidget()
        self.preview_panel.setStyleSheet(f"background: {COLORS['bg_panel']}; border-left: 1px solid {COLORS['border']};")
        self._detail_anim = None  # keep animation ref

        pp_layout = QVBoxLayout(self.preview_panel)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.setSpacing(0)

        # Detail header with close button
        detail_header = QWidget()
        detail_header.setFixedHeight(32)
        detail_header.setStyleSheet(f"background: {COLORS['bg_panel']};")
        dh_layout = QHBoxLayout(detail_header)
        dh_layout.setContentsMargins(12, 4, 4, 4)
        dh_layout.setSpacing(0)

        dh_label = QLabel("Preview")
        dh_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; font-weight: 600; background: transparent;")
        dh_layout.addWidget(dh_label)
        dh_layout.addStretch()

        btn_close_detail = QPushButton("\u2715")
        btn_close_detail.setFixedSize(24, 24)
        btn_close_detail.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close_detail.setToolTip("Close detail panel")
        btn_close_detail.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {COLORS['text_dim']};
                font-size: 14px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: {COLORS['bg_input']};
                color: {COLORS['error']};
            }}
        """)
        btn_close_detail.clicked.connect(self._collapse_detail_panel)
        dh_layout.addWidget(btn_close_detail)

        pp_layout.addWidget(detail_header)

        # Embedded player
        from gui.embedded_player import EmbeddedPlayerWidget
        self.embedded_player = EmbeddedPlayerWidget()
        self.embedded_player.setMinimumHeight(300)
        self.embedded_player.fullscreen_callback = self.open_player_from_tree
        pp_layout.addWidget(self.embedded_player)

        # Keep preview_lbl for fallback
        self.preview_lbl = QLabel()
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet(f"background: {COLORS['bg_app']};")
        self.preview_lbl.setMinimumHeight(250)
        self.preview_lbl.hide()

        self.meta_panel = MetadataPanel()
        self.meta_panel.save_requested.connect(self.save_metadata_handler)
        pp_layout.addWidget(self.meta_panel)

        self.media_splitter.addWidget(self.preview_panel)
        self.media_splitter.setSizes([900, 400])

        layout.addWidget(self.media_splitter)

    def create_menu_bar(self):
        menubar = self.menuBar()
        menubar.setStyleSheet(f"QMenuBar {{ background: {COLORS['bg_panel']}; color: {COLORS['text_main']}; }} QMenuBar::item:selected {{ background: {COLORS['surface_hover']}; }}")
        
        file_menu = menubar.addMenu("File")
        
        act_new = QAction("New Project", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self.new_project_handler)
        file_menu.addAction(act_new)
        
        act_open = QAction("Open Project...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self.open_project_handler)
        file_menu.addAction(act_open)
        
        file_menu.addSeparator()
        
        act_save = QAction("Save Project", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self.save_project)
        file_menu.addAction(act_save)
        
        act_save_as = QAction("Save Project As...", self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self.save_project_as)
        file_menu.addAction(act_save_as)
        
        file_menu.addSeparator()
        
        act_export_srt = QAction("Export SRT...", self)
        act_export_srt.setShortcut("Ctrl+E")
        act_export_srt.triggered.connect(self.export_srt_handler)
        file_menu.addAction(act_export_srt)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        act_settings = QAction("Settings...", self)
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self.show_settings)
        edit_menu.addAction(act_settings)

        # Help menu
        help_menu = menubar.addMenu("Help")
        
        act_shortcuts = QAction("Keyboard Shortcuts...", self)
        act_shortcuts.setShortcut("Ctrl+?")
        act_shortcuts.triggered.connect(self.show_shortcuts_panel)
        help_menu.addAction(act_shortcuts)
        
        act_help = QAction("Help", self)
        act_help.setShortcut("F1")
        act_help.triggered.connect(self.show_shortcuts_panel)  # Show shortcuts as help for now
        help_menu.addAction(act_help)
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts for the main window."""
        # Navigation
        QShortcut(QKeySequence("Ctrl+1"), self, self.switch_to_media)
        QShortcut(QKeySequence("Ctrl+2"), self, self.switch_to_search)
        QShortcut(QKeySequence("Ctrl+F"), self, self.focus_search)
        
        # Media operations
        QShortcut(QKeySequence("Ctrl+I"), self, self.add_files)
        QShortcut(QKeySequence("Ctrl+Shift+I"), self, self.add_folder)
        QShortcut(QKeySequence("Ctrl+A"), self, self.select_all_files)
        
        # Workflow
        QShortcut(QKeySequence("Ctrl+R"), self, self.start_indexing_from_checkboxes)
        QShortcut(QKeySequence("Escape"), self, self.handle_escape)
        QShortcut(QKeySequence("Ctrl+L"), self, self.toggle_activity_log_shortcut)
        
        # General (some already in menu, but adding here for consistency)
        QShortcut(QKeySequence("Ctrl+?"), self, self.show_shortcuts_panel)
        QShortcut(QKeySequence("F1"), self, self.show_shortcuts_panel)
    
    def switch_to_media(self):
        """Switch to Media Library tab."""
        self.btn_nav_media.setChecked(True)
        self.pages.setCurrentIndex(0)
    
    def switch_to_search(self):
        """Switch to Smart Search tab."""
        self.btn_nav_search.setChecked(True)
        self.pages.setCurrentIndex(1)
    
    def focus_search(self):
        """Focus the search bar if in Search tab."""
        if self.pages.currentIndex() == 1:  # Search tab
            self.search_tab.search_bar.setFocus()
    
    def select_all_files(self):
        """Select all files in the media tree."""
        if self.pages.currentIndex() == 0:  # Media tab
            self.tree.toggle_all(True)
    
    def handle_escape(self):
        """Handle Escape key - cancel current operation or close dialogs."""
        if self.workflow_manager.is_running:
            self.cancel_workflow_handler()
    
    def toggle_activity_log_shortcut(self):
        """Toggle activity log via keyboard shortcut."""
        self.btn_activity_log.setChecked(not self.btn_activity_log.isChecked())
    
    def show_shortcuts_panel(self):
        """Show the keyboard shortcuts panel."""
        from gui.shortcuts_panel import ShortcutsPanel
        panel = ShortcutsPanel(self)
        panel.exec()

    def show_settings(self):
        """Open the settings dialog."""
        import config as _cfg
        from gui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(_cfg._settings, self.project_path, parent=self)
        if dlg.exec():
            self._apply_settings_changes()

    def _apply_settings_changes(self):
        """Sync runtime config after settings are saved."""
        import config as _cfg
        # Update USE_BLIP2 at runtime
        _cfg.USE_BLIP2 = (_cfg.get_setting("blip_variant") == "blip-2")
        _cfg.GENERATE_PROXIES = _cfg.get_setting("generate_proxies", False)
        # Update DeepL key
        deepl_key = _cfg.get_setting("deepl_api_key", "")
        _cfg.DEEPL_API_KEY = deepl_key
        _cfg.TRANSLATION_METHOD = "deepl" if deepl_key else "whisper"
        logger.debug("Settings applied to runtime config")

    def open_project_handler(self):
        """Handle Open Project menu action."""
        QMessageBox.information(self, "Open Project", 
                              "To open a different project, please restart the application.\n\n"
                              "Or use File > New Project to create a new one.")

    # --- CORE HANDLERS ---
    def update_preview_panel(self):
        paths = self.tree.get_selected_file_paths()
        if not paths:
            # When clicking empty space, keep the embedded player playing the last selected video
            # Only clear the metadata panel, don't stop/hide the player
            # Clear metadata panel but keep player running
            self.meta_panel.clear()
            # Don't clear current_preview_path - keep it so the player continues playing
            # Don't stop or hide the embedded player - let it continue playing
            return
        
        # Check if multiple files selected (bulk mode)
        if len(paths) > 1:
            # Bulk edit mode
            self.current_preview_path = None
            # Clear current_file_path FIRST to prevent fullscreen callback from opening player with stale path
            if hasattr(self.embedded_player, 'current_file_path'):
                self.embedded_player.current_file_path = None
            try:
                self.embedded_player.stop()
            except AttributeError:
                # media_player might not be initialized yet
                pass
            self.embedded_player.hide()
            self.preview_lbl.show()
            self.preview_lbl.setText(f"{len(paths)} files selected")
            
            # Load tags from first file for bulk editing
            try:
                first_path = paths[0]
                data = self.db.get_video_metadata(first_path)
                tags = data.get("tags", [])
                summary = data.get("summary", "")
                self.meta_panel.load_data(first_path, tags, summary, file_paths=paths)
            except:
                self.meta_panel.load_data(None, [], "", file_paths=paths)
            return
        
        file_path = paths[0]
        self.current_preview_path = file_path 
        
        # Load video in embedded player (auto-play)
        try:
            self.embedded_player.load_video(file_path, 0)
            self.embedded_player.show()
            self.preview_lbl.hide()
        except Exception as e:
            # Fallback to static thumbnail if player fails
            print(f"Player error: {e}")
            self.embedded_player.hide()
            self.preview_lbl.show()
            
            try:
                cap = cv2.VideoCapture(file_path)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total > 0:
                    target_frame = 100 if total > 120 else total // 2
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = cap.read()
                cap.release()
                
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame.shape
                    bytes_per_line = ch * w
                    qt_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                    pix = QPixmap.fromImage(qt_img)
                    scaled_pix = pix.scaled(self.preview_lbl.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.preview_lbl.setPixmap(scaled_pix)
                else:
                    self.preview_lbl.setText("No Preview")
            except:
                self.preview_lbl.setText("Preview unavailable")

        # 2. Load Metadata
        tags = []
        summary = ""
        try:
            data = self.db.get_video_metadata(file_path)
            tags = data.get("tags", [])
            summary = data.get("summary", "")
            
            if not summary:
                trans_data = data.get("transcript", [])
                if isinstance(trans_data, list) and trans_data:
                    preview_text = " ".join([seg['text'] for seg in trans_data[:10]])
                    summary = f"(Auto-Transcript): {preview_text}..."
        except Exception as e:
            print(f"Meta load error: {e}")
            
        self.meta_panel.load_data(file_path, tags, summary)

    def save_metadata_handler(self, new_tags, new_summary):
        if not self.current_preview_path: return
        try:
            self.db.save_tags(self.current_preview_path, new_tags, new_summary)
            if new_tags:
                self.tree.mark_visuals_done(self.current_preview_path, new_summary)
            
            # Efficient Update: Only update this file in the index
            self.search_tab.engine.build_index([self.current_preview_path])
            
            self.status_label.setText(f"Saved metadata for {os.path.basename(self.current_preview_path)}")
            self.mark_dirty()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save metadata: {e}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Video Files", "", "Video (*.mp4 *.mov *.mxf *.braw *.avi)")
        if files:
            self.status_label.setText(f"Adding {len(files)} files...")
            self.tree.add_files_flat(files)
            
            # OPTIMIZATION: Only add NEW files to the search index
            self.search_tab.engine.build_index(files)
            
            self.mark_dirty() 
            self.status_label.setText(f"Added {len(files)} files.")
            self.toast_manager.show_toast(f"Added {len(files)} file(s) to project", "success")

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Import")
        if not folder: return
        self.start_import_worker([folder], is_folder=True)
        
    def handle_dropped_files(self, local_urls):
        valid_files = []
        folders = []
        valid_exts = {'.mp4', '.mov', '.mxf', '.braw', '.avi'}
        
        for path in local_urls:
            if os.path.isdir(path):
                folders.append(path)
            elif os.path.splitext(path)[1].lower() in valid_exts:
                valid_files.append(path)
                
        if valid_files:
            self.tree.add_files_flat(valid_files)
            # OPTIMIZATION: Only add NEW files
            self.search_tab.engine.build_index(valid_files) 
            self.mark_dirty()
        
        if folders:
            self.start_import_worker(folders, is_folder=True)

    def start_import_worker(self, paths, is_folder=False):
        self.import_progress = QProgressDialog("Scanning for media...", "Cancel", 0, 0, self)
        self.import_progress.setWindowTitle("Importing Media")
        self.import_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self.import_progress.setMinimumWidth(350)
        self.import_progress.show()

        try:
            from workers.importer import FolderImportWorker
            self.import_worker = FolderImportWorker(paths[0]) 
            self.import_worker.progress_signal.connect(self.update_import_label)
            self.import_worker.finished_signal.connect(self.on_import_finished)
            self.import_worker.start()
        except ImportError:
            QMessageBox.critical(self, "Error", "Could not load workers/importer.py")
            self.import_progress.close()

    def update_import_label(self, text):
        self.import_progress.setLabelText(text)

    def on_import_finished(self, files):
        self.import_progress.close()
        if files:
            self.status_label.setText(f"Importing {len(files)} files into tree...")
            self.tree.add_files_flat(files) 
            # OPTIMIZATION: Add new files to search index
            self.search_tab.engine.build_index(files)
            
            # Add to background indexing queue (high priority for newly imported files)
            self.background_indexer.add_files(files, priority=2, force=False)
            
            self.mark_dirty()
            self.status_label.setText(f"Added {len(files)} files.")
            self.toast_manager.show_toast(f"Added {len(files)} file(s) to project", "success")
            
            # Start background indexing if not already running
            if not self.background_indexer.background_timer.isActive():
                self.background_indexer.start_background_indexing()
        else:
            self.toast_manager.show_toast("No video files found in selected folder.", "warning")

    def handle_clear_data(self, files, data_type):
        confirm = QMessageBox.question(self, "Confirm Clear", f"Are you sure you want to clear {data_type} data for {len(files)} files?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.No: return
        
        keys_map = {'visuals': ['tags', 'summary'], 'audio': ['transcript', 'summary']}
        keys = keys_map.get(data_type, [])
        for fpath in files:
            self.db.clear_metadata_keys(fpath, keys)
            self.tree.reset_status(fpath, data_type)
            
        self.update_preview_panel()
        self.status_label.setText(f"Cleared {data_type} for {len(files)} files.")

    def mark_dirty(self):
        self.is_dirty = True
        self.setWindowTitle(f"{APP_NAME} - {self.project_name} *")

    def save_project(self):
        files = self.tree.get_all_file_paths()
        data = {"version": "2.0", "files": files}
        try:
            with open(self.project_file, 'w') as f: json.dump(data, f, indent=4)
            self.status_label.setText(f"Project saved ({len(files)} files).")
            self.is_dirty = False
            self.setWindowTitle(f"{APP_NAME} - {self.project_name}")
            self.toast_manager.show_toast(f"Project saved ({len(files)} files)", "success")
            return True
        except Exception as e: 
            QMessageBox.warning(self, "Save Error", str(e))
            return False
            
    def save_project_as(self):
        fpath, _ = QFileDialog.getSaveFileName(self, "Save Project As", self.project_path, f"Cyne Project (*{FILE_EXT})")
        if fpath:
            self.project_file = fpath
            self.project_name = os.path.basename(fpath).replace(FILE_EXT, "")
            self.save_project()

    def new_project_handler(self):
        QMessageBox.information(self, "New Project", "To create a new project, please restart the application.")

    def export_srt_handler(self):
        """Export SRT files for selected files or all files."""
        files = self.tree.get_checked_file_paths()
        if not files:
            # If no files selected, ask if user wants to export all
            reply = QMessageBox.question(self, "No Selection", 
                                       "No files selected. Export SRT for all files?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                files = self.tree.get_all_file_paths()
            else:
                return
        
        # Filter files that have transcripts
        files_with_transcripts = []
        for fpath in files:
            meta = self.db.get_video_metadata(fpath)
            if meta.get("transcript"):
                files_with_transcripts.append(fpath)
        
        if not files_with_transcripts:
            self.toast_manager.show_toast("Selected files do not have transcripts. Please transcribe audio first.", "warning")
            return
        
        # Choose export directory
        export_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory", 
                                                      self.project_path)
        if not export_dir:
            return
        
        # Export SRT files
        from core.srt_exporter import SRTExporter
        transcripts_dict = {}
        for fpath in files_with_transcripts:
            meta = self.db.get_video_metadata(fpath)
            transcripts_dict[fpath] = meta.get("transcript", [])
        
        results = SRTExporter.export_multiple_transcripts(transcripts_dict, export_dir)
        
        # Show results
        success_count = sum(1 for success in results.values() if success)
        if success_count == len(results):
            self.toast_manager.show_toast(f"Successfully exported {success_count} SRT file(s)", "success")
        else:
            failed_count = len(results) - success_count
            self.toast_manager.show_toast(f"Exported {success_count} file(s). {failed_count} failed.", "warning")

    def load_project(self):
        if os.path.exists(self.project_file):
            try:
                with open(self.project_file, 'r') as f:
                    data = json.load(f)
                    files = data.get("files", [])
                    if files: 
                        self.tree.add_files_flat(files)
                        # Build index for loaded files
                        self.search_tab.engine.build_index(files)
            except: pass

    def closeEvent(self, event):
        # 1. STOP WORKERS
        if self.file_watcher and self.file_watcher.isRunning():
            self.file_watcher.stop()
            self.file_watcher.wait(3000)
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

        # 2. UNLOAD AI
        AIBackend().unload_models()
        
        # 3. SAVE CHECK
        if self.is_dirty:
            reply = QMessageBox.question(self, "Unsaved Changes", "Save before quitting?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if reply == QMessageBox.StandardButton.Save:
                if self.save_project(): event.accept()
                else: event.ignore()
            elif reply == QMessageBox.StandardButton.Discard: event.accept()
            else: event.ignore()
        else: event.accept()

    # --- WORKER HANDLERS ---
    def lock_buttons(self, locked):
        """Lock/unlock workflow buttons."""
        # Lock checkboxes and start button
        if hasattr(self, 'checkbox_video'):
            self.checkbox_video.setDisabled(locked)
            self.checkbox_audio.setDisabled(locked)
            if hasattr(self, 'checkbox_translate'):
                self.checkbox_translate.setDisabled(locked)
            self.btn_start_indexing.setDisabled(locked)
            self.radio_speed.setDisabled(locked)
            self.radio_accuracy.setDisabled(locked)

    def cancel_worker(self):
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Stopping worker...")
            self.worker.stop()

    def worker_finished(self):
        self.lock_buttons(False)
        self.progress_bar.hide()
        current_text = self.status_label.text()
        if "CRITICAL" not in current_text and "Error" not in current_text:
            self.status_label.setText("Task Complete")
            self.status_icon.setStyleSheet(f"color: {COLORS['success']}; font-size: 10px;")
        else:
            self.status_icon.setStyleSheet(f"color: {COLORS['error']}; font-size: 10px;")
        self.mark_dirty()
        
        # Update search index with any new metadata found
        files_processed = self.get_files_to_process() # This is approximate, but safe
        if files_processed:
            self.search_tab.engine.build_index(files_processed)
        
        # Notify workflow manager if operation is running
        if hasattr(self, 'workflow_manager') and self.workflow_manager.current_operation:
            op_type = self.workflow_manager.current_operation.op_type
            success = "CRITICAL" not in current_text and "Error" not in current_text
            error_msg = current_text if not success else None
            self.workflow_manager.on_operation_finished(op_type, success, error_msg)
        
        # Wait for thread to finish before deleting
        if self.worker and self.worker.isRunning():
            self.worker.wait(5000)  # Wait up to 5 seconds
        
        self.worker = None
        self.update_preview_panel()

    def on_background_indexing_progress(self, message, percent):
        """Handle background indexing progress updates."""
        if percent >= 0:
            self.status_label.setText(f"Background: {message} ({percent}%)")
        else:
            self.status_label.setText(f"Background: {message}")
    
    def on_file_indexed(self, video_path):
        """Handle completion of background file indexing."""
        # Refresh search index for this file
        if hasattr(self, 'search_tab') and self.search_tab.engine:
            self.search_tab.engine.build_index([video_path])
        
        # Update tree status if needed
        if hasattr(self, 'tree'):
            self.tree.update_file_status(video_path)
    
    def _start_background_indexing_scan(self):
        """Start initial background indexing scan."""
        try:
            new_count = self.background_indexer.scan_for_new_files()
            if new_count > 0:
                self.status_label.setText(f"Found {new_count} files to index in background")
                self.background_indexer.start_background_indexing()
        except Exception as e:
            print(f"Background indexing scan error: {e}")
    
    def on_background_indexing_finished(self):
        """Handle background indexing queue completion."""
        status = self.background_indexer.get_queue_status()
        if status['queue_size'] == 0:
            self.status_label.setText("Background indexing complete")

    # --- FILE WATCHER HANDLERS ---

    def _on_watched_new_file(self, video_path):
        """A new video file appeared in the project directory."""
        logger.info(f"File watcher: new file detected — {video_path}")
        self.tree.add_files_flat([video_path])
        self.search_tab.engine.build_index([video_path])
        self.mark_dirty()
        self.background_indexer.add_file(video_path, priority=2)
        if not self.background_indexer.background_timer.isActive():
            self.background_indexer.start_background_indexing()
        self.activity_log.log_info(f"New file detected: {os.path.basename(video_path)}")

    def _on_watched_file_modified(self, video_path):
        """An existing video file was modified in the project directory."""
        logger.info(f"File watcher: file modified — {video_path}")
        self.background_indexer.add_file(video_path, priority=1, force=True)
        if not self.background_indexer.background_timer.isActive():
            self.background_indexer.start_background_indexing()
        self.activity_log.log_info(f"File modified, re-indexing: {os.path.basename(video_path)}")

    def update_log_status(self, msg):
        self.status_label.setText(msg)
        # Update status icon based on message
        if "CRITICAL" in msg or "Error" in msg or "Failed" in msg:
            self.status_icon.setStyleSheet(f"color: {COLORS['error']}; font-size: 10px;")
        elif "Complete" in msg or "Success" in msg:
            self.status_icon.setStyleSheet(f"color: {COLORS['success']}; font-size: 10px;")
        elif "Running" in msg or "Processing" in msg:
            self.status_icon.setStyleSheet(f"color: {COLORS['warning']}; font-size: 10px;")
        else:
            self.status_icon.setStyleSheet(f"color: {COLORS['accent']}; font-size: 10px;")
        
        # Also log to activity log
        if hasattr(self, 'activity_log'):
            self.activity_log.log_info(msg, timestamp=False)

    def update_progress(self, val, from_workflow=False):
        """Update progress bar. If from_workflow is True, don't call back into workflow manager."""
        if self.progress_bar.isHidden(): self.progress_bar.show()
        self.progress_bar.setValue(val)
        
        # Update workflow manager if operation is running (but NOT if we're being called FROM workflow)
        # This prevents infinite recursion: workflow emits signal → update_progress → workflow.on_operation_progress → emits signal again
        if not from_workflow and hasattr(self, 'workflow_manager') and self.workflow_manager.current_operation:
            current_file = None
            if hasattr(self, 'worker') and self.worker:
                # Try to get current file from worker if available
                if hasattr(self.worker, 'current_file'):
                    current_file = self.worker.current_file
            
            op_type = self.workflow_manager.current_operation.op_type
            self.workflow_manager.on_operation_progress(op_type, val, current_file)
        
    def update_visuals_status(self, path, summary_text):
        self.tree.mark_visuals_done(path, summary_text)
        if self.current_preview_path and path:
            if os.path.normpath(path).lower() == os.path.normpath(self.current_preview_path).lower():
                self.update_preview_panel()

    def update_audio_status(self, path):
        self.tree.mark_audio_done(path)
        if self.current_preview_path and os.path.normpath(path) == os.path.normpath(self.current_preview_path):
            self.update_preview_panel()


    def open_player_from_tree(self, file_path=None):
        """Opens the player window when a file is double-clicked or fullscreen is requested."""
        
        # Check if this was called from clicking empty space (no explicit file_path and no selection)
        selected_paths = self.tree.get_selected_file_paths()
        
        # CRITICAL: If no file_path was explicitly passed AND no selection, don't open player window
        # This prevents the player window from opening when clicking empty space
        if not file_path and not selected_paths:
            return
        
        if not file_path:
            file_path = self.current_preview_path
        
        if not file_path:
            return
        
        # Verify the file still exists and is valid
        if not os.path.exists(file_path):
            return
        
        # Only open player if there's actually a file selected (not when clicking empty space)
        # If file_path was explicitly passed (e.g., from double-click), use it
        # Otherwise, only open if there's a current selection
        selected_paths = self.tree.get_selected_file_paths()
        
        # CRITICAL: Only open player if file_path was explicitly passed OR there's a current selection
        # If file_path is None or empty, and there's no selection, don't open the player
        if not file_path and not selected_paths:
            return
        
        # If file_path is None but we have selected_paths, use the first selected path
        if not file_path and selected_paths:
            file_path = selected_paths[0]
        
        # Final check: ensure we have a valid file_path
        if not file_path or not os.path.exists(file_path):
            return
        
        if not self.player_window:
            from gui.player_window import PlayerWindow
            self.player_window = PlayerWindow()
        
        # Get current position from embedded player if available
        start_time = 0
        if hasattr(self, 'embedded_player') and hasattr(self.embedded_player, 'media_player') and self.embedded_player.media_player and self.embedded_player.media_player.duration() > 0:
            start_time = self.embedded_player.media_player.position() / 1000.0
        self.player_window.load_video(file_path, start_time)
        self.player_window.show()

    def get_files_to_process(self, check_key=None):
        
        selected = self.tree.get_checked_file_paths()
        if not selected:
            if check_key: # Only warn if we are actually trying to run a job
                QMessageBox.warning(self, "No Selection", "Please verify that the checkboxes next to the files are ticked.")
            return []
        
        # Initialize filtered to avoid UnboundLocalError
        filtered = []
        
        if check_key:
            
            for path in selected:
                meta = self.db.get_video_metadata(path)
                # Skip files that already have this data key
                if check_key == 'tags' and meta.get('tags'): continue
                if check_key == 'transcript' and meta.get('transcript'): continue
                if check_key == 'faces' and meta.get('faces'): continue
                filtered.append(path)
            
            if len(filtered) < len(selected) and not filtered:
                self.toast_manager.show_toast(f"All selected files have already been scanned for {check_key}.", "info")
                return []
            return filtered
        return selected

    def _start_indexer_worker(self, files):
        """Start indexer worker (used by workflow manager)."""
        if self.worker and self.worker.isRunning(): return
        
        from workers.indexer import IndexerWorker
        mode = getattr(self.workflow_manager, 'current_mode', 'speed')
        self.worker = IndexerWorker(files, self.project_path, mode=mode)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.update_log_status)
        self.worker.finished_signal.connect(self.worker_finished)
        self.worker.summary_signal.connect(self.update_visuals_status)
        self.worker.start()
    
    def _start_transcriber_worker(self, files):
        """Start transcriber worker (used by workflow manager)."""
        if self.worker and self.worker.isRunning(): return
        
        from workers.transcriber import TranscriberWorker
        mode = getattr(self.workflow_manager, 'current_mode', 'speed')
        self.worker = TranscriberWorker(files, self.project_path, mode=mode)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.update_log_status)
        self.worker.finished_signal.connect(self.worker_finished)
        self.worker.file_finished_signal.connect(self.update_audio_status)
        self.worker.start()
    
    def _start_translate_worker(self, files):
        """Start translation worker (used by workflow manager)."""
        if self.worker and self.worker.isRunning(): return
        
        from workers.transcribe_translate_worker import TranscribeTranslateWorker
        from config import DEEPL_API_KEY
        mode = getattr(self.workflow_manager, 'current_mode', 'speed')
        
        # Process all files sequentially
        # Store files list for batch processing
        if files:
            self.translation_files = files
            self.current_translation_index = 0
            self._process_next_translation_file()
    
    def _process_next_translation_file(self):
        """Process next file in translation batch."""
        if not hasattr(self, 'translation_files') or not hasattr(self, 'current_translation_index'):
            return
        
        if self.current_translation_index >= len(self.translation_files):
            # All files processed
            self.worker_finished()
            return
        
        file_path = self.translation_files[self.current_translation_index]
        from workers.transcribe_translate_worker import TranscribeTranslateWorker
        from config import DEEPL_API_KEY
        mode = getattr(self.workflow_manager, 'current_mode', 'speed')
        
        # Calculate base progress for this file
        total_files = len(self.translation_files)
        base_progress = int((self.current_translation_index / total_files) * 100)
        
        self.worker = TranscribeTranslateWorker(
            file_path,
            self.project_path,
            deepl_api_key=DEEPL_API_KEY,
            mode=mode,
            should_transcribe=False,  # Only translate, don't re-transcribe
            should_translate=True
        )
        
        # Wrap progress signal to account for batch processing
        def update_batch_progress(progress):
            # Scale progress to account for current file position in batch
            scaled_progress = base_progress + int((progress / 100) * (100 / total_files))
            self.update_progress(scaled_progress)
        
        self.worker.progress_signal.connect(update_batch_progress)
        self.worker.log_signal.connect(self.update_log_status)
        # Connect finished to process next file instead of worker_finished
        self.worker.finished_signal.connect(self.on_translation_file_finished)
        self.worker.translation_complete_signal.connect(self.on_translation_complete)
        self.worker.start()
    
    def on_translation_file_finished(self, success: bool, error_msg: str):
        """Handle completion of a single translation file, then process next."""
        if hasattr(self, 'current_translation_index') and hasattr(self, 'translation_files'):
            file_path = self.translation_files[self.current_translation_index]
            if success:
                self.tree.mark_translation_done(file_path)
                self.update_audio_status(file_path)  # Refresh status
            self.current_translation_index += 1
            
            # Update progress
            total_files = len(self.translation_files)
            progress = int((self.current_translation_index / total_files) * 100)
            self.update_progress(progress)
            
            # Process next file
            if self.current_translation_index < len(self.translation_files):
                self._process_next_translation_file()
            else:
                # All files done
                self.worker_finished()
    
    # Direct processing methods (quick actions)
    def run_indexing_direct(self):
        """Run indexing immediately without queue."""
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another operation is already running.")
            return
        files = self.get_files_to_process(check_key='tags')
        if not files: return
        self._start_indexer_worker(files)
    
    def run_transcription_direct(self):
        """Run transcription immediately without queue."""
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another operation is already running.")
            return
        files = self.get_files_to_process(check_key='transcript')
        if not files: return
        self._start_transcriber_worker(files)
    
    # Legacy methods (kept for backward compatibility)
    def run_indexing(self):
        """Legacy method - adds to workflow instead."""
        files = self.get_files_to_process(check_key='tags')
        if not files: return
        self.add_to_workflow(OperationType.INDEX_VISUALS, files)

    def run_transcription(self):
        """Legacy method - adds to workflow instead."""
        files = self.get_files_to_process(check_key='transcript')
        if not files: return
        self.add_to_workflow(OperationType.TRANSCRIBE_AUDIO, files)
