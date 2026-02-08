# [FILE: gui/widgets/thumbnail_card.py]
# Grid-view card: thumbnail + filename + status badges.
# Hover elevation shadow, duration overlay, skeleton shimmer.

import os
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QColor, QPainter, QLinearGradient
from PyQt6.QtWidgets import QGraphicsDropShadowEffect

from gui.theme import (BACKGROUND, SURFACE, SURFACE_HOVER, BORDER, GLOW, ACCENT,
                        TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DISABLED, SUCCESS,
                        WARNING, RADIUS_MD, SPACE_SM, ANIM_FAST, ANIM_NORMAL)

CARD_WIDTH = 180
THUMB_HEIGHT = 100  # ~16:9 for 180 wide


def _format_duration(seconds):
    """Format seconds into M:SS or H:MM:SS string."""
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"


class ShimmerLabel(QLabel):
    """QLabel that paints an animated gradient sweep when in loading mode."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._shimmer_offset = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def set_loading(self, loading):
        self._loading = loading
        if loading:
            self._shimmer_offset = 0.0
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _tick(self):
        self._shimmer_offset += 0.03
        if self._shimmer_offset > 1.5:
            self._shimmer_offset = -0.5
        self.update()

    def paintEvent(self, event):
        if self._loading:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()

            # Base dark background
            painter.fillRect(0, 0, w, h, QColor(BACKGROUND))

            # Animated shimmer gradient
            grad = QLinearGradient(0, 0, w, 0)
            dark = QColor(BACKGROUND)
            light = QColor("#2a2a2a")

            pos = self._shimmer_offset
            grad.setColorAt(max(0.0, pos - 0.3), dark)
            grad.setColorAt(max(0.0, min(1.0, pos)), light)
            grad.setColorAt(min(1.0, pos + 0.3), dark)

            painter.fillRect(0, 0, w, h, grad)
            painter.end()
        else:
            super().paintEvent(event)


class ThumbnailCard(QFrame):
    """A card widget for grid view display of a video file."""

    clicked = pyqtSignal(str)
    double_clicked = pyqtSignal(str)

    def __init__(self, video_path, thumbnail_path=None, title="",
                 status_icons=None, duration=None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self._hover_anim = None
        self.setFixedWidth(CARD_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            ThumbnailCard {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
            ThumbnailCard:hover {{
                background: {SURFACE_HOVER};
                border-color: {ACCENT};
            }}
        """)

        # Drop shadow effect for hover elevation
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(GLOW))
        self.setGraphicsEffect(self._shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Thumbnail (with shimmer support)
        self.thumb_label = ShimmerLabel()
        self.thumb_label.setFixedSize(CARD_WIDTH - 12, THUMB_HEIGHT)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet(f"""
            QLabel {{
                background: {BACKGROUND};
                border-radius: 4px;
                color: {TEXT_DISABLED};
                font-size: 24px;
            }}
        """)

        if thumbnail_path and os.path.isfile(thumbnail_path):
            pix = QPixmap(thumbnail_path)
            if not pix.isNull():
                self.thumb_label.setPixmap(
                    pix.scaled(self.thumb_label.size(),
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
                )
            else:
                self.thumb_label.setText("\U0001f3ac")  # film clapper
        else:
            self.thumb_label.setText("\U0001f3ac")

        layout.addWidget(self.thumb_label)

        # Duration overlay (bottom-right of thumbnail)
        if duration is not None:
            dur_text = _format_duration(duration)
            if dur_text:
                self._duration_label = QLabel(dur_text, self.thumb_label)
                self._duration_label.setStyleSheet("""
                    QLabel {
                        background: rgba(0, 0, 0, 0.7);
                        color: #ffffff;
                        font-size: 10px;
                        font-weight: 600;
                        padding: 2px 6px;
                        border-radius: 4px;
                    }
                """)
                self._duration_label.adjustSize()
                # Position bottom-right of thumbnail
                lbl_w = self._duration_label.width()
                lbl_h = self._duration_label.height()
                self._duration_label.move(
                    self.thumb_label.width() - lbl_w - 4,
                    self.thumb_label.height() - lbl_h - 4
                )

        # Title
        display_title = title or os.path.basename(video_path)
        title_lbl = QLabel(display_title)
        title_lbl.setWordWrap(True)
        title_lbl.setMaximumHeight(36)
        title_lbl.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }}
        """)
        layout.addWidget(title_lbl)

        # Status badges row
        if status_icons:
            badge_layout = QHBoxLayout()
            badge_layout.setContentsMargins(0, 0, 0, 0)
            badge_layout.setSpacing(4)
            for icon_text, color in status_icons:
                badge = QLabel(icon_text)
                badge.setStyleSheet(f"""
                    QLabel {{
                        color: {color};
                        font-size: 12px;
                        background: transparent;
                    }}
                """)
                badge_layout.addWidget(badge)
            badge_layout.addStretch()
            layout.addLayout(badge_layout)

    def set_loading(self, loading):
        """Toggle shimmer loading state on the thumbnail."""
        self.thumb_label.set_loading(loading)

    def set_thumbnail(self, thumbnail_path):
        """Set a thumbnail after loading (stops shimmer)."""
        self.thumb_label.set_loading(False)
        if thumbnail_path and os.path.isfile(thumbnail_path):
            pix = QPixmap(thumbnail_path)
            if not pix.isNull():
                self.thumb_label.setPixmap(
                    pix.scaled(self.thumb_label.size(),
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
                )

    def enterEvent(self, event):
        """Animate shadow elevation on hover."""
        if self._hover_anim is not None:
            self._hover_anim.stop()
        self._hover_anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._hover_anim.setDuration(ANIM_FAST)
        self._hover_anim.setStartValue(self._shadow.blurRadius())
        self._hover_anim.setEndValue(12)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.start()

        # Also animate offset for "lifted" feel
        self._hover_offset_anim = QPropertyAnimation(self._shadow, b"offset")
        self._hover_offset_anim.setDuration(ANIM_FAST)
        self._hover_offset_anim.setStartValue(self._shadow.offset())
        self._hover_offset_anim.setEndValue(self._shadow.offset().__class__(0, 2))
        self._hover_offset_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_offset_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Animate shadow back to zero on leave."""
        if self._hover_anim is not None:
            self._hover_anim.stop()
        self._hover_anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._hover_anim.setDuration(ANIM_FAST)
        self._hover_anim.setStartValue(self._shadow.blurRadius())
        self._hover_anim.setEndValue(0)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._hover_anim.start()

        if hasattr(self, '_hover_offset_anim') and self._hover_offset_anim is not None:
            self._hover_offset_anim.stop()
        self._hover_offset_anim = QPropertyAnimation(self._shadow, b"offset")
        self._hover_offset_anim.setDuration(ANIM_FAST)
        self._hover_offset_anim.setStartValue(self._shadow.offset())
        from PyQt6.QtCore import QPointF
        self._hover_offset_anim.setEndValue(QPointF(0, 0))
        self._hover_offset_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._hover_offset_anim.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.video_path)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.video_path)
        super().mouseDoubleClickEvent(event)

    def sizeHint(self):
        return QSize(CARD_WIDTH, THUMB_HEIGHT + 60)
