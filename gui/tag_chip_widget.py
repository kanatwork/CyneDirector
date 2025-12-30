# [FILE: gui/tag_chip_widget.py]
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QPushButton, QLabel, 
                             QLineEdit, QCompleter, QVBoxLayout, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QStringListModel
from PyQt6.QtGui import QColor
from config import COLORS
from core.tags import get_tag_bank

class TagChip(QPushButton):
    """Individual tag chip widget."""
    remove_requested = pyqtSignal(str)  # Emits tag text when remove is clicked
    
    def __init__(self, tag_text, category=None, parent=None):
        super().__init__(parent)
        self.tag_text = tag_text
        self.category = category or self._categorize_tag(tag_text)
        
        # Set text and styling
        self.setText(f"{tag_text} ×")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Color coding by category
        color_map = {
            'object': COLORS['accent'],
            'action': '#FFA500',  # Orange
            'person': '#4CAF50',  # Green
            'nature': '#00BCD4',  # Cyan
            'color': '#E91E63',   # Pink
            'cinematography': '#9C27B0',  # Purple
            'other': COLORS['text_dim']
        }
        
        bg_color = color_map.get(self.category, color_map['other'])
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: #121212;
                border: none;
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
                max-height: 24px;
            }}
            QPushButton:hover {{
                background: {bg_color};
                opacity: 0.8;
            }}
        """)
        
        self.clicked.connect(lambda: self.remove_requested.emit(self.tag_text))
    
    def _categorize_tag(self, tag):
        """Categorize tag based on content."""
        tag_lower = tag.lower()
        
        # Objects/Props
        object_keywords = ['phone', 'laptop', 'car', 'cup', 'book', 'camera', 'bag', 'chair', 'table']
        if any(kw in tag_lower for kw in object_keywords):
            return 'object'
        
        # Actions
        action_keywords = ['running', 'walking', 'sitting', 'talking', 'eating', 'drinking', 'working']
        if any(kw in tag_lower for kw in action_keywords) or tag_lower.endswith('ing'):
            return 'action'
        
        # People
        person_keywords = ['person', 'man', 'woman', 'child', 'people', 'crowd', 'face']
        if any(kw in tag_lower for kw in person_keywords):
            return 'person'
        
        # Nature
        nature_keywords = ['tree', 'flower', 'ocean', 'mountain', 'sky', 'sun', 'moon', 'rain']
        if any(kw in tag_lower for kw in nature_keywords):
            return 'nature'
        
        # Colors
        color_keywords = ['red', 'blue', 'green', 'yellow', 'purple', 'orange', 'black', 'white']
        if tag_lower in color_keywords:
            return 'color'
        
        # Cinematography
        cine_keywords = ['close', 'wide', 'aerial', 'shot', 'pan', 'zoom', 'golden hour']
        if any(kw in tag_lower for kw in cine_keywords):
            return 'cinematography'
        
        return 'other'


class TagInputWidget(QWidget):
    """Widget for managing tags with chips and autocomplete."""
    tags_changed = pyqtSignal(list)  # Emits list of tags when changed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tags = []
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Chips container (scrollable)
        self.chips_scroll = QScrollArea()
        self.chips_scroll.setWidgetResizable(True)
        self.chips_scroll.setFixedHeight(80)
        self.chips_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                background: {COLORS['bg_input']};
            }}
        """)
        self.chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.chips_widget = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_widget)
        self.chips_layout.setContentsMargins(8, 8, 8, 8)
        self.chips_layout.setSpacing(6)
        self.chips_layout.addStretch()
        
        self.chips_scroll.setWidget(self.chips_widget)
        layout.addWidget(self.chips_scroll)
        
        # Input field with autocomplete
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Type a tag and press Enter...")
        self.tag_input.returnPressed.connect(self.add_tag_from_input)
        self.tag_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 10px;
                color: {COLORS['text_main']};
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS['accent']};
            }}
        """)
        
        # Setup autocomplete
        tag_bank = get_tag_bank()
        completer = QCompleter(tag_bank, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.tag_input.setCompleter(completer)
        
        layout.addWidget(self.tag_input)
    
    def add_tag(self, tag_text):
        """Add a tag chip."""
        tag_text = tag_text.strip()
        if not tag_text or tag_text in self.tags:
            return
        
        self.tags.append(tag_text)
        chip = TagChip(tag_text)
        chip.remove_requested.connect(self.remove_tag)
        
        # Insert before stretch
        self.chips_layout.insertWidget(self.chips_layout.count() - 1, chip)
        self.tags_changed.emit(self.tags.copy())
    
    def add_tag_from_input(self):
        """Add tag from input field."""
        text = self.tag_input.text().strip()
        if text:
            self.add_tag(text)
            self.tag_input.clear()
    
    def remove_tag(self, tag_text):
        """Remove a tag."""
        if tag_text in self.tags:
            self.tags.remove(tag_text)
            # Remove chip widget
            for i in range(self.chips_layout.count() - 1):  # Exclude stretch
                item = self.chips_layout.itemAt(i)
                if item and item.widget():
                    chip = item.widget()
                    if isinstance(chip, TagChip) and chip.tag_text == tag_text:
                        chip.deleteLater()
                        break
            self.tags_changed.emit(self.tags.copy())
    
    def set_tags(self, tags):
        """Set tags (replaces existing)."""
        # Clear existing chips
        for i in range(self.chips_layout.count() - 1, -1, -1):
            item = self.chips_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        
        self.tags = []
        for tag in tags:
            self.add_tag(tag)
    
    def get_tags(self):
        """Get current tags."""
        return self.tags.copy()
    
    def clear(self):
        """Clear all tags."""
        self.set_tags([])


