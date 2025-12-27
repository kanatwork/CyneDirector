import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QLabel, QSlider, QStyle, QFrame)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

class PlayerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CyneDirector Player")
        self.resize(1000, 650)
        self.setStyleSheet("background: #000; color: #FFF;")
        
        # --- Media Backend ---
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        # --- Playback State ---
        self.is_dragging_slider = False
        self.playback_rate = 1.0
        self.frame_duration = 40  # Default to ~25fps (40ms), updates on load

        # --- UI Setup ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Video Surface
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget)
        self.media_player.setVideoOutput(self.video_widget)
        
        # 2. Controls Container
        self.controls = QWidget()
        self.controls.setFixedHeight(90)
        self.controls.setStyleSheet("background: #1E1E1E; border-top: 1px solid #333;")
        ctrl_layout = QVBoxLayout(self.controls)
        ctrl_layout.setContentsMargins(15, 5, 15, 10)
        
        # A. Timeline Slider
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #333; border-radius: 3px; }
            QSlider::handle:horizontal { background: #00E676; width: 14px; margin: -5px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #00E676; border-radius: 3px; }
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
        self.btn_play.setStyleSheet("border: 1px solid #555; border-radius: 20px; background: #333;")
        self.btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_row.addWidget(self.btn_play)
        
        # Time Label
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("font-family: monospace; font-size: 13px; color: #CCC; font-weight: bold;")
        btn_row.addWidget(self.lbl_time)
        
        # Speed Label (Feedback for JKL)
        self.lbl_speed = QLabel("1x")
        self.lbl_speed.setStyleSheet("color: #777; font-size: 11px; margin-left: 10px;")
        btn_row.addWidget(self.lbl_speed)

        btn_row.addStretch()
        
        # Volume Slider
        vol_icon = QLabel("🔊")
        btn_row.addWidget(vol_icon)
        
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.valueChanged.connect(self.audio_output.setVolume) # 0-1.0 float in Qt6, logic handled below
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.vol_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #444; }
            QSlider::handle:horizontal { background: #FFF; width: 10px; margin: -3px 0; border-radius: 5px; }
            QSlider::sub-page:horizontal { background: #AAA; }
        """)
        btn_row.addWidget(self.vol_slider)

        ctrl_layout.addLayout(btn_row)
        layout.addWidget(self.controls)
        
        # --- Signals ---
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)
        self.media_player.errorOccurred.connect(self.handle_errors)
        
        # Initial Volume
        self.set_volume(70)

    # --- KEYBOARD CONTROLS (The "Pro" Features) ---
    def keyPressEvent(self, event):
        key = event.key()
        
        if key == Qt.Key.Key_Space:
            self.toggle_play()
            
        elif key == Qt.Key.Key_K: # STOP/PAUSE
            self.media_player.pause()
            self.playback_rate = 0
            self.update_speed_label()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

        elif key == Qt.Key.Key_L: # FORWARD (1x -> 2x -> 4x)
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
                self.playback_rate = 1.0
            else:
                if self.playback_rate < 1: self.playback_rate = 1.0
                else: self.playback_rate = min(self.playback_rate * 2, 8.0)
            
            self.media_player.setPlaybackRate(self.playback_rate)
            self.update_speed_label()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

        elif key == Qt.Key.Key_J: # REVERSE (1x -> 2x -> 4x)
            # NOTE: Reverse playback support depends on codec. 
            # If standard backend fails, this might just pause or jump.
            if self.media_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.play()
                self.playback_rate = -1.0
            else:
                if self.playback_rate > -1: self.playback_rate = -1.0
                else: self.playback_rate = max(self.playback_rate * 2, -8.0) # -2, -4...
            
            self.media_player.setPlaybackRate(self.playback_rate)
            self.update_speed_label()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

        elif key == Qt.Key.Key_Right: # FRAME STEP FORWARD
            self.media_player.pause()
            pos = self.media_player.position()
            self.media_player.setPosition(pos + self.frame_duration)
            
        elif key == Qt.Key.Key_Left: # FRAME STEP BACK
            self.media_player.pause()
            pos = self.media_player.position()
            self.media_player.setPosition(max(0, pos - self.frame_duration))

    def update_speed_label(self):
        rate = self.media_player.playbackRate()
        self.lbl_speed.setText(f"{rate}x")

    def load_video(self, file_path, start_time_sec=0):
        # Reset state
        self.playback_rate = 1.0
        self.media_player.setPlaybackRate(1.0)
        self.update_speed_label()

        source = QUrl.fromLocalFile(file_path)
        self.media_player.setSource(source)
        self.media_player.play()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        
        if start_time_sec > 0:
            self.media_player.setPosition(int(start_time_sec * 1000))
        
        self.show()
        self.raise_()
        self.activateWindow() # Force focus for keyboard events

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            self.media_player.setPlaybackRate(1.0) # Reset speed on play
            self.media_player.play()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self.update_speed_label()

    def set_volume(self, value):
        # Qt6 AudioOutput takes float 0.0 - 1.0
        self.audio_output.setVolume(value / 100.0)

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
        # Approximate frame duration (assuming 25fps if unknown)
        self.frame_duration = 40 

    def set_position(self, position):
        self.update_time_label(position, self.media_player.duration())

    def update_time_label(self, current_ms, total_ms):
        def fmt(ms):
            seconds = (ms // 1000) % 60
            minutes = (ms // 60000)
            return f"{minutes:02}:{seconds:02}"
        self.lbl_time.setText(f"{fmt(current_ms)} / {fmt(total_ms)}")

    def handle_errors(self):
        self.btn_play.setEnabled(False)
        self.lbl_time.setText("Error: Could not load media")
        print(f"Player Error: {self.media_player.errorString()}")

    def closeEvent(self, event):
        self.media_player.stop()
        self.media_player.setSource(QUrl()) # Release file lock
        event.accept()