# [FILE: gui/query_builder_dialog.py]
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QComboBox, QCheckBox, QGroupBox, QTextEdit, QScrollArea)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from config import COLORS

class QueryBuilderDialog(QDialog):
    def __init__(self, parent=None, recent_searches=None, saved_searches=None):
        super().__init__(parent)
        self.setWindowTitle("Visual Query Builder")
        self.setMinimumSize(700, 600)
        self.setStyleSheet(f"""
            QDialog {{
                background: {COLORS['bg_main']};
                color: {COLORS['text_main']};
            }}
        """)
        
        self.recent_searches = recent_searches or []
        self.saved_searches = saved_searches or []
        self.query_parts = []
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("Build Complex Search Query")
        header.setStyleSheet(f"color: {COLORS['accent']}; font-size: 18px; font-weight: bold;")
        layout.addWidget(header)
        
        # Query templates
        templates_group = QGroupBox("Query Templates")
        templates_group.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: {COLORS['text_main']};
                font-weight: bold;
            }}
        """)
        templates_layout = QVBoxLayout(templates_group)
        
        templates = [
            ("Simple Search", "person running"),
            ("Boolean AND", "person AND running"),
            ("Boolean OR", "person OR walking"),
            ("Boolean NOT", "person NOT walking"),
            ("Phrase Search", '"hello world"'),
            ("Field Search", "visual:person dialogue:hello"),
            ("Score Range", "person score:>80"),
            ("Temporal", "person walking then sitting"),
            ("Complex", "person AND running NOT walking score:>70")
        ]
        
        self.template_list = QListWidget()
        self.template_list.setMaximumHeight(150)
        self.template_list.setStyleSheet(f"""
            QListWidget {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_main']};
            }}
            QListWidget::item {{
                padding: 5px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QListWidget::item:hover {{
                background: {COLORS['bg_panel']};
            }}
            QListWidget::item:selected {{
                background: {COLORS['accent']};
                color: #121212;
            }}
        """)
        
        for name, query in templates:
            item = QListWidgetItem(f"{name}: {query}")
            item.setData(Qt.ItemDataRole.UserRole, query)
            self.template_list.addItem(item)
        
        self.template_list.itemDoubleClicked.connect(self.use_template)
        templates_layout.addWidget(self.template_list)
        layout.addWidget(templates_group)
        
        # Query builder area
        builder_group = QGroupBox("Build Query")
        builder_group.setStyleSheet(templates_group.styleSheet())
        builder_layout = QVBoxLayout(builder_group)
        
        # Query preview
        preview_label = QLabel("Query Preview:")
        preview_label.setStyleSheet(f"color: {COLORS['text_main']}; font-weight: bold;")
        builder_layout.addWidget(preview_label)
        
        self.query_preview = QTextEdit()
        self.query_preview.setMaximumHeight(100)
        self.query_preview.setReadOnly(True)
        self.query_preview.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_main']};
                padding: 5px;
            }}
        """)
        builder_layout.addWidget(self.query_preview)
        
        # Query components
        components_label = QLabel("Add Components:")
        components_label.setStyleSheet(f"color: {COLORS['text_main']}; font-weight: bold; margin-top: 10px;")
        builder_layout.addWidget(components_label)
        
        # Component input row
        component_row = QHBoxLayout()
        
        self.component_input = QLineEdit()
        self.component_input.setPlaceholderText("Enter search term...")
        self.component_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 5px;
                color: {COLORS['text_main']};
            }}
        """)
        self.component_input.returnPressed.connect(self.add_component)
        component_row.addWidget(self.component_input)
        
        # Operator selector
        self.operator_combo = QComboBox()
        self.operator_combo.addItems(["AND", "OR", "NOT"])
        self.operator_combo.setStyleSheet(f"""
            QComboBox {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 5px;
                color: {COLORS['text_main']};
            }}
        """)
        component_row.addWidget(self.operator_combo)
        
        # Add button
        btn_add = QPushButton("Add")
        btn_add.clicked.connect(self.add_component)
        btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: #121212;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent']}dd;
            }}
        """)
        component_row.addWidget(btn_add)
        
        builder_layout.addLayout(component_row)
        
        # Components list
        self.components_list = QListWidget()
        self.components_list.setMaximumHeight(150)
        self.components_list.setStyleSheet(self.template_list.styleSheet())
        self.components_list.itemDoubleClicked.connect(self.remove_component)
        builder_layout.addWidget(self.components_list)
        
        # Quick actions
        actions_row = QHBoxLayout()
        
        btn_phrase = QPushButton("Add Phrase")
        btn_phrase.clicked.connect(self.add_phrase)
        btn_phrase.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 4px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
            }}
        """)
        actions_row.addWidget(btn_phrase)
        
        btn_field = QPushButton("Add Field")
        btn_field.clicked.connect(self.add_field)
        btn_field.setStyleSheet(btn_phrase.styleSheet())
        actions_row.addWidget(btn_field)
        
        btn_score = QPushButton("Add Score")
        btn_score.clicked.connect(self.add_score)
        btn_score.setStyleSheet(btn_phrase.styleSheet())
        actions_row.addWidget(btn_score)
        
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_query)
        btn_clear.setStyleSheet(btn_phrase.styleSheet())
        actions_row.addWidget(btn_clear)
        
        builder_layout.addLayout(actions_row)
        
        layout.addWidget(builder_group)
        
        # Recent/Saved searches
        history_group = QGroupBox("Query History")
        history_group.setStyleSheet(templates_group.styleSheet())
        history_layout = QVBoxLayout(history_group)
        
        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(100)
        self.history_list.setStyleSheet(self.template_list.styleSheet())
        self.history_list.itemDoubleClicked.connect(self.use_history_item)
        
        # Add recent searches
        for query in self.recent_searches[:10]:
            item = QListWidgetItem(f"Recent: {query}")
            item.setData(Qt.ItemDataRole.UserRole, query)
            self.history_list.addItem(item)
        
        # Add saved searches
        for saved in self.saved_searches:
            query = saved.get('query', '')
            if query:
                item = QListWidgetItem(f"Saved: {query}")
                item.setData(Qt.ItemDataRole.UserRole, query)
                self.history_list.addItem(item)
        
        history_layout.addWidget(self.history_list)
        layout.addWidget(history_group)
        
        # Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['bg_input']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 4px;
                padding: 8px 20px;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
            }}
        """)
        button_row.addWidget(btn_cancel)
        
        btn_ok = QPushButton("Use Query")
        btn_ok.clicked.connect(self.accept)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']};
                color: #121212;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {COLORS['accent']}dd;
            }}
        """)
        button_row.addWidget(btn_ok)
        
        layout.addLayout(button_row)
        
        self.update_preview()
    
    def use_template(self, item):
        """Use a template query."""
        query = item.data(Qt.ItemDataRole.UserRole)
        self.query_preview.setPlainText(query)
        self.query_parts = [query]
        self.update_components_list()
    
    def use_history_item(self, item):
        """Use a history item."""
        query = item.data(Qt.ItemDataRole.UserRole)
        self.query_preview.setPlainText(query)
        self.query_parts = [query]
        self.update_components_list()
    
    def add_component(self):
        """Add a component to the query."""
        text = self.component_input.text().strip()
        if not text:
            return
        
        operator = self.operator_combo.currentText()
        
        if self.query_parts:
            # Add with operator
            self.query_parts.append(f" {operator} {text}")
        else:
            # First component, no operator
            self.query_parts.append(text)
        
        self.component_input.clear()
        self.update_preview()
        self.update_components_list()
    
    def add_phrase(self):
        """Add a phrase component."""
        text = self.component_input.text().strip()
        if not text:
            return
        
        phrase = f'"{text}"'
        operator = self.operator_combo.currentText()
        
        if self.query_parts:
            self.query_parts.append(f" {operator} {phrase}")
        else:
            self.query_parts.append(phrase)
        
        self.component_input.clear()
        self.update_preview()
        self.update_components_list()
    
    def add_field(self):
        """Add a field-specific component."""
        text = self.component_input.text().strip()
        if not text:
            return
        
        # Show field selector
        from PyQt6.QtWidgets import QInputDialog
        field, ok = QInputDialog.getItem(self, "Select Field", "Field:", 
                                        ["visual", "dialogue", "tag", "filename"], 0, False)
        if ok and field:
            field_query = f"{field}:{text}"
            operator = self.operator_combo.currentText()
            
            if self.query_parts:
                self.query_parts.append(f" {operator} {field_query}")
            else:
                self.query_parts.append(field_query)
            
            self.component_input.clear()
            self.update_preview()
            self.update_components_list()
    
    def add_score(self):
        """Add a score range component."""
        from PyQt6.QtWidgets import QInputDialog
        score, ok = QInputDialog.getText(self, "Score Range", "Enter score (e.g., >80, 50-90, <60):")
        if ok and score:
            score_query = f"score:{score}"
            operator = self.operator_combo.currentText()
            
            if self.query_parts:
                self.query_parts.append(f" {operator} {score_query}")
            else:
                self.query_parts.append(score_query)
            
            self.update_preview()
            self.update_components_list()
    
    def remove_component(self, item):
        """Remove a component."""
        index = self.components_list.row(item)
        if 0 <= index < len(self.query_parts):
            self.query_parts.pop(index)
            self.update_preview()
            self.update_components_list()
    
    def clear_query(self):
        """Clear the query."""
        self.query_parts = []
        self.update_preview()
        self.update_components_list()
    
    def update_preview(self):
        """Update query preview."""
        query = "".join(self.query_parts)
        self.query_preview.setPlainText(query)
    
    def update_components_list(self):
        """Update components list display."""
        self.components_list.clear()
        for i, part in enumerate(self.query_parts):
            item = QListWidgetItem(f"{i+1}. {part.strip()}")
            self.components_list.addItem(item)
    
    def get_query(self):
        """Get the final query string."""
        return "".join(self.query_parts).strip()





