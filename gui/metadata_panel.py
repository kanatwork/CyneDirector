# [FILE: gui/metadata_panel.py]
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, 
                             QTextEdit, QPushButton, QHBoxLayout, QMessageBox, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from config import COLORS

class MetadataPanel(QWidget):
    save_requested = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {COLORS['bg_panel']};")
        self.is_editing = False # State tracker
        self.setup_ui()
        self.current_file_path = None

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 1. Header with Filename & Edit Toggle
        header_layout = QHBoxLayout()
        
        self.lbl_filename = QLabel("No Selection")
        self.lbl_filename.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 900; font-size: 13px; letter-spacing: 0.5px;")
        self.lbl_filename.setWordWrap(True)
        header_layout.addWidget(self.lbl_filename, stretch=1)
        
        self.btn_edit = QPushButton("✎ Edit")
        self.btn_edit.setFixedSize(60, 25)
        self.btn_edit.setCheckable(True)
        self.btn_edit.clicked.connect(self.toggle_edit_mode)
        self.btn_edit.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid #555; color: #888; border-radius: 4px; font-size: 11px; font-weight: bold; }}
            QPushButton:checked {{ background: {COLORS['accent']}; color: black; border: none; }}
            QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
            QPushButton:checked:hover {{ color: black; }}
        """)
        header_layout.addWidget(self.btn_edit)
        
        layout.addLayout(header_layout)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(line)

        # 2. Tags Input
        lbl_tags = QLabel("VISUAL KEYWORDS")
        lbl_tags.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_tags)

        self.input_tags = QTextEdit() # Changed to TextEdit for multi-line tags
        self.input_tags.setPlaceholderText("AI generated keywords will appear here...")
        self.input_tags.setFixedHeight(80)
        self.input_tags.setStyleSheet(self._get_input_style(read_only=True))
        self.input_tags.setReadOnly(True)
        layout.addWidget(self.input_tags)

        # 3. AI Summary
        lbl_summary = QLabel("DESCRIPTION / SUMMARY")
        lbl_summary.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_summary)

        self.input_summary = QTextEdit()
        self.input_summary.setPlaceholderText("Detailed description...")
        self.input_summary.setStyleSheet(self._get_input_style(read_only=True))
        self.input_summary.setReadOnly(True)
        layout.addWidget(self.input_summary)

        # 4. Save Button (Hidden by default)
        self.btn_save = QPushButton("SAVE CHANGES")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.handle_save)
        self.btn_save.setFixedHeight(40)
        self.btn_save.hide() 
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: #121212;
                border: none; border-radius: 4px; font-weight: 800; font-size: 12px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        layout.addWidget(self.btn_save)
        
        layout.addStretch()
        self.clear()

    def _get_input_style(self, read_only=True):
        if read_only:
            return f"""
                QTextEdit {{
                    background: {COLORS['bg_app']}; color: #CCC;
                    border: 1px solid transparent; padding: 8px; border-radius: 4px;
                    font-size: 12px; font-family: 'Segoe UI', sans-serif;
                }}
            """
        else:
            return f"""
                QTextEdit {{
                    background: {COLORS['bg_input']}; color: white;
                    border: 1px solid {COLORS['border']}; padding: 8px; border-radius: 4px;
                    font-size: 12px; font-family: 'Segoe UI', sans-serif;
                }}
                QTextEdit:focus {{ border: 1px solid {COLORS['accent']}; }}
            """

    def toggle_edit_mode(self, checked):
        self.is_editing = checked
        self.input_tags.setReadOnly(not checked)
        self.input_summary.setReadOnly(not checked)
        
        self.input_tags.setStyleSheet(self._get_input_style(not checked))
        self.input_summary.setStyleSheet(self._get_input_style(not checked))
        
        if checked:
            self.btn_save.show()
            self.btn_edit.setText("Cancel")
        else:
            self.btn_save.hide()
            self.btn_edit.setText("✎ Edit")
            # Revert changes if cancelled? For now, we just hide button
            if self.current_file_path:
                # Reload data to revert any unsaved typing
                # We need the main window to re-trigger load, or we store local cache.
                # For simplicity in V2.1, we assume user saves or loses edits.
                pass

    def load_data(self, file_path, tags, summary):
        self.current_file_path = file_path
        
        # Reset Edit Mode
        if self.btn_edit.isChecked():
            self.btn_edit.setChecked(False)
            self.toggle_edit_mode(False)
        
        name = file_path.split("/")[-1]
        if "\\" in name: name = name.split("\\")[-1]
        self.lbl_filename.setText(name.upper())
        
        # Format tags nicely
        tag_str = ", ".join(tags) if tags else "No tags yet."
        self.input_tags.setText(tag_str)
        self.input_summary.setText(summary if summary else "No summary available.")
        
        self.btn_edit.setEnabled(True)

    def clear(self):
        self.current_file_path = None
        self.lbl_filename.setText("NO SELECTION")
        self.input_tags.clear()
        self.input_summary.clear()
        self.btn_edit.setEnabled(False)
        self.btn_edit.setChecked(False)
        self.toggle_edit_mode(False)

    def handle_save(self):
        if not self.current_file_path: return
        
        raw_tags = self.input_tags.toPlainText().split(',')
        clean_tags = [t.strip() for t in raw_tags if t.strip()]
        summary = self.input_summary.toPlainText()
        
        self.save_requested.emit(clean_tags, summary)
        
        # Exit edit mode
        self.btn_edit.setChecked(False)
        self.toggle_edit_mode(False)