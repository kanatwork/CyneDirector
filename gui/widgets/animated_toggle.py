# [FILE: gui/widgets/animated_toggle.py]
# iOS-style animated toggle switch (replaces QCheckBox for settings).

from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRectF, pyqtProperty, QSize
from PyQt6.QtGui import QPainter, QColor, QPen

from gui.theme import ACCENT, BORDER, TEXT_PRIMARY, SURFACE_INPUT, ANIM_FAST


class AnimatedToggle(QCheckBox):
    """iOS-style sliding toggle with smooth animation."""

    _TRACK_W = 44
    _TRACK_H = 24
    _THUMB_R = 9  # radius of thumb circle

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self._TRACK_W, self._TRACK_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Internal animated position (0.0 = off/left, 1.0 = on/right)
        self._position = 0.0

        self._anim = QPropertyAnimation(self, b"thumb_position")
        self._anim.setDuration(ANIM_FAST)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.stateChanged.connect(self._on_state_changed)

    # ── Animated property ────────────────────────────────────
    @pyqtProperty(float)
    def thumb_position(self):
        return self._position

    @thumb_position.setter
    def thumb_position(self, value):
        self._position = value
        self.update()

    # ── State change handler ─────────────────────────────────
    def _on_state_changed(self, state):
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(1.0 if state else 0.0)
        self._anim.start()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        r = h / 2

        # Track color: blend from off to on
        off_color = QColor(SURFACE_INPUT)
        on_color = QColor(ACCENT)
        track_color = _lerp_color(off_color, on_color, self._position)

        # Draw track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Subtle border
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

        # Thumb
        thumb_x = self._THUMB_R + 3 + self._position * (w - 2 * (self._THUMB_R + 3))
        thumb_y = h / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TEXT_PRIMARY))
        p.drawEllipse(QRectF(thumb_x - self._THUMB_R, thumb_y - self._THUMB_R,
                              self._THUMB_R * 2, self._THUMB_R * 2))
        p.end()

    def sizeHint(self):
        return QSize(self._TRACK_W, self._TRACK_H)

    # Override to prevent default checkbox drawing
    def hitButton(self, pos):
        return self.contentsRect().contains(pos)


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    """Linearly interpolate between two QColors."""
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )
