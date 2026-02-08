# [FILE: gui/model_download_dialog.py]
# Pre-download dialog for AI models — shows cache status and download progress.

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from config import COLORS
from core.model_manager import (
    MODEL_REGISTRY, get_model_status, get_missing_required_models,
    ModelDownloadWorker,
)
from core.logger import get_logger

logger = get_logger(__name__)


class ModelDownloadDialog(QDialog):
    """Dialog that shows AI model cache status and allows pre-downloading."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Model Setup")
        self.setFixedSize(560, 520)
        self.worker = None
        self.model_rows = {}  # key -> {"status": QLabel, "progress": QProgressBar}

        self._apply_stylesheet()
        self._build_ui()

    # ── Styling ──────────────────────────────────────────────────────

    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['bg_app']};
                color: {COLORS['text_main']};
            }}
            QLabel {{
                background: transparent;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)

    # ── Layout ───────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(6)

        # Title
        title = QLabel("AI Model Setup")
        title.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 20px; font-weight: 800; "
            f"letter-spacing: 0.5px;"
        )
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Models are downloaded once and cached locally.")
        subtitle.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 12px;")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Scrollable model list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)

        status = get_model_status()

        # Required models section
        self._add_section_header("Required")
        for key in ("clip", "blip", "whisper", "yolo"):
            if key in status:
                self._add_model_row(key, status[key])

        # Optional models section
        self._add_section_header("Optional")
        for key in ("blip2", "llm"):
            if key in status:
                self._add_model_row(key, status[key])

        self.scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, stretch=1)

        # Summary
        self._build_summary(layout)

        # Buttons
        self._build_buttons(layout)

    def _add_section_header(self, text: str):
        header = QLabel(text.upper())
        header.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1px; padding: 10px 0 4px 0;"
        )
        self.scroll_layout.addWidget(header)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        line.setFixedHeight(1)
        self.scroll_layout.addWidget(line)

    def _add_model_row(self, key: str, data: dict):
        info = data["info"]
        cached = data["cached"]

        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 8, 4, 8)
        row_layout.setSpacing(10)

        # Status icon
        status_lbl = QLabel()
        if cached:
            status_lbl.setText("\u2713")  # checkmark
            status_lbl.setStyleSheet(
                f"color: {COLORS['success']}; font-size: 16px; font-weight: 700; "
                f"min-width: 20px; max-width: 20px;"
            )
        else:
            status_lbl.setText("\u25cb")  # open circle
            status_lbl.setStyleSheet(
                f"color: {COLORS['text_disabled']}; font-size: 16px; "
                f"min-width: 20px; max-width: 20px;"
            )
        row_layout.addWidget(status_lbl, 0, Qt.AlignmentFlag.AlignTop)

        # Info column
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        # Name + size
        name_row = QHBoxLayout()
        name_lbl = QLabel(info["name"])
        name_lbl.setStyleSheet(
            f"color: {COLORS['text_main']}; font-size: 13px; font-weight: 700;"
        )
        name_row.addWidget(name_lbl)
        name_row.addStretch()

        size = info["size_mb"]
        size_text = f"~{size / 1000:.1f} GB" if size >= 1000 else f"~{size} MB"
        size_lbl = QLabel(size_text)
        size_lbl.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 11px;")
        name_row.addWidget(size_lbl)
        info_col.addLayout(name_row)

        # Description
        desc_lbl = QLabel(info["description"])
        desc_lbl.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        info_col.addWidget(desc_lbl)

        # Progress bar (hidden by default)
        progress = QProgressBar()
        progress.setFixedHeight(6)
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: {COLORS['bg_input']};
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {COLORS['accent']};
                border-radius: 3px;
            }}
        """)
        progress.hide()
        info_col.addWidget(progress)

        row_layout.addLayout(info_col, stretch=1)
        self.scroll_layout.addWidget(row)

        self.model_rows[key] = {
            "status": status_lbl,
            "progress": progress,
            "name": info["name"],
        }

    def _build_summary(self, parent_layout):
        parent_layout.addSpacing(4)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px;")
        line.setFixedHeight(1)
        parent_layout.addWidget(line)

        missing = get_missing_required_models()
        total_mb = sum(MODEL_REGISTRY[k]["size_mb"] for k in missing)
        if total_mb >= 1000:
            size_text = f"~{total_mb / 1000:.1f} GB"
        else:
            size_text = f"~{total_mb} MB"

        if missing:
            text = f"{len(missing)} required model{'s' if len(missing) != 1 else ''} missing ({size_text})"
        else:
            text = "All required models are cached."

        self.summary_label = QLabel(text)
        self.summary_label.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 12px; padding: 8px 0;"
        )
        parent_layout.addWidget(self.summary_label)

    def _build_buttons(self, parent_layout):
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        # Skip / Cancel
        self.btn_skip = QPushButton("Skip for Now")
        self.btn_skip.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_skip.setFixedHeight(38)
        self.btn_skip.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_panel']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_main']};
                border-radius: 6px;
                padding: 0 20px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {COLORS['accent']};
                color: {COLORS['accent']};
            }}
        """)
        self.btn_skip.clicked.connect(self._on_skip)
        btn_layout.addWidget(self.btn_skip)

        # Download All
        self.btn_download = QPushButton("Download All")
        self.btn_download.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_download.setFixedHeight(38)
        self.btn_download.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['accent']};
                color: {COLORS['text_on_accent']};
                border: none;
                border-radius: 6px;
                padding: 0 24px;
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_hover']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['bg_input']};
                color: {COLORS['text_disabled']};
            }}
        """)
        self.btn_download.clicked.connect(self._on_download)
        btn_layout.addWidget(self.btn_download)

        # Disable download if nothing to download
        if not get_missing_required_models():
            self.btn_download.setEnabled(False)
            self.btn_download.setText("All Cached")

        parent_layout.addLayout(btn_layout)

    # ── Actions ──────────────────────────────────────────────────────

    def _on_skip(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.accept()

    def _on_download(self):
        missing = get_missing_required_models()
        if not missing:
            self.accept()
            return

        # Disable buttons during download
        self.btn_download.setEnabled(False)
        self.btn_download.setText("Downloading...")
        self.btn_skip.setText("Cancel")

        # Mark all missing as "pending download"
        for key in missing:
            row = self.model_rows.get(key)
            if row:
                row["progress"].show()
                row["progress"].setValue(0)

        self.worker = ModelDownloadWorker(missing)
        self.worker.download_progress.connect(self._on_progress)
        self.worker.download_complete.connect(self._on_model_done)
        self.worker.download_error.connect(self._on_model_error)
        self.worker.all_complete.connect(self._on_all_done)
        self.worker.status_message.connect(self._on_status)
        self.worker.start()

    # ── Slots ────────────────────────────────────────────────────────

    def _on_progress(self, key: str, percent: int):
        row = self.model_rows.get(key)
        if not row:
            return
        row["progress"].setValue(percent)
        if percent > 0:
            # Show downloading icon
            row["status"].setText("\u2193")  # down arrow
            row["status"].setStyleSheet(
                f"color: {COLORS['accent']}; font-size: 16px; font-weight: 700; "
                f"min-width: 20px; max-width: 20px;"
            )

    def _on_model_done(self, key: str):
        row = self.model_rows.get(key)
        if not row:
            return
        row["progress"].setValue(100)
        row["progress"].hide()
        row["status"].setText("\u2713")
        row["status"].setStyleSheet(
            f"color: {COLORS['success']}; font-size: 16px; font-weight: 700; "
            f"min-width: 20px; max-width: 20px;"
        )

    def _on_model_error(self, key: str, error: str):
        row = self.model_rows.get(key)
        if not row:
            return
        row["progress"].hide()
        row["status"].setText("\u2717")  # X mark
        row["status"].setStyleSheet(
            f"color: {COLORS['error']}; font-size: 16px; font-weight: 700; "
            f"min-width: 20px; max-width: 20px;"
        )
        logger.error(f"Model download failed for {key}: {error}")

    def _on_all_done(self):
        self.btn_download.setText("Download All")
        self.btn_skip.setText("Skip for Now")

        # Update summary
        missing = get_missing_required_models()
        if not missing:
            self.summary_label.setText("All required models are cached.")
            self.btn_download.setText("All Cached")
            # Auto-close after a short moment
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(800, self.accept)
        else:
            total_mb = sum(MODEL_REGISTRY[k]["size_mb"] for k in missing)
            size_text = f"~{total_mb / 1000:.1f} GB" if total_mb >= 1000 else f"~{total_mb} MB"
            self.summary_label.setText(
                f"{len(missing)} required model{'s' if len(missing) != 1 else ''} "
                f"still missing ({size_text})"
            )
            self.btn_download.setEnabled(True)

    def _on_status(self, msg: str):
        logger.info(f"[ModelDownload] {msg}")

    # ── Cleanup ──────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        super().closeEvent(event)
