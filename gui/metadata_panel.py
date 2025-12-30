# [FILE: gui/metadata_panel.py]
import os
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, 
                             QTextEdit, QPushButton, QHBoxLayout, QMessageBox, QFrame,
                             QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from config import COLORS
from core.logger import get_logger

logger = get_logger(__name__)

class MetadataPanel(QWidget):
    save_requested = pyqtSignal(list, str)

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {COLORS['bg_panel']};")
        self.is_editing = False # State tracker
        self.current_file_path = None
        self.selected_files = []  # For bulk operations
        self.is_bulk_mode = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 1. Header with Filename & Edit Toggle
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        
        self.lbl_filename = QLabel("No Selection")
        self.lbl_filename.setStyleSheet(f"color: {COLORS['accent']}; font-weight: 900; font-size: 13px; letter-spacing: 0.5px;")
        self.lbl_filename.setWordWrap(True)
        header_layout.addWidget(self.lbl_filename, stretch=1)
        
        self.btn_edit = QPushButton("✎ Edit")
        self.btn_edit.setFixedSize(70, 28)
        self.btn_edit.setCheckable(True)
        self.btn_edit.clicked.connect(self.toggle_edit_mode)
        self.btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid #555; color: {COLORS['text_main']}; border-radius: 4px; font-size: 11px; font-weight: bold; }}
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

        # 2. Tags Input (Visual Chip-based)
        lbl_tags = QLabel("VISUAL KEYWORDS")
        lbl_tags.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_tags)

        from gui.tag_chip_widget import TagInputWidget
        self.tag_input_widget = TagInputWidget()
        self.tag_input_widget.tags_changed.connect(self.on_tags_changed)
        self.tag_input_widget.setEnabled(False)  # Disabled until edit mode
        layout.addWidget(self.tag_input_widget)
        
        # Keep old input_tags for backward compatibility during transition
        self.input_tags = None

        # 3. AI Summary
        lbl_summary = QLabel("DESCRIPTION / SUMMARY")
        lbl_summary.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_summary)

        self.input_summary = QTextEdit()
        self.input_summary.setPlaceholderText("Detailed description...")
        self.input_summary.setStyleSheet(self._get_input_style(read_only=True))
        self.input_summary.setReadOnly(True)
        layout.addWidget(self.input_summary)

        # 3.5. Full Transcript Display
        lbl_transcript = QLabel("FULL AUDIO TRANSCRIPT")
        lbl_transcript.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_transcript)

        self.input_transcript = QTextEdit()
        self.input_transcript.setPlaceholderText("Full audio transcript will appear here after transcription...")
        self.input_transcript.setFixedHeight(200)  # Fixed height with scrollbar
        self.input_transcript.setStyleSheet(self._get_input_style(read_only=True))
        self.input_transcript.setReadOnly(True)
        self.input_transcript.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.input_transcript)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        
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
        btn_layout.addWidget(self.btn_save)
        
        self.btn_export_srt = QPushButton("EXPORT SRT")
        self.btn_export_srt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_srt.clicked.connect(self.handle_export_srt)
        self.btn_export_srt.setFixedHeight(40)
        self.btn_export_srt.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']}; color: {COLORS['text_main']};
                border: 1px solid {COLORS['border']}; border-radius: 4px; 
                font-weight: 600; font-size: 12px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ 
                background: {COLORS['selection']}; 
                border-color: {COLORS['accent']};
            }}
            QPushButton:disabled {{
                background: {COLORS['bg_app']};
                color: #666;
                border-color: #333;
            }}
        """)
        btn_layout.addWidget(self.btn_export_srt)
        
        layout.addLayout(btn_layout)
        
        # Bulk operations panel (hidden by default)
        self.bulk_panel = self.create_bulk_panel()
        layout.addWidget(self.bulk_panel)
        
        layout.addStretch()
        self.clear()
    
    def create_bulk_panel(self):
        """Create bulk operations panel."""
        panel = QWidget()
        panel.hide()
        panel.setStyleSheet(f"""
            QWidget {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Header
        bulk_header = QLabel("BULK EDIT MODE")
        bulk_header.setStyleSheet(f"color: {COLORS['accent']}; font-size: 12px; font-weight: bold;")
        layout.addWidget(bulk_header)
        
        self.bulk_count_label = QLabel("0 files selected")
        self.bulk_count_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        layout.addWidget(self.bulk_count_label)
        
        # Copy tags from first
        btn_copy_tags = QPushButton("Copy Tags from First Selected")
        btn_copy_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy_tags.clicked.connect(self.copy_tags_from_first)
        btn_copy_tags.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_app']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                padding: 6px;
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        layout.addWidget(btn_copy_tags)
        
        # Apply tags to all
        btn_apply_tags = QPushButton("Apply Tags to All Selected")
        btn_apply_tags.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_apply_tags.clicked.connect(self.apply_tags_to_all)
        btn_apply_tags.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: #121212;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
        """)
        layout.addWidget(btn_apply_tags)
        
        return panel
    
    def show_bulk_mode(self, file_paths):
        """Show bulk edit mode for multiple files."""
        self.selected_files = file_paths
        self.is_bulk_mode = True
        self.bulk_panel.show()
        self.bulk_count_label.setText(f"{len(file_paths)} files selected")
        
        # Hide single-file edit button
        self.btn_edit.hide()
        self.btn_save.hide()
        
        # Load tags from first file
        if file_paths:
            try:
                from core.database import Database
                db = Database()
                meta = db.get_video_metadata(file_paths[0])
                tags = meta.get("tags", [])
                self.tag_input_widget.set_tags(tags)
                self.tag_input_widget.setEnabled(True)
            except:
                pass
    
    def hide_bulk_mode(self):
        """Hide bulk edit mode."""
        self.is_bulk_mode = False
        self.bulk_panel.hide()
        self.selected_files = []
        self.btn_edit.show()
    
    def copy_tags_from_first(self):
        """Copy tags from first selected file to tag input."""
        if not self.selected_files:
            return
        
        try:
            from core.database import Database
            db = Database()
            meta = db.get_video_metadata(self.selected_files[0])
            tags = meta.get("tags", [])
            self.tag_input_widget.set_tags(tags)
        except:
            pass
    
    def apply_tags_to_all(self):
        """Apply current tags to all selected files."""
        if not self.selected_files:
            return
        
        tags = self.tag_input_widget.get_tags()
        summary = self.input_summary.toPlainText().strip()
        
        try:
            from core.database import Database
            db = Database()
            for file_path in self.selected_files:
                db.save_tags(file_path, tags, summary)
            
            # Emit signal for main window to update tree
            self.save_requested.emit(tags, summary)
            
            # Show success message
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Bulk Update", 
                                  f"Applied tags to {len(self.selected_files)} file(s).")
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to apply tags: {e}")

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
        self.tag_input_widget.setEnabled(checked)
        self.input_summary.setReadOnly(not checked)
        
        self.input_summary.setStyleSheet(self._get_input_style(not checked))
        
        if checked:
            self.btn_save.show()
            self.btn_edit.setText("Cancel")
        else:
            self.btn_save.hide()
            self.btn_edit.setText("✎ Edit")
    
    def on_tags_changed(self, tags):
        """Handle tags changed signal from tag widget."""
        # Tags are automatically updated in the widget
        pass

    def load_data(self, file_path, tags, summary, file_paths=None):
        """Load data for single file or multiple files (bulk mode)."""
        # Hide bulk mode if showing single file
        if file_paths is None:
            self.hide_bulk_mode()
            self.current_file_path = file_path
            
            # Reset Edit Mode
            if self.btn_edit.isChecked():
                self.btn_edit.setChecked(False)
                self.toggle_edit_mode(False)
            
            if file_path:
                self.lbl_filename.setText(os.path.basename(file_path).upper())
                self.btn_edit.setEnabled(True)
            else:
                self.lbl_filename.setText("NO SELECTION")
                self.btn_edit.setEnabled(False)
            
            # Set tags in chip widget
            self.tag_input_widget.set_tags(tags if tags else [])
            self.input_summary.setText(summary if summary else "")
            
            # Load and display full transcript
            self.load_transcript(file_path)
            
            # Update export button state
            self.update_export_button_state()
        else:
            # Bulk mode
            self.show_bulk_mode(file_paths)
            if file_paths:
                self.lbl_filename.setText(f"{len(file_paths)} FILES SELECTED")

    def load_transcript(self, file_path):
        """Load and display the full transcript from database."""
        if not file_path:
            self.input_transcript.clear()
            return
        
        try:
            from core.database import Database
            db = Database()
            meta = db.get_video_metadata(file_path)
            transcript_data = meta.get("transcript", [])
            
            if transcript_data and isinstance(transcript_data, list):
                # Format transcript with timestamps
                transcript_lines = []
                for seg in transcript_data:
                    start_time = seg.get("start", 0)
                    text = seg.get("text", "").strip()
                    if text:
                        # Format time as MM:SS
                        minutes = int(start_time // 60)
                        seconds = int(start_time % 60)
                        time_str = f"[{minutes:02d}:{seconds:02d}]"
                        transcript_lines.append(f"{time_str} {text}")
                
                full_transcript = "\n".join(transcript_lines)
                self.input_transcript.setText(full_transcript)
            else:
                self.input_transcript.clear()
                self.input_transcript.setPlaceholderText("No transcript available. Transcribe audio to see full dialogue here.")
        except Exception as e:
            print(f"Error loading transcript: {e}")
            self.input_transcript.clear()

    def clear(self):
        self.current_file_path = None
        self.lbl_filename.setText("NO SELECTION")
        self.tag_input_widget.clear()
        self.input_summary.clear()
        self.input_transcript.clear()
        self.btn_edit.setEnabled(False)
        self.btn_edit.setChecked(False)
        self.toggle_edit_mode(False)
        # Update export button state
        self.update_export_button_state()
    
    def update_export_button_state(self):
        """Enable/disable export button based on whether transcript exists."""
        if not self.current_file_path:
            self.btn_export_srt.setEnabled(False)
            return
        
        from core.database import Database
        db = Database()
        meta = db.get_video_metadata(self.current_file_path)
        has_transcript = bool(meta.get("transcript"))
        self.btn_export_srt.setEnabled(has_transcript)

    def handle_save(self):
        if not self.current_file_path: return
        
        # Get tags from chip widget
        clean_tags = self.tag_input_widget.get_tags()
        
        summary = self.input_summary.toPlainText().strip()
        
        self.save_requested.emit(clean_tags, summary)
        
        # Exit edit mode
        self.btn_edit.setChecked(False)
        self.toggle_edit_mode(False)
    
    def handle_export_srt(self):
        """Export SRT for the current file."""
        if not self.current_file_path:
            QMessageBox.warning(self, "No File", "No file selected.")
            return
        
        # Check if transcript exists
        from core.database import Database
        db = Database()
        meta = db.get_video_metadata(self.current_file_path)
        transcript = meta.get("transcript", [])
        
        if not transcript:
            QMessageBox.information(self, "No Transcript", 
                                  "This file does not have a transcript. Please transcribe audio first.")
            return
        
        # Choose export location
        base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
        default_path = os.path.join(os.path.dirname(self.current_file_path), f"{base_name}.srt")
        
        export_path, _ = QFileDialog.getSaveFileName(
            self, "Export SRT", default_path, "SRT Files (*.srt)"
        )
        
        if not export_path:
            return
        
        # Export
        from core.srt_exporter import SRTExporter
        success = SRTExporter.export_transcript_to_srt(transcript, export_path)
        
        if success:
            QMessageBox.information(self, "Export Complete", 
                                  f"SRT file exported successfully:\n{export_path}")
        else:
            QMessageBox.warning(self, "Export Failed", 
                              "Failed to export SRT file. Please check the file path and try again.")