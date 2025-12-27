import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, 
                             QTextEdit, QPushButton, QHBoxLayout, QMessageBox, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from config import COLORS

class MetadataPanel(QWidget):
    # Signal to send data back to Main Window: (tags_list, summary_text)
    save_requested = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {COLORS['bg_panel']};")
        self.setup_ui()
        self.current_file_path = None

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 1. Header with Filename
        self.lbl_filename = QLabel("No Selection")
        self.lbl_filename.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 900; font-size: 13px; letter-spacing: 0.5px;")
        self.lbl_filename.setWordWrap(True)
        layout.addWidget(self.lbl_filename)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(line)

        # 2. Tags Input
        lbl_tags = QLabel("VISUAL TAGS (Comma separated)")
        lbl_tags.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_tags)

        self.input_tags = QLineEdit()
        self.input_tags.setPlaceholderText("e.g. Wedding, Smile, Slow Motion...")
        self.input_tags.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_input']}; color: {COLORS['text_main']};
                border: 1px solid {COLORS['border']}; padding: 8px; border-radius: 4px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
        """)
        layout.addWidget(self.input_tags)

        # 3. AI Summary / Description Input
        lbl_summary = QLabel("DESCRIPTION / AI SUMMARY")
        lbl_summary.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_summary)

        self.input_summary = QTextEdit()
        self.input_summary.setPlaceholderText("Detailed description of the clip...")
        self.input_summary.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['bg_input']}; color: {COLORS['text_main']};
                border: 1px solid {COLORS['border']}; padding: 8px; border-radius: 4px;
                font-family: 'Segoe UI', sans-serif; font-size: 12px; line-height: 1.4;
            }}
            QTextEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
        """)
        layout.addWidget(self.input_summary)

        # 4. Save Button
        self.btn_save = QPushButton("SAVE CHANGES")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.handle_save)
        self.btn_save.setFixedHeight(40)
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: #121212;
                border: none; border-radius: 4px; font-weight: 800; font-size: 12px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
            QPushButton:pressed {{ background: #999; }}
            QPushButton:disabled {{ background: #333; color: #555; }}
        """)
        layout.addWidget(self.btn_save)
        
        # Add stretch to push everything up
        layout.addStretch()

        # Start disabled until file selected
        self.clear()

    def load_data(self, file_path, tags, summary):
        self.current_file_path = file_path
        
        # Clean filename for display
        name = file_path.split("/")[-1]
        if "\\" in name: name = name.split("\\")[-1]
        self.lbl_filename.setText(name.upper())
        
        # Join tags list into a string
        tag_str = ", ".join(tags) if tags else ""
        self.input_tags.setText(tag_str)
        
        self.input_summary.setText(summary if summary else "")
        
        # Enable controls
        self.input_tags.setEnabled(True)
        self.input_summary.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.btn_save.setText("SAVE CHANGES")

    def clear(self):
        self.current_file_path = None
        self.lbl_filename.setText("NO SELECTION")
        self.input_tags.clear()
        self.input_summary.clear()
        
        # Disable controls
        self.input_tags.setEnabled(False)
        self.input_summary.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_save.setText("SAVE CHANGES")

    def handle_save(self):
        if not self.current_file_path: return
        
        # Parse tags back into list
        raw_tags = self.input_tags.text().split(',')
        clean_tags = [t.strip() for t in raw_tags if t.strip()]
        
        summary = self.input_summary.toPlainText()
        
        # Emit signal to Main Window
        self.save_requested.emit(clean_tags, summary)
        
        # Visual Feedback
        self.btn_save.setText("SAVED!")