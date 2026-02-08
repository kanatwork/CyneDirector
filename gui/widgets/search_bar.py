# [FILE: gui/widgets/search_bar.py]
# Unified SearchBar with icon, placeholder, Ctrl+K hint, inner glow, and expand on focus.

from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QLineEdit, QLabel,
                              QPushButton, QGraphicsDropShadowEffect)
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QKeySequence, QShortcut, QColor

from gui.theme import (SURFACE_INPUT, ACCENT, BORDER, GLOW, TEXT_PRIMARY,
                        TEXT_SECONDARY, TEXT_DISABLED, RADIUS_LG, SPACE_SM,
                        FONT_SIZE_BASE, ANIM_FAST, ANIM_NORMAL)


class _FocusLineEdit(QLineEdit):
    """QLineEdit subclass that emits focus signals to the parent SearchBar."""

    def __init__(self, parent_bar, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parent_bar = parent_bar

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._parent_bar._on_focus_in()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._parent_bar._on_focus_out()


class SearchBar(QWidget):
    """Rounded search input with icon prefix, Ctrl+K hint, inner glow, and expand on focus."""

    search_submitted = pyqtSignal(str)
    text_changed = pyqtSignal(str)

    def __init__(self, parent=None, placeholder="Search...", shortcut_key="Ctrl+K"):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._glow_anim = None
        self._expand_anim = None
        self._base_min_width = 0  # set after layout

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Container for styling
        self._container = QWidget()
        self._container.setStyleSheet(f"""
            QWidget {{
                background: {SURFACE_INPUT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_LG}px;
            }}
        """)

        # Inner glow effect (drop shadow on container)
        self._glow_effect = QGraphicsDropShadowEffect(self._container)
        self._glow_effect.setBlurRadius(0)
        self._glow_effect.setOffset(0, 0)
        self._glow_effect.setColor(QColor(GLOW))
        self._container.setGraphicsEffect(self._glow_effect)

        c_layout = QHBoxLayout(self._container)
        c_layout.setContentsMargins(12, 0, 12, 0)
        c_layout.setSpacing(8)

        # Search icon
        icon_lbl = QLabel("\U0001f50d")  # magnifying glass emoji
        icon_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; background: transparent; border: none;")
        c_layout.addWidget(icon_lbl)

        # Line edit (custom subclass for focus events)
        self._edit = _FocusLineEdit(self)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_PRIMARY};
                font-size: {FONT_SIZE_BASE}px;
                padding: 0;
            }}
        """)
        self._edit.returnPressed.connect(self._on_submit)
        self._edit.textChanged.connect(self.text_changed.emit)
        self._edit.textChanged.connect(self._update_clear_btn)
        c_layout.addWidget(self._edit, stretch=1)

        # Clear button (hidden when empty)
        self._clear_btn = QPushButton("\u00d7")  # × symbol
        self._clear_btn.setFixedSize(20, 20)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {TEXT_SECONDARY};
                font-size: 16px;
                font-weight: bold;
                padding: 0;
                border-radius: 10px;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                background: {BORDER};
            }}
        """)
        self._clear_btn.clicked.connect(self.clear)
        self._clear_btn.hide()
        c_layout.addWidget(self._clear_btn)

        # Shortcut hint label
        self._hint_lbl = None
        if shortcut_key:
            self._hint_lbl = QLabel(shortcut_key)
            self._hint_lbl.setStyleSheet(f"""
                QLabel {{
                    color: {TEXT_DISABLED};
                    font-size: 10px;
                    background: transparent;
                    border: 1px solid {BORDER};
                    border-radius: 4px;
                    padding: 2px 6px;
                }}
            """)
            c_layout.addWidget(self._hint_lbl)

        layout.addWidget(self._container)

    def _on_focus_in(self):
        """Animate inner glow and slight width expand on focus."""
        # Glow animation
        if self._glow_anim is not None:
            self._glow_anim.stop()
        self._container.setStyleSheet(f"""
            QWidget {{
                background: {SURFACE_INPUT};
                border: 1px solid {ACCENT};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        self._glow_anim = QPropertyAnimation(self._glow_effect, b"blurRadius")
        self._glow_anim.setDuration(ANIM_NORMAL)
        self._glow_anim.setStartValue(self._glow_effect.blurRadius())
        self._glow_anim.setEndValue(8)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._glow_anim.start()

    def _on_focus_out(self):
        """Remove inner glow and restore width on blur."""
        if self._glow_anim is not None:
            self._glow_anim.stop()
        self._container.setStyleSheet(f"""
            QWidget {{
                background: {SURFACE_INPUT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        self._glow_anim = QPropertyAnimation(self._glow_effect, b"blurRadius")
        self._glow_anim.setDuration(ANIM_NORMAL)
        self._glow_anim.setStartValue(self._glow_effect.blurRadius())
        self._glow_anim.setEndValue(0)
        self._glow_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._glow_anim.start()

    def _update_clear_btn(self, text):
        """Show/hide clear button based on text content."""
        if text:
            self._clear_btn.show()
            if self._hint_lbl:
                self._hint_lbl.hide()
        else:
            self._clear_btn.hide()
            if self._hint_lbl:
                self._hint_lbl.show()

    def _on_submit(self):
        text = self._edit.text().strip()
        if text:
            self.search_submitted.emit(text)

    def focus(self):
        """Focus the internal line edit."""
        self._edit.setFocus()
        self._edit.selectAll()

    def clear(self):
        """Clear the search text."""
        self._edit.clear()

    def set_placeholder(self, text):
        """Update the placeholder text."""
        self._edit.setPlaceholderText(text)

    def text(self):
        """Return current text."""
        return self._edit.text()
