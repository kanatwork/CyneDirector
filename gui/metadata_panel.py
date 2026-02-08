# [FILE: gui/metadata_panel.py]
import os
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QLineEdit, 
                             QTextEdit, QPushButton, QHBoxLayout, QMessageBox, QFrame,
                             QFileDialog, QProgressDialog, QCheckBox, QTabWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from config import COLORS, DEEPL_API_KEY
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
        self.translate_worker = None
        self.translated_segments = None
        self.original_segments = None
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
            QPushButton {{ background: transparent; border: 1px solid {COLORS['text_disabled']}; color: {COLORS['text_main']}; border-radius: 4px; font-size: 11px; font-weight: bold; }}
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

        # 3.5. Full Transcript Display with Tabs
        lbl_transcript = QLabel("FULL AUDIO TRANSCRIPT")
        lbl_transcript.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(lbl_transcript)

        # Create tab widget for original and translated transcripts
        self.transcript_tabs = QTabWidget()
        self.transcript_tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border']};
                background: {COLORS['bg_app']};
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background: {COLORS['bg_input']};
                color: {COLORS['text_dim']};
                padding: 8px 16px;
                border: 1px solid {COLORS['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background: {COLORS['bg_app']};
                color: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """)
        
        # Original transcript tab
        self.input_transcript_original = QTextEdit()
        self.input_transcript_original.setPlaceholderText("Original language transcript will appear here after transcription...")
        self.input_transcript_original.setStyleSheet(self._get_input_style(read_only=True))
        self.input_transcript_original.setReadOnly(True)
        self.input_transcript_original.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.transcript_tabs.addTab(self.input_transcript_original, "Original")
        
        # Translated transcript tab
        self.input_transcript_translated = QTextEdit()
        self.input_transcript_translated.setPlaceholderText("English translation will appear here after translation...")
        self.input_transcript_translated.setStyleSheet(self._get_input_style(read_only=True))
        self.input_transcript_translated.setReadOnly(True)
        self.input_transcript_translated.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.transcript_tabs.addTab(self.input_transcript_translated, "English")
        
        self.transcript_tabs.setFixedHeight(200)
        layout.addWidget(self.transcript_tabs)
        
        # Keep old input_transcript for backward compatibility (point to original tab)
        self.input_transcript = self.input_transcript_original

        # 4. Transcription/Translation Controls
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(10)
        
        # Checkboxes for options
        checkbox_layout = QHBoxLayout()
        checkbox_layout.setSpacing(15)
        
        self.checkbox_transcribe = QCheckBox("Transcribe")
        self.checkbox_transcribe.setChecked(True)  # Default to checked
        self.checkbox_transcribe.stateChanged.connect(self.update_start_process_button_state)
        self.checkbox_transcribe.setStyleSheet(f"""
            QCheckBox {{
                color: {COLORS['text_main']};
                font-size: 12px;
                font-weight: 600;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {COLORS['border']};
                border-radius: 4px;
                background: {COLORS['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """)
        checkbox_layout.addWidget(self.checkbox_transcribe)
        
        self.checkbox_translate = QCheckBox("Translate to English")
        self.checkbox_translate.setChecked(False)
        self.checkbox_translate.stateChanged.connect(self.update_start_process_button_state)
        self.checkbox_translate.setStyleSheet(f"""
            QCheckBox {{
                color: {COLORS['text_main']};
                font-size: 12px;
                font-weight: 600;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {COLORS['border']};
                border-radius: 4px;
                background: {COLORS['bg_input']};
            }}
            QCheckBox::indicator:checked {{
                background: {COLORS['accent']};
                border-color: {COLORS['accent']};
            }}
        """)
        checkbox_layout.addWidget(self.checkbox_translate)
        
        checkbox_layout.addStretch()
        controls_layout.addLayout(checkbox_layout)
        
        # DeepL Status Indicator
        self.deepl_status_label = QLabel("")
        self.deepl_status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_dim']};
                font-size: 10px;
                font-style: italic;
                padding: 4px 0px;
            }}
        """)
        self.deepl_status_label.hide()  # Hidden by default, shown when file is loaded
        controls_layout.addWidget(self.deepl_status_label)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_save = QPushButton("SAVE CHANGES")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.handle_save)
        self.btn_save.setFixedHeight(40)
        self.btn_save.hide() 
        self.btn_save.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: {COLORS['text_on_accent']};
                border: none; border-radius: 4px; font-weight: 800; font-size: 12px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
        """)
        btn_layout.addWidget(self.btn_save)
        
        self.btn_start_process = QPushButton("▶ START PROCESS")
        self.btn_start_process.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_process.clicked.connect(self.handle_start_process)
        self.btn_start_process.setFixedHeight(40)
        self.btn_start_process.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; color: {COLORS['text_on_accent']};
                border: none; border-radius: 4px; 
                font-weight: 800; font-size: 12px;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ 
                background: {COLORS['accent_hover']};
            }}
            QPushButton:disabled {{
                background: {COLORS['bg_app']};
                color: {COLORS['text_dim']};
                border-color: {COLORS['border']};
            }}
        """)
        btn_layout.addWidget(self.btn_start_process)
        
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
                color: {COLORS['text_dim']};
                border-color: {COLORS['border']};
            }}
        """)
        btn_layout.addWidget(self.btn_export_srt)
        
        controls_layout.addLayout(btn_layout)
        layout.addLayout(controls_layout)
        
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
                color: {COLORS['text_on_accent']};
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
                    background: {COLORS['bg_app']}; color: {COLORS['text_main']};
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
            
            # Update DeepL status indicator
            self.update_deepl_status()
            
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
            
            # Ensure segments have language detection (for existing transcripts)
            try:
                from core.database import Database
                db = Database()
                db.ensure_segment_languages(file_path)
            except Exception as e:
                logger.debug(f"Could not ensure segment languages: {e}")
            
            # Also load translated transcript if available
            self.load_translated_transcript(file_path)
            
            # Check for existing transcript and update UI accordingly
            self.update_transcript_ui_state(file_path)
            
            # Update export button state
            self.update_export_button_state()
            self.update_start_process_button_state()
        else:
            # Bulk mode
            self.show_bulk_mode(file_paths)
            if file_paths:
                self.lbl_filename.setText(f"{len(file_paths)} FILES SELECTED")

    def load_transcript(self, file_path):
        """Load and display the full transcript from database.
        Shows original transcript as-is: English in English, other languages in native text."""
        if not file_path:
            self.input_transcript_original.clear()
            return
        
        try:
            from core.database import Database
            from core.translator import detect_segment_language
            db = Database()
            meta = db.get_video_metadata(file_path)
            transcript_data = meta.get("transcript", [])
            
            if transcript_data and isinstance(transcript_data, list):
                # Format transcript with timestamps
                # For mixed-language: show English in English, other languages in native text
                transcript_lines = []
                for seg in transcript_data:
                    start_time = seg.get("start", 0)
                    text = seg.get("text", "").strip()
                    if text:
                        # Detect language if not already stored
                        lang = detect_segment_language(seg)
                        
                        # Format time as MM:SS
                        minutes = int(start_time // 60)
                        seconds = int(start_time % 60)
                        time_str = f"[{minutes:02d}:{seconds:02d}]"
                        
                        # Optionally add language indicator for non-English segments
                        # (can be removed if user prefers cleaner display)
                        if lang and lang != 'en':
                            lang_label = lang.upper()
                            transcript_lines.append(f"{time_str} [{lang_label}] {text}")
                        else:
                            transcript_lines.append(f"{time_str} {text}")
                
                full_transcript = "\n".join(transcript_lines)
                self.input_transcript_original.setText(full_transcript)
                self.original_segments = transcript_data
            else:
                self.input_transcript_original.clear()
                self.input_transcript_original.setPlaceholderText("No transcript available. Check 'Transcribe' and click 'Start Process' to transcribe audio.")
        except Exception as e:
            logger.error(f"Error loading transcript: {e}")
            self.input_transcript_original.clear()
    
    def load_translated_transcript(self, file_path):
        """Load and display the translated transcript from database if available.
        The translated transcript should already be all in English (English segments kept as-is,
        non-English segments translated)."""
        if not file_path:
            self.input_transcript_translated.clear()
            return
        
        try:
            from core.database import Database
            db = Database()
            meta = db.get_video_metadata(file_path)
            translated_data = meta.get("transcript_translated", [])
            translation_method = meta.get("translation_method", "whisper")
            
            if translated_data and isinstance(translated_data, list):
                # The translated transcript should already be all in English
                # (English segments unchanged, non-English segments translated)
                # But add safety check to filter out any Hindi that might have slipped through
                
                # Format transcript with timestamps
                # Show ALL segments - don't filter out Hindi, but mark them
                transcript_lines = []
                hindi_segments_found = 0
                for seg in translated_data:
                    start_time = seg.get("start", 0)
                    text = seg.get("text", "").strip()
                    if text:
                        # Check if segment still contains Hindi
                        has_hindi = any('\u0900' <= char <= '\u097F' for char in text)
                        if has_hindi:
                            hindi_segments_found += 1
                            logger.warning(f"Hindi text found in translated segment: {text[:50]}...")
                            # Don't filter it out - show it with a warning marker
                            text = f"[⚠ Translation incomplete] {text}"
                        
                        # Format time as MM:SS
                        minutes = int(start_time // 60)
                        seconds = int(start_time % 60)
                        time_str = f"[{minutes:02d}:{seconds:02d}]"
                        transcript_lines.append(f"{time_str} {text}")
                
                if hindi_segments_found > 0:
                    logger.warning(f"Found {hindi_segments_found} segments with Hindi text in English translation tab")
                    # Show a warning to the user
                    header_note = f"[⚠ Warning: {hindi_segments_found} segment(s) still contain Hindi - translation may be incomplete. Please retry translation.]\n\n"
                else:
                    header_note = ""
                
                if transcript_lines:
                    full_transcript = "\n".join(transcript_lines)
                    # Add header showing translation method
                    method_text = "DeepL" if translation_method == "deepl" else "Whisper"
                    header = f"[Translated with {method_text}]\n\n"
                    self.input_transcript_translated.setText(header_note + header + full_transcript)
                    # Store all segments (including those with Hindi - they're marked)
                    self.translated_segments = translated_data
                else:
                    self.input_transcript_translated.clear()
                    self.input_transcript_translated.setPlaceholderText("Translation available but no text to display.")
            else:
                self.input_transcript_translated.clear()
                self.input_transcript_translated.setPlaceholderText("No translation available. Check 'Translate to English' and click 'Start Process' to translate.")
        except Exception as e:
            logger.error(f"Error loading translated transcript: {e}")
            self.input_transcript_translated.clear()

    def clear(self):
        self.current_file_path = None
        self.lbl_filename.setText("NO SELECTION")
        self.tag_input_widget.clear()
        self.input_summary.clear()
        self.input_transcript_original.clear()
        self.input_transcript_translated.clear()
        self.original_segments = None
        self.translated_segments = None
        self.btn_edit.setEnabled(False)
        self.btn_edit.setChecked(False)
        self.toggle_edit_mode(False)
        self.deepl_status_label.hide()
        # Reset checkbox states
        self.checkbox_transcribe.setChecked(True)
        self.checkbox_transcribe.setText("Transcribe")
        self.checkbox_translate.setChecked(False)
        self.checkbox_translate.setEnabled(True)
        # Update export button state
        self.update_export_button_state()
        self.update_start_process_button_state()
    
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
    
    def update_transcript_ui_state(self, file_path):
        """Update UI based on existing transcript/translation status."""
        if not file_path:
            return
        
        try:
            from core.database import Database
            db = Database()
            meta = db.get_video_metadata(file_path)
            has_transcript = bool(meta.get("transcript"))
            has_translation = bool(meta.get("transcript_translated"))
            
            # Update checkbox states based on what exists
            if has_transcript:
                # If transcript exists, uncheck transcribe by default (user can re-check to re-transcribe)
                self.checkbox_transcribe.setChecked(False)
                self.checkbox_transcribe.setText("Re-transcribe")
                # Enable translate checkbox
                self.checkbox_translate.setEnabled(True)
                # If translation doesn't exist, check translate by default
                if not has_translation:
                    self.checkbox_translate.setChecked(True)
                else:
                    # Translation exists, uncheck by default (user can re-check to re-translate)
                    self.checkbox_translate.setChecked(False)
            else:
                # No transcript, check transcribe by default
                self.checkbox_transcribe.setChecked(True)
                self.checkbox_transcribe.setText("Transcribe")
                # Can't translate without transcript
                self.checkbox_translate.setChecked(False)
                self.checkbox_translate.setEnabled(False)
        except Exception as e:
            logger.error(f"Error updating transcript UI state: {e}")
    
    def update_deepl_status(self):
        """Update DeepL status indicator."""
        if not self.current_file_path:
            self.deepl_status_label.hide()
            return
        
        try:
            from config import DEEPL_API_KEY
            from core.translator import get_translator
            
            # Check if DeepL is available
            deepl_translator = get_translator(DEEPL_API_KEY)
            if deepl_translator and deepl_translator.available:
                self.deepl_status_label.setText("🌐 DeepL translation available")
                self.deepl_status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLORS['success']};
                        font-size: 10px;
                        font-style: italic;
                        padding: 4px 0px;
                    }}
                """)
            else:
                self.deepl_status_label.setText("⚠ Using Whisper translation (DeepL not configured)")
                self.deepl_status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLORS['warning']};
                        font-size: 10px;
                        font-style: italic;
                        padding: 4px 0px;
                    }}
                """)
            
            # Check if file already has translation and show method used
            from core.database import Database
            db = Database()
            meta = db.get_video_metadata(self.current_file_path)
            translation_method = meta.get("translation_method")
            if translation_method:
                method_text = "DeepL" if translation_method == "deepl" else "Whisper"
                self.deepl_status_label.setText(f"🌐 Translation method: {method_text}")
            
            self.deepl_status_label.show()
        except Exception as e:
            logger.error(f"Error updating DeepL status: {e}")
            self.deepl_status_label.hide()
    
    def update_start_process_button_state(self):
        """Enable/disable start process button."""
        if not self.current_file_path:
            self.btn_start_process.setEnabled(False)
            return
        
        # Enable if we have a valid video file and at least one checkbox is checked
        if os.path.exists(self.current_file_path) and (self.checkbox_transcribe.isChecked() or self.checkbox_translate.isChecked()):
            self.btn_start_process.setEnabled(True)
        else:
            self.btn_start_process.setEnabled(False)
        
        # Enable translate checkbox if transcript exists
        try:
            from core.database import Database
            db = Database()
            meta = db.get_video_metadata(self.current_file_path)
            has_transcript = bool(meta.get("transcript"))
            self.checkbox_translate.setEnabled(has_transcript or self.checkbox_transcribe.isChecked())
        except:
            pass

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
        
        # Check which tab is active to determine what to export
        current_tab = self.transcript_tabs.currentIndex()
        use_translated = (current_tab == 1) and self.translated_segments
        
        # Get transcript data
        from core.database import Database
        db = Database()
        meta = db.get_video_metadata(self.current_file_path)
        
        if use_translated and self.translated_segments:
            transcript = self.translated_segments
            default_suffix = "_translated"
        else:
            transcript = meta.get("transcript", [])
            if not transcript and self.original_segments:
                transcript = self.original_segments
            default_suffix = ""
        
        if not transcript:
            QMessageBox.information(self, "No Transcript", 
                                  "This file does not have a transcript. Please transcribe audio first.")
            return
        
        # Choose export location
        base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
        default_path = os.path.join(os.path.dirname(self.current_file_path), f"{base_name}{default_suffix}.srt")
        
        export_path, _ = QFileDialog.getSaveFileName(
            self, "Export SRT", default_path, "SRT Files (*.srt)"
        )
        
        if not export_path:
            return
        
        # Export - both use sentence-aware export (one sentence per subtitle)
        from core.srt_exporter import SRTExporter
        if use_translated:
            # For translated, use split_segments_into_sentences to preserve timing
            success = SRTExporter.export_translated_srt(transcript, export_path, merge_segments=False)
        else:
            # For original, also split into sentences for proper SRT format
            success = SRTExporter.export_transcript_to_srt(transcript, export_path, one_sentence_per_subtitle=True)
        
        if success:
            QMessageBox.information(self, "Export Complete", 
                                  f"SRT file exported successfully:\n{export_path}")
        else:
            QMessageBox.warning(self, "Export Failed", 
                              "Failed to export SRT file. Please check the file path and try again.")
    
    def handle_start_process(self):
        """Handle start process button click."""
        if not self.current_file_path:
            QMessageBox.warning(self, "No File", "No file selected.")
            return
        
        if not os.path.exists(self.current_file_path):
            QMessageBox.warning(self, "File Not Found", "The selected file does not exist.")
            return
        
        # Check if at least one option is selected
        if not self.checkbox_transcribe.isChecked() and not self.checkbox_translate.isChecked():
            QMessageBox.warning(self, "No Option Selected", "Please select at least one option (Transcribe or Translate).")
            return
        
        # Check if worker is already running
        if self.translate_worker and self.translate_worker.isRunning():
            QMessageBox.information(self, "Already Running", 
                                  "Processing is already in progress.")
            return
        
        # Try to integrate with main workflow if available
        # Get main window reference if possible
        main_window = None
        try:
            from PyQt6.QtWidgets import QApplication
            for widget in QApplication.topLevelWidgets():
                if hasattr(widget, 'workflow_manager') and hasattr(widget, 'project_path'):
                    main_window = widget
                    break
        except:
            pass
        
        # If main workflow is running, add to queue instead
        if main_window and hasattr(main_window, 'workflow_manager') and main_window.workflow_manager.is_running:
            # Add to workflow queue
            from core.workflow_manager import OperationType
            files = [self.current_file_path]
            
            if self.checkbox_transcribe.isChecked():
                main_window.workflow_manager.add_operation(OperationType.TRANSCRIBE_AUDIO, files, smart_filter=False)
            
            if self.checkbox_translate.isChecked():
                main_window.workflow_manager.add_operation(OperationType.TRANSLATE_AUDIO, files, smart_filter=False)
            
            # Update workflow display
            if hasattr(main_window, 'update_workflow_queue_display'):
                main_window.update_workflow_queue_display()
            if hasattr(main_window, '_show_workflow_panel'):
                main_window._show_workflow_panel()
            
            QMessageBox.information(self, "Added to Queue", 
                                  "Operation added to workflow queue. It will be processed when the current workflow completes.")
            return
        
        # Get project path from database
        try:
            from core.database import Database
            db = Database()
            project_path = getattr(db, 'project_path', None)
            if not project_path:
                # Fallback: use directory containing the video file
                project_path = os.path.dirname(self.current_file_path)
        except Exception as e:
            logger.warning(f"Could not get project path from database: {e}")
            # Fallback: use directory containing the video file
            project_path = os.path.dirname(self.current_file_path)
        
        # Determine what to do
        should_transcribe = self.checkbox_transcribe.isChecked()
        should_translate = self.checkbox_translate.isChecked()
        
        # Create progress dialog
        action_text = []
        if should_transcribe:
            action_text.append("transcribing")
        if should_translate:
            action_text.append("translating")
        action_str = " and ".join(action_text)
        
        self.progress_dialog = QProgressDialog(f"{action_str.capitalize()}...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Processing")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setMinimumWidth(400)
        self.progress_dialog.setCancelButton(None)  # Disable cancel for now (can be enabled later)
        self.progress_dialog.show()
        
        # Create and start worker
        from workers.transcribe_translate_worker import TranscribeTranslateWorker
        self.translate_worker = TranscribeTranslateWorker(
            self.current_file_path,
            project_path,
            deepl_api_key=DEEPL_API_KEY,
            mode="accuracy",
            should_transcribe=should_transcribe,
            should_translate=should_translate
        )
        
        # Connect signals
        self.translate_worker.log_signal.connect(self.on_translate_log)
        self.translate_worker.progress_signal.connect(self.on_translate_progress)
        self.translate_worker.finished_signal.connect(self.on_translate_finished)
        self.translate_worker.transcription_complete_signal.connect(self.on_transcription_complete)
        self.translate_worker.translation_complete_signal.connect(self.on_translation_complete)
        
        # Disable button and checkboxes during processing
        self.btn_start_process.setEnabled(False)
        self.checkbox_transcribe.setEnabled(False)
        self.checkbox_translate.setEnabled(False)
        
        # Start worker
        self.translate_worker.start()
    
    def on_translate_log(self, message: str):
        """Handle log messages from translation worker."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setLabelText(message)
        logger.info(f"Translation: {message}")
    
    def on_translate_progress(self, value: int):
        """Handle progress updates from translation worker."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.setValue(value)
    
    def on_translate_finished(self, success: bool, error_msg: str):
        """Handle translation worker completion."""
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
        
        # Re-enable controls
        self.btn_start_process.setEnabled(True)
        self.checkbox_transcribe.setEnabled(True)
        self.checkbox_translate.setEnabled(True)
        self.update_start_process_button_state()
        
        if success:
            # Update export button state after successful transcription/translation
            self.update_export_button_state()
            
            # Show success message
            message = "Processing completed successfully!"
            if self.translated_segments:
                message += "\n\nWould you like to export the translated SRT file?"
                reply = QMessageBox.question(
                    self,
                    "Processing Complete",
                    message,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.export_translated_srt()
            else:
                QMessageBox.information(self, "Processing Complete", message)
        else:
            QMessageBox.warning(
                self,
                "Processing Failed",
                f"Processing failed: {error_msg}"
            )
    
    def on_transcription_complete(self, original_segments: list):
        """Handle transcription completion with original language segments."""
        self.original_segments = original_segments
        
        # Update original transcript tab
        if original_segments:
            transcript_lines = []
            for seg in original_segments:
                start_time = seg.get("start", 0)
                text = seg.get("text", "").strip()
                if text:
                    minutes = int(start_time // 60)
                    seconds = int(start_time % 60)
                    time_str = f"[{minutes:02d}:{seconds:02d}]"
                    transcript_lines.append(f"{time_str} {text}")
            
            full_transcript = "\n".join(transcript_lines)
            self.input_transcript_original.setText(full_transcript)
            
            # Switch to original tab to show the transcription
            self.transcript_tabs.setCurrentIndex(0)
        
        # Update export button state after transcription completes
        self.update_export_button_state()
    
    def on_translation_complete(self, translated_segments: list):
        """Handle translation completion with segments."""
        self.translated_segments = translated_segments
        
        # Update translated transcript tab
        if translated_segments and len(translated_segments) > 0:
            transcript_lines = []
            for seg in translated_segments:
                start_time = seg.get("start", 0)
                text = seg.get("text", "").strip()
                if text:
                    minutes = int(start_time // 60)
                    seconds = int(start_time % 60)
                    time_str = f"[{minutes:02d}:{seconds:02d}]"
                    transcript_lines.append(f"{time_str} {text}")
            
            if transcript_lines:
                full_transcript = "\n".join(transcript_lines)
                self.input_transcript_translated.setText(full_transcript)
                logger.info(f"Updated English tab with {len(translated_segments)} translated segments")
                
                # Switch to translated tab if translation was done
                if self.checkbox_translate.isChecked():
                    self.transcript_tabs.setCurrentIndex(1)
            else:
                logger.warning("Translation completed but no text to display")
                self.input_transcript_translated.setText("Translation completed but no text was generated.")
        else:
            logger.warning("Translation completed but no segments received")
            self.input_transcript_translated.setText("Translation failed or returned no results.")
        
        # Update export button state after translation completes
        self.update_export_button_state()
    
    def export_translated_srt(self):
        """Export the translated SRT file."""
        if not self.translated_segments:
            QMessageBox.warning(self, "No Translation", "No translated segments available.")
            return
        
        if not self.current_file_path:
            QMessageBox.warning(self, "No File", "No file selected.")
            return
        
        # Choose export location
        base_name = os.path.splitext(os.path.basename(self.current_file_path))[0]
        default_path = os.path.join(os.path.dirname(self.current_file_path), f"{base_name}_translated.srt")
        
        export_path, _ = QFileDialog.getSaveFileName(
            self, "Export Translated SRT", default_path, "SRT Files (*.srt)"
        )
        
        if not export_path:
            return
        
        # Export using sentence-aware method (preserves timing)
        from core.srt_exporter import SRTExporter
        success = SRTExporter.export_translated_srt(
            self.translated_segments,
            export_path,
            merge_segments=False  # Preserve original timing instead of redistributing
        )
        
        if success:
            QMessageBox.information(
                self,
                "Export Complete",
                f"Translated SRT file exported successfully:\n{export_path}"
            )
        else:
            QMessageBox.warning(
                self,
                "Export Failed",
                "Failed to export translated SRT file. Please check the file path and try again."
            )