# [FILE: gui/embedded_player.py]
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QHBoxLayout, QLabel, QSlider, QStyle, QSizePolicy
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QMouseEvent
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
        logger.debug(f"ClickableVideoWidget clicked. Visible: {self.isVisible()}")
        if event.button() == Qt.MouseButton.LeftButton:
            if self.parent_player:
                self.parent_player.toggle_play()
                self.parent_player.setFocus()
        super().mousePressEvent(event)

class EmbeddedPlayerWidget(QWidget):
    """Embedded video player widget for the main window preview panel."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("EmbeddedPlayerWidget initialized")
        self.setStyleSheet(f"background: {COLORS['bg_app']}; color: {COLORS['text_main']};")
        
        # Enable Keyboard Shortcuts
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Callback for fullscreen mode
        self.fullscreen_callback = None
        self.current_file_path = None
        
        # --- Media Backend ---
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        # --- Playback State ---
        self.is_dragging_slider = False
        self.playback_rate = 1.0
        self.frame_duration = 40  # Default to 25fps (40ms)
        
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
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        
        layout.addWidget(self.video_widget)
        self.media_player.setVideoOutput(self.video_widget)
        
        # 2. Minimal Controls Container
        self.controls = QWidget()
        self.controls.setFixedHeight(60)
        self.controls.setStyleSheet(f"background: {COLORS['bg_panel']}; border-top: 1px solid {COLORS['border']};")
        ctrl_layout = QVBoxLayout(self.controls)
        ctrl_layout.setContentsMargins(10, 5, 10, 5)
        
        # A. Timeline Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height: 4px; background: {COLORS['border']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {COLORS['accent']}; width: 12px; margin: -4px 0; border-radius: 6px; }}
            QSlider::sub-page:horizontal {{ background: {COLORS['accent']}; border-radius: 2px; }}
        """)
        ctrl_layout.addWidget(self.slider)

        # B. Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        # Play/Pause Button
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setFixedSize(32, 32)
        self.btn_play.setStyleSheet(f"""
            QPushButton {{ border: 1px solid {COLORS['text_disabled']}; border-radius: 16px; background: {COLORS['border']}; }}
            QPushButton:hover {{ background: {COLORS['surface_hover']}; border-color: {COLORS['accent']}; }}
        """)
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.btn_play)
        
        # Time Label
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet(f"font-family: monospace; font-size: 11px; color: {COLORS['text_main']}; font-weight: bold;")
        btn_row.addWidget(self.lbl_time)
        
        btn_row.addStretch()
        
        # Fullscreen Button
        self.btn_fullscreen = QPushButton("FULLSCREEN")
        self.btn_fullscreen.setStyleSheet(f"""
            QPushButton {{ 
                background: transparent; 
                border: 1px solid {COLORS['border']}; 
                color: {COLORS['text_dim']}; 
                padding: 4px 8px; 
                font-size: 10px; 
                font-weight: bold;
            }}
            QPushButton:hover {{ 
                border-color: {COLORS['accent']}; 
                color: {COLORS['accent']}; 
            }}
        """)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        self.btn_fullscreen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.btn_fullscreen)

        ctrl_layout.addLayout(btn_row)
        layout.addWidget(self.controls)

    def load_video(self, file_path, start_time_sec=0):
        """Load a video file into the player."""
        logger.debug(f"Loading video: {file_path} at {start_time_sec}s")
        self.current_file_path = file_path
        
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
        self.setFocus()

    def toggle_play(self):
        """Toggle play/pause."""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.setPlaybackRate(self.playback_rate if self.playback_rate > 0 else 1.0)
            self.media_player.play()

    def stop(self):
        """Stop playback."""
        self.media_player.stop()
        self.current_file_path = None

    def media_state_changed(self, state):
        """Update play/pause button icon based on playback state."""
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def set_volume(self, value):
        """Set volume (0-100)."""
        self.audio_output.setVolume(value / 100.0)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode by calling the callback."""
        logger.debug("Attempting to toggle fullscreen")
        if self.fullscreen_callback and self.current_file_path:
            logger.debug("Calling fullscreen_callback")
            self.fullscreen_callback(self.current_file_path)

    # --- KEYBOARD CONTROLS ---
    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key.Key_Space:
            self.toggle_play()
        elif key == Qt.Key.Key_K:  # STOP/PAUSE
            self.media_player.pause()
            self.playback_rate = 0
            self.update_speed_label()
        elif key == Qt.Key.Key_L:  # FORWARD
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
                self.playback_rate = 1.0
            else:
                if self.playback_rate < 1:
                    self.playback_rate = 1.0
                else:
                    self.playback_rate = min(self.playback_rate * 2, 8.0)
            self.media_player.setPlaybackRate(self.playback_rate)
            self.update_speed_label()
        elif key == Qt.Key.Key_J:  # REVERSE
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
                self.playback_rate = -1.0
            else:
                if self.playback_rate > -1:
                    self.playback_rate = -1.0
                else:
                    self.playback_rate = max(self.playback_rate * 2, -8.0)
            self.media_player.setPlaybackRate(self.playback_rate)
            self.update_speed_label()
        elif key == Qt.Key.Key_Right:  # FRAME STEP FORWARD
            self.media_player.pause()
            self.media_player.setPosition(self.media_player.position() + self.frame_duration)
        elif key == Qt.Key.Key_Left:  # FRAME STEP BACK
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
        self.frame_duration = 40

    def set_position(self, position):
        self.update_time_label(position, self.media_player.duration())

    def update_time_label(self, current_ms, total_ms):
        """Update the time display label."""
        def fmt(ms):
            seconds = (ms // 1000) % 60
            minutes = (ms // 60000)
            return f"{minutes:02}:{seconds:02}"
        self.lbl_time.setText(f"{fmt(current_ms)} / {fmt(total_ms)}")

    def update_speed_label(self):
        """Update playback speed label (not shown in embedded player, but kept for compatibility)."""
        rate = self.media_player.playbackRate()
        # Speed label not shown in embedded player, but we keep the method for compatibility

    def handle_errors(self):
        """Handle media player errors."""
        self.btn_play.setEnabled(False)
        self.lbl_time.setText("Error")
        logger.error("Media player error occurred")
