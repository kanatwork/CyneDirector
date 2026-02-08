# [FILE: gui/widgets/status_indicator.py]
# Pulsing dot + label for status bar device info.

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty, QSize
from PyQt6.QtGui import QPainter, QColor, QPen

from gui.theme import SUCCESS, TEXT_SECONDARY, BORDER, FONT_SIZE_SM, ANIM_SLOW


class _PulsingDot(QWidget):
    """Small circle that pulses opacity when active."""

    def __init__(self, color=SUCCESS, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._color = QColor(color)
        self._opacity = 1.0

        self._anim = QPropertyAnimation(self, b"dot_opacity")
        self._anim.setDuration(2000)
        self._anim.setStartValue(0.5)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)  # infinite

    @pyqtProperty(float)
    def dot_opacity(self):
        return self._opacity

    @dot_opacity.setter
    def dot_opacity(self, value):
        self._opacity = value
        self.update()

    def set_color(self, color_str):
        self._color = QColor(color_str)
        self.update()

    def start_pulse(self):
        self._anim.start()

    def stop_pulse(self):
        self._anim.stop()
        self._opacity = 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(self._opacity)
        p.setPen(QPen(c.darker(130), 0.5))
        p.setBrush(c)
        p.drawEllipse(1, 1, 6, 6)
        p.end()


class StatusIndicator(QWidget):
    """Pulsing dot + text label for system status display."""

    def __init__(self, text="", color=SUCCESS, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = _PulsingDot(color, self)
        layout.addWidget(self._dot)

        self._label = QLabel(text)
        self._label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_SECONDARY};
                font-size: 11px;
                background: transparent;
            }}
        """)
        layout.addWidget(self._label)

    def set_status(self, text, color=None):
        """Update the label text and optionally the dot color."""
        self._label.setText(text)
        if color:
            self._dot.set_color(color)

    def set_active(self, active):
        """Start or stop the pulsing animation."""
        if active:
            self._dot.start_pulse()
        else:
            self._dot.stop_pulse()

    def sizeHint(self):
        return QSize(120, 20)
