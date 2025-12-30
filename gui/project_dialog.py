# [FILE: gui/project_dialog.py]
import os
import json
import re
import sys
from datetime import datetime
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QFileDialog, QLineEdit, QMessageBox, QFrame,
                             QScrollArea, QWidget, QListWidget, QListWidgetItem, QMenu)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QCursor, QColor
from PyQt6.QtWidgets import QApplication
from config import COLORS, APP_NAME, FILE_EXT, VERSION
from core.project_manager import ProjectManager
from core.logger import get_logger

logger = get_logger(__name__)

class ProjectDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setFixedSize(900, 650)  # Increased height to accommodate all buttons
        self.project_manager = ProjectManager()
        
        # Modern Dark Theme Stylesheet
        self.setStyleSheet(f"""
            QDialog {{ 
                background-color: {COLORS['bg_app']}; 
                color: {COLORS['text_main']};
            }}
            
            /* LABELS */
            QLabel.header {{ 
                font-size: 24px; font-weight: 900; 
                color: {COLORS['accent']}; letter-spacing: 1.5px;
                margin-bottom: 5px;
            }}
            QLabel.sub-label {{ 
                color: {COLORS['text_dim']}; 
                font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;
                margin-top: 15px;
            }}
            
            /* INPUTS - FIXED CLIPPING */
            QLineEdit {{ 
                background-color: {COLORS['bg_input']}; 
                border: 1px solid {COLORS['border']}; 
                border-radius: 6px; 
                padding: 0px 12px;
                min-height: 40px; 
                color: white; font-size: 13px;
                selection-background-color: {COLORS['accent']};
                selection-color: black;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
            
            /* BUTTONS - Base style */
            QPushButton {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
                min-height: 35px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_panel']};
                border-color: {COLORS['accent']};
            }}
            
            /* Primary button - use objectName instead of class */
            QPushButton[primary="true"] {{
                background-color: {COLORS['accent']}; 
                color: #121212; 
                font-weight: 800; 
                font-size: 13px;
                border-radius: 6px; 
                min-height: 45px; 
                border: none; 
                letter-spacing: 0.5px;
            }}
            QPushButton[primary="true"]:hover {{
                background-color: {COLORS['accent_hover']};
            }}
            
            /* Secondary button */
            QPushButton[secondary="true"] {{
                background-color: {COLORS['bg_panel']}; 
                border: 1px solid {COLORS['border']}; 
                color: {COLORS['text_main']};
                border-radius: 6px; 
                padding: 0 15px; 
                font-size: 12px;
                min-height: 40px;
            }}
            QPushButton[secondary="true"]:hover {{
                border-color: {COLORS['accent']}; 
                color: {COLORS['accent']};
            }}

            /* Ghost button */
            QPushButton[ghost="true"] {{
                background-color: transparent; 
                border: none; 
                color: {COLORS['text_main']}; 
                font-weight: 600;
                padding: 8px 12px;
                min-height: 35px;
            }}
            QPushButton[ghost="true"]:hover {{
                color: {COLORS['accent']}; 
                background-color: {COLORS['bg_input']};
                border-radius: 4px;
            }}
        """)
        
        self.selected_project_path = None
        self.project_name = None
        
        self.setup_ui()
        logger.debug("Project dialog setup complete")
    
    def showEvent(self, event):
        """Handle dialog show event."""
        super().showEvent(event)
        logger.debug("Project dialog shown")
        
    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Header (spans both panels)
        header_widget = QWidget()
        header_widget.setStyleSheet(f"background: {COLORS['bg_panel']}; border-bottom: 1px solid {COLORS['border']};")
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 20, 30, 20)
        header_layout.setSpacing(5)
        
        title = QLabel(APP_NAME.upper())
        title.setProperty("class", "header")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {COLORS['accent']}; font-size: 28px; font-weight: 900; letter-spacing: 2px;")
        header_layout.addWidget(title)
        
        subtitle = QLabel(f"Version {VERSION}")
        subtitle.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle)
        
        # 2. Two-Panel Layout
        panels_layout = QHBoxLayout()
        panels_layout.setSpacing(0)
        panels_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left Panel: Create New Project (60%)
        left_panel = self.create_left_panel()
        panels_layout.addWidget(left_panel, stretch=6)
        
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"background: {COLORS['border']}; max-width: 1px;")
        panels_layout.addWidget(divider)
        
        # Right Panel: Recent Projects (40%)
        right_panel = self.create_right_panel()
        panels_layout.addWidget(right_panel, stretch=4)
        
        # Combine header and panels
        content_layout = QVBoxLayout()
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(header_widget)
        content_layout.addLayout(panels_layout)
        
        main_layout.addLayout(content_layout)
    
    def create_left_panel(self):
        """Create the left panel for creating new projects."""
        panel = QWidget()
        panel.setStyleSheet(f"background: {COLORS['bg_app']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(12)
        
        # Section header
        header = QLabel("CREATE NEW PROJECT")
        header.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 14px; font-weight: 800; letter-spacing: 1px;")
        layout.addWidget(header)
        
        # Project Name
        lbl_name = QLabel("Project Name")
        lbl_name.setProperty("class", "sub-label")
        layout.addWidget(lbl_name)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Nike_Summer_Campaign")
        layout.addWidget(self.name_input)
        
        # Location
        lbl_loc = QLabel("Location")
        lbl_loc.setProperty("class", "sub-label")
        layout.addWidget(lbl_loc)
        
        loc_row = QHBoxLayout()
        loc_row.setSpacing(10)
        
        self.loc_input = QLineEdit()
        self.loc_input.setReadOnly(True)
        self.loc_input.setPlaceholderText("Where should we save it?")
        loc_row.addWidget(self.loc_input, stretch=1)
        
        btn_browse = QPushButton("Browse")
        btn_browse.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_browse.clicked.connect(self.browse_location)
        btn_browse.setFixedHeight(40)
        btn_browse.setFixedWidth(100)
        btn_browse.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_panel']}; 
                border: 1px solid {COLORS['border']}; 
                color: {COLORS['text_main']};
                border-radius: 6px; 
                font-size: 12px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']}; 
                color: {COLORS['accent']};
            }}
        """)
        loc_row.addWidget(btn_browse)
        
        layout.addLayout(loc_row)
        
        layout.addSpacing(20)
        
        # Create Button - Use direct stylesheet instead of property selector
        self.btn_create = QPushButton("CREATE PROJECT")
        self.btn_create.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_create.clicked.connect(self.create_project)
        self.btn_create.setFixedHeight(45)
        self.btn_create.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent']}; 
                color: #121212; 
                font-weight: 800; 
                font-size: 13px;
                border-radius: 6px; 
                border: none; 
                letter-spacing: 0.5px;
                padding: 10px 20px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['accent']};
            }}
        """)
        layout.addWidget(self.btn_create)
        
        # Divider
        div_layout = QHBoxLayout()
        div_layout.setContentsMargins(0, 15, 0, 15)
        div_layout.setSpacing(0)
        
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        line1.setFixedHeight(1)
        
        lbl_or = QLabel("OR")
        lbl_or.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_or.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; padding: 0 15px;")
        lbl_or.setFixedWidth(50)
        
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        line2.setFixedHeight(1)
        
        div_layout.addWidget(line1, stretch=1)
        div_layout.addWidget(lbl_or)
        div_layout.addWidget(line2, stretch=1)
        layout.addLayout(div_layout)
        
        # Open Existing Button - Add border/box
        btn_open = QPushButton("Open Existing Project")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(self.open_project)
        btn_open.setFixedHeight(35)
        btn_open.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                font-weight: 600;
                padding: 8px 12px;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                color: {COLORS['accent']};
                background-color: {COLORS['selection']};
                border-color: {COLORS['accent']};
            }}
        """)
        layout.addWidget(btn_open)
        return panel
    
    def create_right_panel(self):
        """Create the right panel for recent projects."""
        panel = QWidget()
        panel.setStyleSheet(f"background: {COLORS['bg_panel']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        
        # Section header
        header = QLabel("RECENT PROJECTS")
        header.setStyleSheet(f"color: {COLORS['text_main']}; font-size: 14px; font-weight: 800; letter-spacing: 1px;")
        layout.addWidget(header)
        
        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)
        
        self.recent_list = QListWidget()
        self.recent_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Prevent horizontal scroll
        self.recent_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background: {COLORS['bg_input']};
                border-radius: 8px;
                padding: 0px;
                margin: 6px 0;
                min-height: 70px;
                border: none;
            }}
            QListWidget::item QWidget {{
                width: 100%;
                background: transparent;
            }}
            QListWidget::item:hover {{
                background: {COLORS['selection']};
                border: 1px solid {COLORS['accent']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['selection']};
                border: 1px solid {COLORS['accent']};
            }}
        """)
        self.recent_list.itemDoubleClicked.connect(self.on_recent_project_clicked)
        self.recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self.show_recent_context_menu)
        
        scroll.setWidget(self.recent_list)
        layout.addWidget(scroll)
        
        # Load recent projects
        self.load_recent_projects()
        
        return panel
    
    def load_recent_projects(self):
        """Load and display recent projects."""
        self.recent_list.clear()
        recent_projects = self.project_manager.get_recent_projects()
        
        if not recent_projects:
            # Empty state
            empty_item = QListWidgetItem("No recent projects")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setForeground(QColor(COLORS['text_dim']))
            self.recent_list.addItem(empty_item)
            return
        
        for project in recent_projects:
            item = QListWidgetItem()
            
            # Create custom widget for project card
            card = QWidget()
            card.setStyleSheet(f"""
                QWidget {{
                    background: transparent;
                }}
            """)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 14, 14, 14)  # Move padding from item to card
            card_layout.setSpacing(12)
            
            # Left side: Icon
            icon_container = QWidget()
            icon_container.setFixedSize(40, 40)
            icon_container.setStyleSheet(f"""
                QWidget {{
                    background: {COLORS['bg_panel']};
                    border-radius: 8px;
                    border: 1px solid {COLORS['border']};
                }}
            """)
            icon_layout = QVBoxLayout(icon_container)
            icon_layout.setContentsMargins(0, 0, 0, 0)
            icon_label = QLabel("📁")
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 20px;
                    background: transparent;
                }}
            """)
            icon_layout.addWidget(icon_label)
            card_layout.addWidget(icon_container)
            
            # Right side: Project info
            info_layout = QVBoxLayout()
            info_layout.setContentsMargins(0, 0, 0, 0)
            info_layout.setSpacing(6)
            
            # Project name - larger, bolder
            name_label = QLabel(project['name'])
            name_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLORS['text_main']};
                    font-size: 15px;
                    font-weight: 700;
                    letter-spacing: 0.3px;
                }}
            """)
            name_label.setWordWrap(True)
            name_label.setTextFormat(Qt.TextFormat.PlainText)
            info_layout.addWidget(name_label)
            
            # Date modified - refined styling
            last_accessed = project.get('last_accessed', 0)
            if last_accessed:
                dt = datetime.fromtimestamp(last_accessed)
                time_ago = self._format_time_ago(dt)
                time_label = QLabel(f"Modified {time_ago}")
                time_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLORS['text_dim']};
                        font-size: 11px;
                        font-weight: 500;
                        letter-spacing: 0.2px;
                    }}
                """)
                time_label.setWordWrap(False)
                info_layout.addWidget(time_label)
            
            info_layout.addStretch()
            card_layout.addLayout(info_layout, stretch=1)
            
            # Store full path in tooltip for the entire card
            original_path = project['path']
            card.setToolTip(f"Path: {original_path}")
            
            # Set item size hint
            card.adjustSize()
            item.setSizeHint(QSize(card.sizeHint().width(), max(70, card.sizeHint().height())))
            self.recent_list.addItem(item)
            self.recent_list.setItemWidget(item, card)
            
            # Store project path in item data
            item.setData(Qt.ItemDataRole.UserRole, project['path'])
    
    def _format_time_ago(self, dt):
        """Format datetime as relative time (e.g., '2d ago', '1w ago')."""
        now = datetime.now()
        diff = now - dt
        
        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                minutes = diff.seconds // 60
                return f"{minutes}m ago" if minutes > 0 else "just now"
            return f"{hours}h ago"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            return f"{weeks}w ago"
        elif diff.days < 365:
            months = diff.days // 30
            return f"{months}mo ago"
        else:
            years = diff.days // 365
            return f"{years}y ago"
    
    def on_recent_project_clicked(self, item):
        """Handle double-click on recent project."""
        project_path = item.data(Qt.ItemDataRole.UserRole)
        if project_path:
            project_file = os.path.join(project_path, f"{os.path.basename(project_path)}.cyne")
            if os.path.exists(project_file):
                self.selected_project_path = project_path
                self.project_name = os.path.basename(project_path)
                # Update last accessed
                self.project_manager.add_recent_project(project_path, self.project_name)
                self.accept()
            else:
                QMessageBox.warning(self, "Project Not Found", 
                                  f"Project file not found:\n{project_file}\n\nRemoving from recent list.")
                self.project_manager.remove_recent_project(project_path)
                self.load_recent_projects()
    
    def show_recent_context_menu(self, position):
        """Show context menu for recent project item."""
        item = self.recent_list.itemAt(position)
        if not item or not item.data(Qt.ItemDataRole.UserRole):
            return
        
        project_path = item.data(Qt.ItemDataRole.UserRole)
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
                color: #121212;
            }}
        """)
        
        act_open = menu.addAction("Open")
        act_open.triggered.connect(lambda: self.on_recent_project_clicked(item))
        
        menu.addSeparator()
        
        act_remove = menu.addAction("Remove from List")
        act_remove.triggered.connect(lambda: self.remove_recent_project(project_path))
        
        act_show = menu.addAction("Show in Explorer")
        act_show.triggered.connect(lambda: self.show_in_explorer(project_path))
        
        menu.exec(self.recent_list.mapToGlobal(position))
    
    def remove_recent_project(self, project_path):
        """Remove project from recent list."""
        self.project_manager.remove_recent_project(project_path)
        self.load_recent_projects()
    
    def show_in_explorer(self, project_path):
        """Show project in file explorer."""
        if sys.platform == 'win32':
            os.startfile(project_path)
        elif sys.platform == 'darwin':
            import subprocess
            subprocess.Popen(['open', project_path])
        else:
            import subprocess
            subprocess.Popen(['xdg-open', project_path])

    def browse_location(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Parent Folder")
        if folder:
            self.loc_input.setText(folder)

    def sanitize_filename(self, name):
        # Remove invalid chars for Windows/Linux filenames
        return re.sub(r'[<>:"/\\|?*]', '', name).strip()

    def create_project(self):
        parent_folder = self.loc_input.text()
        raw_name = self.name_input.text()
        name = self.sanitize_filename(raw_name)
        
        if not parent_folder or not name:
            QMessageBox.warning(self, "Missing Info", "Please enter a project name and select a parent folder.")
            return
            
        # --- ROBUSTNESS FIX: Create a dedicated subfolder ---
        # Instead of creating the file directly in 'Documents', create 'Documents/ProjectName/'
        project_dir = os.path.join(parent_folder, name)
        
        try:
            # 1. Create the Project Directory
            os.makedirs(project_dir, exist_ok=True)
            
            # 2. Check if project file already exists
            project_file = os.path.join(project_dir, f"{name}{FILE_EXT}")
            if os.path.exists(project_file):
                QMessageBox.warning(self, "Error", f"A project named '{name}' already exists in that folder.")
                return

            # 3. Initialize Project JSON
            with open(project_file, 'w') as f:
                f.write(json.dumps({"version": "2.0", "files": []}, indent=4))
            
            # 4. Pre-create Database Directory (Optional but good for permissions check)
            os.makedirs(os.path.join(project_dir, "_cyne_db"), exist_ok=True)
            
            self.selected_project_path = project_dir
            self.project_name = name
            # Add to recent projects
            self.project_manager.add_recent_project(project_dir, name)
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create project:\n{e}")

    def open_project(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", f"Cyne Project (*{FILE_EXT})")
        if fpath:
            self.selected_project_path = os.path.dirname(fpath)
            self.project_name = os.path.basename(fpath).replace(FILE_EXT, "")
            # Add to recent projects
            self.project_manager.add_recent_project(self.selected_project_path, self.project_name)
            self.accept()