# [FILE: gui/player_window.py]
import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QLabel, QSlider, QStyle, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, QUrl, QEvent
from PyQt6.QtGui import QIcon, QAction, QMouseEvent
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from config import COLORS
from core.logger import get_logger

logger = get_logger(__name__)

class ClickableVideoWidget(QVideoWidget):
    """A VideoWidget that accepts clicks to toggle play/pause and grab focus."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_player = parent

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.parent_player:
                self.parent_player.toggle_play()
                self.parent_player.setFocus() # CRITICAL: Regain keyboard focus
        super().mousePressEvent(event)

class PlayerWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("PlayerWindow initialized")
        self.setStyleSheet(f"background: {COLORS['bg_app']}; color: {COLORS['text_main']};")
        
        # Enable Keyboard Shortcuts (Space, J, K, L, Arrows)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # --- Media Backend ---
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        # --- Playback State ---
        self.is_dragging_slider = False
        self.playback_rate = 1.0
        self.frame_duration = 40 # Default to 25fps (40ms), updated on load
        
        self.setup_ui()
        
        # --- Signals ---
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.media_player.errorOccurred.connect(self.handle_errors)
        self.media_player.playbackStateChanged.connect(self.media_state_changed)
        
        # Default Volume
        self.set_volume(70)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 1. Video Surface (Custom Clickable)
        self.video_widget = ClickableVideoWidget(self)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Prevent video stretching
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        
        layout.addWidget(self.video_widget)
        self.media_player.setVideoOutput(self.video_widget)
        
        # 2. Controls Container
        self.controls = QWidget()
        self.controls.setFixedHeight(90)
        self.controls.setStyleSheet(f"background: {COLORS['bg_panel']}; border-top: 1px solid {COLORS['border']};")
        ctrl_layout = QVBoxLayout(self.controls)
        ctrl_layout.setContentsMargins(15, 5, 15, 10)
        
        # A. Timeline Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 6px; background: {COLORS['border']}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {COLORS['accent']}; width: 14px; margin: -5px 0; border-radius: 7px; }}
            QSlider::sub-page:horizontal {{ background: {COLORS['accent']}; border-radius: 3px; }}
        """)
        ctrl_layout.addWidget(self.slider)

        # B. Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        # Play/Pause Button
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setFixedSize(40, 40)
        self.btn_play.setStyleSheet(f"""
            QPushButton {{ border: 1px solid {COLORS['text_disabled']}; border-radius: 20px; background: {COLORS['border']}; }}
            QPushButton:hover {{ background: {COLORS['surface_hover']}; border-color: {COLORS['accent']}; }}
        """)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.btn_play)
        
        # Time Label
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet(f"font-family: monospace; font-size: 13px; color: {COLORS['text_main']}; font-weight: bold;")
        btn_row.addWidget(self.lbl_time)
        
        # Speed Label
        self.lbl_speed = QLabel("1x")
        self.lbl_speed.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px; margin-left: 10px;")
        btn_row.addWidget(self.lbl_speed)

        btn_row.addStretch()
        
        # Volume Slider
        vol_icon = QLabel("VOL")
        vol_icon.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        btn_row.addWidget(vol_icon)
        
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {COLORS['border']}; }}
            QSlider::handle:horizontal {{ background: {COLORS['text_main']}; width: 10px; margin: -3px 0; border-radius: 5px; }}
            QSlider::sub-page:horizontal {{ background: {COLORS['text_dim']}; }}
        """)
        btn_row.addWidget(self.vol_slider)

        ctrl_layout.addLayout(btn_row)
        layout.addWidget(self.controls)

    def load_video(self, file_path, start_time_sec=0):
        logger.debug(f"Loading video: {file_path} at {start_time_sec}s")
        # Stop previous playback
        self.media_player.stop()
        self.playback_rate = 1.0
        self.media_player.setPlaybackRate(1.0)
        self.update_speed_label()

        source = QUrl.fromLocalFile(file_path)
        self.media_player.setSource(source)
        
        if start_time_sec > 0:
            self.media_player.setPosition(int(start_time_sec * 1000))
        
        self.media_player.play()
        self.setFocus() # Grab keyboard focus immediately

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.setPlaybackRate(self.playback_rate if self.playback_rate > 0 else 1.0)
            self.media_player.play()

    def media_state_changed(self, state):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)

    # --- KEYBOARD CONTROLS (J-K-L NLE Style) ---
    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key.Key_Space:
            self.toggle_play()
            
        elif key == Qt.Key.Key_K: # STOP/PAUSE
            self.media_player.pause()
            self.playback_rate = 0
            self.update_speed_label()

        elif key == Qt.Key.Key_L: # FORWARD (1x -> 2x -> 4x -> 8x)
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
                self.playback_rate = 1.0
            else:
                if self.playback_rate < 1: self.playback_rate = 1.0
                else: self.playback_rate = min(self.playback_rate * 2, 8.0)
            
            self.media_player.setPlaybackRate(self.playback_rate)
            self.update_speed_label()

        elif key == Qt.Key.Key_J: # REVERSE (-1x -> -2x -> -4x)
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
                self.playback_rate = -1.0
            else:
                if self.playback_rate > -1: self.playback_rate = -1.0
                else: self.playback_rate = max(self.playback_rate * 2, -8.0) 
            
            self.media_player.setPlaybackRate(self.playback_rate)
            self.update_speed_label()

        elif key == Qt.Key.Key_Right: # FRAME STEP FORWARD
            self.media_player.pause()
            self.media_player.setPosition(self.media_player.position() + self.frame_duration)
            
        elif key == Qt.Key.Key_Left: # FRAME STEP BACK
            self.media_player.pause()
            self.media_player.setPosition(max(0, self.media_player.position() - self.frame_duration))

    # --- Slider & Time Logic ---
    def on_slider_pressed(self):
        self.is_dragging_slider = True

    def on_slider_released(self):
        self.is_dragging_slider = False
        self.media_player.setPosition(self.slider.value())

    def position_changed(self, position):
        if not self.is_dragging_slider:
            self.slider.setValue(position)
        self.update_time_label(position, self.media_player.duration())

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)
        # Approximate frame duration check could go here if we had metadata
        self.frame_duration = 40 

    def set_position(self, position):
        self.update_time_label(position, self.media_player.duration())

    def update_time_label(self, current_ms, total_ms):
        def fmt(ms):
            seconds = (ms // 1000) % 60
            minutes = (ms // 60000)
            return f"{minutes:02}:{seconds:02}"
        self.lbl_time.setText(f"{fmt(current_ms)} / {fmt(total_ms)}")

    def update_speed_label(self):
        rate = self.media_player.playbackRate()
        self.lbl_speed.setText(f"{rate}x")

    def handle_errors(self):
        self.btn_play.setEnabled(False)
        self.lbl_time.setText("Error")

    def closeEvent(self, event):
        self.media_player.stop()
        self.media_player.setSource(QUrl()) 
        event.accept()
