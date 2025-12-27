import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QHBoxLayout, 
                             QLabel, QSlider, QStyle, QFrame)
from PyQt6.QtCore import Qt, QUrl, QTime
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

class PlayerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CyneDirector Player")
        self.resize(900, 600)
        self.setStyleSheet("background: #000; color: #FFF;")
        
        # --- Media Backend ---
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        # State
        self.is_dragging_slider = False

        # --- UI Setup ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Video Surface
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget)
        self.media_player.setVideoOutput(self.video_widget)
        
        # Controls Bar
        self.controls = QWidget()
        self.controls.setFixedHeight(80)
        self.controls.setStyleSheet("background: #1E1E1E; border-top: 1px solid #333;")
        ctrl_layout = QVBoxLayout(self.controls)
        ctrl_layout.setContentsMargins(10, 5, 10, 5)
        
        # Slider Row
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #333; }
            QSlider::handle:horizontal { background: #00E676; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::sub-page:horizontal { background: #00E676; }
        """)
        ctrl_layout.addWidget(self.slider)

        # Buttons Row
        btn_row = QHBoxLayout()
        
        # Play/Pause
        self.btn_play = QPushButton()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setFixedSize(40, 40)
        self.btn_play.setStyleSheet("border: 1px solid #444; border-radius: 20px; background: #252526;")
        btn_row.addWidget(self.btn_play)
        
        # Time Label
        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setStyleSheet("font-family: monospace; font-size: 12px; color: #AAA; margin-left: 10px;")
        btn_row.addWidget(self.lbl_time)
        
        btn_row.addStretch()
        ctrl_layout.addLayout(btn_row)
        layout.addWidget(self.controls)
        
        # Signals
        self.media_player.positionChanged.connect(self.position_changed)
        self.media_player.durationChanged.connect(self.duration_changed)

    def load_video(self, file_path, start_time_sec=0):
        self.media_player.setSource(QUrl.fromLocalFile(file_path))
        self.media_player.play()
        self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        
        if start_time_sec > 0:
            self.media_player.setPosition(int(start_time_sec * 1000))
            
        self.show()
        self.raise_()

    def toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            self.media_player.play()
            self.btn_play.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))

    def on_slider_pressed(self):
        self.is_dragging_slider = True

    def on_slider_released(self):
        self.is_dragging_slider = False
        # Sync final position
        self.media_player.setPosition(self.slider.value())

    def position_changed(self, position):
        if not self.is_dragging_slider:
            self.slider.setValue(position)
        self.update_time_label(position, self.media_player.duration())

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)

    def set_position(self, position):
        # Called while dragging
        self.update_time_label(position, self.media_player.duration())
        # Optional: live seek (can be laggy)
        # self.media_player.setPosition(position) 

    def update_time_label(self, current_ms, total_ms):
        def fmt(ms):
            seconds = (ms // 1000) % 60
            minutes = (ms // 60000)
            return f"{minutes:02}:{seconds:02}"
        self.lbl_time.setText(f"{fmt(current_ms)} / {fmt(total_ms)}")

    def closeEvent(self, event):
        self.media_player.stop()
        event.accept()