# [FILE: gui/activity_log.py]
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                             QPushButton, QLabel, QCheckBox, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor
from config import COLORS
from enum import Enum

class LogLevel(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"

class ActivityLog(QWidget):
    """Expandable activity log panel showing real-time backend activity."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.max_entries = 1000  # Limit to prevent memory issues
        self.auto_scroll = True
        self.entry_count = 0
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header bar (improved)
        header = QWidget()
        header.setFixedHeight(40)
        header.setStyleSheet(f"""
            background: {COLORS['bg_panel']};
            border-bottom: 1px solid {COLORS['border']};
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 8, 15, 8)
        header_layout.setSpacing(12)
        
        # Header icon
        header_icon = QLabel("📋")
        header_icon.setStyleSheet(f"color: {COLORS['accent']}; font-size: 16px;")
        header_layout.addWidget(header_icon)
        
        self.header_label = QLabel("Activity Log")
        self.header_label.setStyleSheet(f"""
            color: {COLORS['text_main']};
            font-weight: bold;
            font-size: 13px;
        """)
        header_layout.addWidget(self.header_label)
        
        header_layout.addStretch()
        
        # Auto-scroll checkbox
        self.auto_scroll_cb = QCheckBox("Auto-scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.stateChanged.connect(self.toggle_auto_scroll)
        self.auto_scroll_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {COLORS['text_dim']};
                font-size: 11px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
            }}
        """)
        header_layout.addWidget(self.auto_scroll_cb)
        
        # Clear button
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedSize(60, 25)
        self.btn_clear.clicked.connect(self.clear_log)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #35373C;
                border-color: {COLORS['accent']};
            }}
        """)
        header_layout.addWidget(self.btn_clear)
        
        layout.addWidget(header)
        
        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['bg_app']};
                color: {COLORS['text_main']};
                border: none;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.log_text)
        
        # Set initial height (collapsed state)
        self._max_height = 200
        self.setMaximumHeight(self._max_height)
        self.is_expanded = False
        
        # Animation for smooth expand/collapse
        self.animation = QPropertyAnimation(self, b"maximumHeight")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    
    def toggle_auto_scroll(self, state):
        """Toggle auto-scroll behavior."""
        self.auto_scroll = (state == Qt.CheckState.Checked.value)
    
    def clear_log(self):
        """Clear all log entries."""
        self.log_text.clear()
        self.entry_count = 0
    
    def add_entry(self, message: str, level: LogLevel = LogLevel.INFO, 
                  timestamp: bool = True, details: str = None):
        """
        Add a log entry with color coding.
        
        Args:
            message: Log message text
            level: Log level (INFO, SUCCESS, WARNING, ERROR)
            timestamp: Whether to include timestamp
            details: Optional detailed information (e.g., stack trace) to show on expand
        """
        # Limit entries to prevent memory issues
        if self.entry_count >= self.max_entries:
            # Remove oldest entries (first 100)
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            for _ in range(100):
                cursor.movePosition(QTextCursor.MoveOperation.Down, 
                                  QTextCursor.MoveMode.KeepAnchor)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, 
                                  QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self.entry_count -= 100
        
        # Format timestamp
        if timestamp:
            time_str = QDateTime.currentDateTime().toString("hh:mm:ss")
            prefix = f"[{time_str}] "
        else:
            prefix = "  "
        
        # Get icon and color based on level
        icon_map = {
            LogLevel.INFO: "ℹ",
            LogLevel.SUCCESS: "✓",
            LogLevel.WARNING: "⚠",
            LogLevel.ERROR: "✗"
        }
        color_map = {
            LogLevel.INFO: COLORS['text_main'],
            LogLevel.SUCCESS: COLORS['success'],
            LogLevel.WARNING: COLORS['warning'],
            LogLevel.ERROR: COLORS['error']
        }
        icon = icon_map.get(level, "•")
        color = color_map.get(level, COLORS['text_main'])
        
        # Format text
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # Apply color formatting
        format = QTextCharFormat()
        format.setForeground(QColor(color))
        cursor.setCharFormat(format)
        
        # Insert text with icon
        full_text = f"{prefix}{icon} {message}"
        if details:
            full_text += f" [Details: {details[:50]}...]"  # Preview
        full_text += "\n"
        
        # If details provided, add them in a collapsed format
        if details:
            detail_format = QTextCharFormat()
            detail_format.setForeground(QColor(COLORS['text_dim']))
            detail_format.setFontPointSize(9)
            cursor.setCharFormat(detail_format)
            detail_lines = details.split('\n')
            for line in detail_lines[:10]:  # Limit to 10 lines
                cursor.insertText(f"    {line}\n")
            if len(detail_lines) > 10:
                cursor.insertText(f"    ... ({len(detail_lines) - 10} more lines)\n")
        
        cursor.insertText(full_text)
        
        self.entry_count += 1
        
        # Auto-scroll if enabled
        if self.auto_scroll:
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def log_info(self, message: str, timestamp: bool = True):
        """Log an info message."""
        self.add_entry(message, LogLevel.INFO, timestamp)
    
    def log_success(self, message: str, timestamp: bool = True):
        """Log a success message."""
        self.add_entry(message, LogLevel.SUCCESS, timestamp)
    
    def log_warning(self, message: str, timestamp: bool = True):
        """Log a warning message."""
        self.add_entry(message, LogLevel.WARNING, timestamp)
    
    def log_error(self, message: str, timestamp: bool = True, error_details: str = None):
        """Log an error message with optional details."""
        self.add_entry(message, LogLevel.ERROR, timestamp, details=error_details)
    
    def expand(self, height: int = 300):
        """Expand the log panel with smooth animation."""
        if not self.is_expanded:
            self._max_height = height
            self.animation.setStartValue(self.maximumHeight())
            self.animation.setEndValue(height)
            self.animation.start()
            self.is_expanded = True
    
    def collapse(self):
        """Collapse the log panel with smooth animation."""
        if self.is_expanded:
            self.animation.setStartValue(self.maximumHeight())
            self.animation.setEndValue(200)
            self.animation.start()
            self.is_expanded = False
    
    def toggle_expand(self, height: int = 300):
        """Toggle expand/collapse state with smooth animation."""
        if self.is_expanded:
            self.collapse()
        else:
            self.expand(height)
    
    @pyqtProperty(int)
    def maximumHeight(self):
        """Property for animation."""
        return super().maximumHeight()
    
    @maximumHeight.setter
    def maximumHeight(self, value):
        """Property setter for animation."""
        self.setMaximumHeight(value)

