import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QFileDialog, QLineEdit, QMessageBox, QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from config import COLORS, APP_NAME, FILE_EXT

class ProjectDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Welcome to {APP_NAME}")
        self.setFixedSize(500, 480)
        
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
                padding: 0px 12px; /* No vertical padding to prevent clip */
                min-height: 40px;  /* Explicit height */
                color: white; font-size: 13px;
                selection-background-color: {COLORS['accent']};
                selection-color: black;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
            
            /* BUTTONS */
            QPushButton.primary {{ 
                background-color: {COLORS['accent']}; 
                color: #121212; font-weight: 800; font-size: 13px;
                border-radius: 6px; min-height: 45px; border: none; letter-spacing: 0.5px;
            }}
            QPushButton.primary:hover {{ background-color: {COLORS['accent_hover']}; }}
            
            QPushButton.secondary {{ 
                background-color: {COLORS['bg_panel']}; 
                border: 1px solid {COLORS['border']}; 
                color: {COLORS['text_main']};
                border-radius: 6px; padding: 0 15px; font-size: 12px;
                min-height: 40px;
            }}
            QPushButton.secondary:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}

            QPushButton.ghost {{ 
                background-color: transparent; border: none; 
                color: {COLORS['text_dim']}; font-weight: 600;
            }}
            QPushButton.ghost:hover {{ color: {COLORS['accent']}; text-decoration: none; }}
        """)
        
        self.selected_project_path = None
        self.project_name = None
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(45, 45, 45, 45)
        
        # 1. Header
        title = QLabel(APP_NAME.upper())
        title.setProperty("class", "header")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(f"Version 2.0 (Redux)")
        subtitle.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; margin-bottom: 20px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        
        # 2. Project Name
        lbl_name = QLabel("Project Name")
        lbl_name.setProperty("class", "sub-label")
        layout.addWidget(lbl_name)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Nike_Summer_Campaign")
        layout.addWidget(self.name_input)

        # 3. Location
        lbl_loc = QLabel("Location")
        lbl_loc.setProperty("class", "sub-label")
        layout.addWidget(lbl_loc)

        loc_row = QHBoxLayout()
        loc_row.setSpacing(10)
        
        self.loc_input = QLineEdit()
        self.loc_input.setReadOnly(True)
        self.loc_input.setPlaceholderText("Select folder...")
        loc_row.addWidget(self.loc_input)
        
        btn_browse = QPushButton("Browse")
        btn_browse.setProperty("class", "secondary")
        btn_browse.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_browse.clicked.connect(self.browse_location)
        loc_row.addWidget(btn_browse)
        
        layout.addLayout(loc_row)
        
        layout.addSpacing(25) 

        # 4. Create Button
        self.btn_create = QPushButton("CREATE PROJECT")
        self.btn_create.setProperty("class", "primary")
        self.btn_create.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_create.clicked.connect(self.create_project)
        layout.addWidget(self.btn_create)

        # 5. Divider
        div_layout = QHBoxLayout()
        div_layout.setContentsMargins(0, 15, 0, 15)
        
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        
        lbl_or = QLabel("OR")
        lbl_or.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; padding: 0 10px;")
        
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        
        div_layout.addWidget(line1)
        div_layout.addWidget(lbl_or)
        div_layout.addWidget(line2)
        layout.addLayout(div_layout)

        # 6. Open Existing
        btn_open = QPushButton("Open Existing Project")
        btn_open.setProperty("class", "ghost")
        btn_open.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_open.clicked.connect(self.open_project)
        layout.addWidget(btn_open)

        layout.addStretch()

    def browse_location(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if folder:
            self.loc_input.setText(folder)

    def create_project(self):
        folder = self.loc_input.text()
        name = self.name_input.text().strip()
        
        if not folder or not name:
            QMessageBox.warning(self, "Missing Info", "Please enter a project name and select a folder.")
            return
            
        project_file = os.path.join(folder, f"{name}{FILE_EXT}")
        if os.path.exists(project_file):
            QMessageBox.warning(self, "Error", "A project with this name already exists in that folder.")
            return

        try:
            with open(project_file, 'w') as f:
                f.write('{"version": "2.0", "files": []}')
            
            self.selected_project_path = folder
            self.project_name = name
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def open_project(self):
        fpath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", f"Cyne Project (*{FILE_EXT})")
        if fpath:
            self.selected_project_path = os.path.dirname(fpath)
            self.project_name = os.path.basename(fpath).replace(FILE_EXT, "")
            self.accept()