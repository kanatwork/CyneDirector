# [FILE: gui/shortcuts_panel.py]
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QListWidget, QListWidgetItem, QPushButton, QWidget)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QColor
from config import COLORS, APP_NAME

class ShortcutsPanel(QDialog):
    """Dialog showing all keyboard shortcuts organized by category."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Keyboard Shortcuts - {APP_NAME}")
        self.setFixedSize(600, 700)
        self.setup_ui()
        self.populate_shortcuts()
    
    def setup_ui(self):
        """Setup the shortcuts panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("Keyboard Shortcuts")
        header.setStyleSheet(f"""
            color: {COLORS['accent']};
            font-size: 20px;
            font-weight: 900;
            letter-spacing: 1px;
        """)
        layout.addWidget(header)
        
        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search shortcuts...")
        self.search_input.textChanged.connect(self.filter_shortcuts)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {COLORS['text_main']};
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['accent']};
            }}
        """)
        layout.addWidget(self.search_input)
        
        # Shortcuts list
        self.shortcuts_list = QListWidget()
        self.shortcuts_list.setStyleSheet(f"""
            QListWidget {{
                background: {COLORS['bg_app']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 0px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['selection']};
                border-left: 3px solid {COLORS['accent']};
            }}
        """)
        layout.addWidget(self.shortcuts_list)
        
        # Close button
        btn_close = QPushButton("Close")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        btn_close.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: #121212;
                border: none;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: 700;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: {COLORS['accent_hover']};
            }}
        """)
        layout.addWidget(btn_close)
    
    def populate_shortcuts(self):
        """Populate the shortcuts list with all available shortcuts."""
        self.all_shortcuts = [
            # Navigation
            {"category": "Navigation", "action": "Switch to Media Library", "key": "Ctrl+1"},
            {"category": "Navigation", "action": "Switch to Smart Search", "key": "Ctrl+2"},
            {"category": "Navigation", "action": "Focus search bar", "key": "Ctrl+F"},
            
            # Media
            {"category": "Media", "action": "Add Files", "key": "Ctrl+I"},
            {"category": "Media", "action": "Add Folder", "key": "Ctrl+Shift+I"},
            {"category": "Media", "action": "Select All Files", "key": "Ctrl+A"},
            {"category": "Media", "action": "Open Player (double-click file)", "key": "Double-click"},
            
            # Workflow
            {"category": "Workflow", "action": "Start Indexing", "key": "Ctrl+R"},
            {"category": "Workflow", "action": "Cancel Operation", "key": "Escape"},
            {"category": "Workflow", "action": "Toggle Activity Log", "key": "Ctrl+L"},
            
            # General
            {"category": "General", "action": "Save Project", "key": "Ctrl+S"},
            {"category": "General", "action": "Save Project As", "key": "Ctrl+Shift+S"},
            {"category": "General", "action": "New Project", "key": "Ctrl+N"},
            {"category": "General", "action": "Open Project", "key": "Ctrl+O"},
            {"category": "General", "action": "Export SRT", "key": "Ctrl+E"},
            {"category": "General", "action": "Show Keyboard Shortcuts", "key": "Ctrl+?"},
            {"category": "General", "action": "Help", "key": "F1"},
            
            # Player (shown if player is open)
            {"category": "Player", "action": "Play/Pause", "key": "Space"},
            {"category": "Player", "action": "Stop/Pause", "key": "K"},
            {"category": "Player", "action": "Forward (1x → 2x → 4x → 8x)", "key": "L"},
            {"category": "Player", "action": "Reverse (-1x → -2x → -4x)", "key": "J"},
            {"category": "Player", "action": "Frame Step Forward", "key": "→"},
            {"category": "Player", "action": "Frame Step Back", "key": "←"},
        ]
        
        self.display_shortcuts(self.all_shortcuts)
    
    def display_shortcuts(self, shortcuts):
        """Display shortcuts in the list, grouped by category."""
        self.shortcuts_list.clear()
        
        # Group by category
        categories = {}
        for shortcut in shortcuts:
            cat = shortcut['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(shortcut)
        
        # Display by category
        for category in sorted(categories.keys()):
            # Category header
            header_item = QListWidgetItem(f"  {category}")
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)
            header_item.setForeground(QColor(COLORS['accent']))
            header_item.setFont(header_item.font())
            header_item.font().setBold(True)
            header_item.font().setPointSize(12)
            self.shortcuts_list.addItem(header_item)
            
            # Shortcuts in category
            for shortcut in categories[category]:
                item = QListWidgetItem()
                
                # Create custom widget
                widget = QWidget()
                widget_layout = QHBoxLayout(widget)
                widget_layout.setContentsMargins(10, 8, 10, 8)
                widget_layout.setSpacing(15)
                
                # Action label
                action_label = QLabel(shortcut['action'])
                action_label.setStyleSheet(f"""
                    color: {COLORS['text_main']};
                    font-size: 13px;
                """)
                widget_layout.addWidget(action_label, stretch=1)
                
                # Key badge
                key_label = QLabel(shortcut['key'])
                key_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                key_label.setStyleSheet(f"""
                    QLabel {{
                        background: {COLORS['bg_input']};
                        color: {COLORS['accent']};
                        border: 1px solid {COLORS['border']};
                        border-radius: 4px;
                        padding: 4px 10px;
                        font-size: 11px;
                        font-weight: 700;
                        font-family: 'Consolas', monospace;
                        min-width: 80px;
                    }}
                """)
                widget_layout.addWidget(key_label)
                
                item.setSizeHint(widget.sizeHint())
                self.shortcuts_list.addItem(item)
                self.shortcuts_list.setItemWidget(item, widget)
    
    def filter_shortcuts(self, text):
        """Filter shortcuts based on search text."""
        if not text:
            self.display_shortcuts(self.all_shortcuts)
            return
        
        text_lower = text.lower()
        filtered = [s for s in self.all_shortcuts 
                   if text_lower in s['action'].lower() 
                   or text_lower in s['key'].lower()
                   or text_lower in s['category'].lower()]
        self.display_shortcuts(filtered)

