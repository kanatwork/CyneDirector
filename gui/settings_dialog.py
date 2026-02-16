# [FILE: gui/settings_dialog.py]
# Full-height settings dialog with vertical category tabs.

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QStackedWidget, QScrollArea, QComboBox, QLineEdit, QFrame,
    QButtonGroup, QSlider, QSizePolicy, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QIcon

from config import COLORS, APP_NAME
from gui.theme import (
    ACCENT, ACCENT_HOVER, BORDER, SURFACE, SURFACE_INPUT, SURFACE_HOVER,
    BACKGROUND, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DISABLED, TEXT_ON_ACCENT,
    ANIM_FAST, ANIM_NORMAL,
)
from gui.widgets.animated_toggle import AnimatedToggle
from core.logger import get_logger

logger = get_logger(__name__)

# ── Accent color presets ────────────────────────────────────────────
ACCENT_PRESETS = [
    ("#6366f1", "Indigo"),
    ("#22c55e", "Emerald"),
    ("#f43f5e", "Rose"),
    ("#f59e0b", "Amber"),
    ("#06b6d4", "Cyan"),
    ("#8b5cf6", "Violet"),
]

# Category definitions (icon, label)
CATEGORIES = [
    ("General",),
    ("AI / Models",),
    ("Indexing",),
    ("Appearance",),
    ("API Keys",),
]


class SettingsDialog(QDialog):
    """Modal settings dialog with vertical category navigation."""

    def __init__(self, settings_manager, project_path="", parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._project_path = project_path
        self._controls = {}  # key → widget for reading values on save

        self.setWindowTitle(f"Settings — {APP_NAME}")
        self.setFixedSize(750, 550)
        self.setModal(True)

        self._build_ui()
        self._load_values()

    # ── UI construction ─────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──────────────────────────────────────────────
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background: {SURFACE}; border-bottom: 1px solid {BORDER};")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)
        title = QLabel("Settings")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent;")
        h_lay.addWidget(title)
        h_lay.addStretch()
        root.addWidget(header)

        # ── Body (nav + pages) ──────────────────────────────────
        body = QWidget()
        body.setStyleSheet(f"background: {BACKGROUND};")
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        # Left nav
        nav = QWidget()
        nav.setFixedWidth(140)
        nav.setStyleSheet(f"background: {SURFACE}; border-right: 1px solid {BORDER};")
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(0, 8, 0, 8)
        nav_lay.setSpacing(2)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._pages = QStackedWidget()

        for i, (label,) in enumerate(CATEGORIES):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._nav_btn_style())
            btn.setFixedHeight(36)
            self._nav_group.addButton(btn, i)
            nav_lay.addWidget(btn)

        nav_lay.addStretch()
        self._nav_group.idToggled.connect(self._on_nav_changed)
        body_lay.addWidget(nav)

        # Right pages
        self._pages.setStyleSheet(f"background: {BACKGROUND};")
        self._pages.addWidget(self._build_general_page())
        self._pages.addWidget(self._build_ai_page())
        self._pages.addWidget(self._build_indexing_page())
        self._pages.addWidget(self._build_appearance_page())
        self._pages.addWidget(self._build_keys_page())
        body_lay.addWidget(self._pages, 1)

        root.addWidget(body, 1)

        # ── Footer ──────────────────────────────────────────────
        footer = QWidget()
        footer.setFixedHeight(48)
        footer.setStyleSheet(f"background: {SURFACE}; border-top: 1px solid {BORDER};")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(20, 0, 20, 0)
        f_lay.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(self._secondary_btn_style())
        btn_cancel.clicked.connect(self.reject)
        f_lay.addWidget(btn_cancel)

        btn_save = QPushButton("Save Settings")
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet(self._accent_btn_style())
        btn_save.clicked.connect(self._save_and_close)
        f_lay.addWidget(btn_save)

        root.addWidget(footer)

        # Select first category
        first_btn = self._nav_group.button(0)
        if first_btn:
            first_btn.setChecked(True)

    # ── Page builders ───────────────────────────────────────────────

    def _build_general_page(self):
        page = self._make_scroll_page()
        lay = page.widget().layout()

        lay.addWidget(self._section_header("Project"))
        path_label = QLabel(self._project_path or "(no project)")
        path_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        path_label.setWordWrap(True)
        lay.addWidget(self._setting_row("Project Directory", "Current project location", path_label))

        lay.addWidget(self._section_header("Behavior"))
        toggle_auto = AnimatedToggle()
        self._controls["auto_index_on_change"] = toggle_auto
        lay.addWidget(self._setting_row("Auto-index on file change",
                                        "Automatically index new or modified files", toggle_auto))

        combo_lang = QComboBox()
        combo_lang.addItems(["Auto", "English", "Spanish", "French", "German",
                             "Japanese", "Chinese", "Korean"])
        self._controls["language_preference"] = combo_lang
        lay.addWidget(self._setting_row("Language", "Transcription language preference", combo_lang))

        lay.addStretch()
        return page

    def _build_ai_page(self):
        page = self._make_scroll_page()
        lay = page.widget().layout()

        lay.addWidget(self._section_header("Compute"))
        combo_device = QComboBox()
        combo_device.addItems(["Auto", "CUDA", "MPS", "CPU"])
        self._controls["device"] = combo_device
        lay.addWidget(self._setting_row("Device", "Compute device for AI inference", combo_device))

        combo_quality = QComboBox()
        combo_quality.addItems(["Fast", "Balanced", "Quality"])
        self._controls["model_quality"] = combo_quality
        lay.addWidget(self._setting_row("Model Quality (Reserved)",
                                        "Saved for future use. Speed/accuracy is set per-workflow.", combo_quality))

        lay.addWidget(self._section_header("Models"))
        toggle_blip = AnimatedToggle()
        self._controls["blip_variant"] = toggle_blip
        lay.addWidget(self._setting_row("Use BLIP-2",
                                        "BLIP-2 (3 GB VRAM) vs BLIP-Large (1 GB)", toggle_blip))

        combo_whisper = QComboBox()
        combo_whisper.addItems(["base", "small", "medium", "large-v3"])
        self._controls["whisper_model"] = combo_whisper
        lay.addWidget(self._setting_row("Whisper Model",
                                        "Speech transcription model size", combo_whisper))

        lay.addWidget(self._section_header("Model Status"))
        self._model_status_container = QVBoxLayout()
        self._model_status_container.setSpacing(4)
        lay.addLayout(self._model_status_container)
        self._populate_model_status()

        lay.addStretch()
        return page

    def _build_indexing_page(self):
        page = self._make_scroll_page()
        lay = page.widget().layout()

        lay.addWidget(self._section_header("Processing"))
        combo_batch = QComboBox()
        combo_batch.addItems(["Auto", "1", "2", "4", "8", "16"])
        self._controls["batch_size"] = combo_batch
        lay.addWidget(self._setting_row("Batch Size",
                                        "Auto uses dynamic RAM-based sizing", combo_batch))

        lay.addWidget(self._section_header("Output"))
        toggle_proxy = AnimatedToggle()
        self._controls["generate_proxies"] = toggle_proxy
        lay.addWidget(self._setting_row("Generate Proxies",
                                        "Create 720p proxy videos during indexing", toggle_proxy))

        toggle_thumb = AnimatedToggle()
        self._controls["generate_thumbnails"] = toggle_thumb
        lay.addWidget(self._setting_row("Generate Thumbnails",
                                        "Extract thumbnail JPEG during indexing", toggle_thumb))

        lay.addWidget(self._section_header("Keyframes"))
        slider_kf = QSlider(Qt.Orientation.Horizontal)
        slider_kf.setRange(1, 10)
        slider_kf.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider_kf.setTickInterval(1)
        slider_kf.setFixedWidth(180)
        val_label = QLabel("2 s")
        val_label.setFixedWidth(30)
        val_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 600; background: transparent;")
        slider_kf.valueChanged.connect(lambda v: val_label.setText(f"{v} s"))
        slider_row = QWidget()
        slider_row.setStyleSheet("background: transparent;")
        sr_lay = QHBoxLayout(slider_row)
        sr_lay.setContentsMargins(0, 0, 0, 0)
        sr_lay.addWidget(slider_kf)
        sr_lay.addWidget(val_label)
        self._controls["keyframe_interval"] = slider_kf
        lay.addWidget(self._setting_row("Keyframe Interval",
                                        "Seconds between extracted keyframes", slider_row))

        lay.addStretch()
        return page

    def _build_appearance_page(self):
        page = self._make_scroll_page()
        lay = page.widget().layout()

        lay.addWidget(self._section_header("Theme"))
        combo_theme = QComboBox()
        combo_theme.addItems(["Dark"])
        combo_theme.setEnabled(False)
        self._controls["theme"] = combo_theme
        lay.addWidget(self._setting_row("Theme", "Light theme coming soon", combo_theme))

        lay.addWidget(self._section_header("Accent Color"))
        color_row = QWidget()
        color_row.setStyleSheet("background: transparent;")
        cr_lay = QHBoxLayout(color_row)
        cr_lay.setContentsMargins(0, 4, 0, 4)
        cr_lay.setSpacing(8)
        self._color_group = QButtonGroup(self)
        self._color_group.setExclusive(True)
        for hex_color, name in ACCENT_PRESETS:
            btn = self._color_button(hex_color)
            btn.setToolTip(name)
            self._color_group.addButton(btn)
            cr_lay.addWidget(btn)
        cr_lay.addStretch()
        self._controls["accent_color"] = self._color_group
        lay.addWidget(self._setting_row("Accent Color", "Choose your accent color", color_row))

        lay.addWidget(self._section_header("Layout"))
        combo_sidebar = QComboBox()
        combo_sidebar.addItems(["Expanded", "Collapsed"])
        self._controls["sidebar_default"] = combo_sidebar
        lay.addWidget(self._setting_row("Sidebar Default",
                                        "Sidebar state on app launch", combo_sidebar))

        lay.addStretch()
        return page

    def _build_keys_page(self):
        page = self._make_scroll_page()
        lay = page.widget().layout()

        lay.addWidget(self._section_header("Translation"))

        # API key input with show/hide toggle
        key_row = QWidget()
        key_row.setStyleSheet("background: transparent;")
        kr_lay = QHBoxLayout(key_row)
        kr_lay.setContentsMargins(0, 0, 0, 0)
        kr_lay.setSpacing(6)
        key_input = QLineEdit()
        key_input.setEchoMode(QLineEdit.EchoMode.Password)
        key_input.setPlaceholderText("Enter DeepL API key...")
        key_input.setFixedWidth(280)
        kr_lay.addWidget(key_input)

        btn_show = QPushButton("Show")
        btn_show.setFixedWidth(50)
        btn_show.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_show.setStyleSheet(self._secondary_btn_style())

        def _toggle_visibility():
            if key_input.echoMode() == QLineEdit.EchoMode.Password:
                key_input.setEchoMode(QLineEdit.EchoMode.Normal)
                btn_show.setText("Hide")
            else:
                key_input.setEchoMode(QLineEdit.EchoMode.Password)
                btn_show.setText("Show")
        btn_show.clicked.connect(_toggle_visibility)
        kr_lay.addWidget(btn_show)

        self._controls["deepl_api_key"] = key_input
        lay.addWidget(self._setting_row("DeepL API Key",
                                        "For high-quality translation (optional)", key_row))

        lay.addStretch()
        return page

    # ── Model status ────────────────────────────────────────────────

    def _populate_model_status(self):
        try:
            from core.model_manager import get_model_status
            statuses = get_model_status()
        except Exception:
            lbl = QLabel("Could not query model status")
            lbl.setStyleSheet(f"color: {TEXT_DISABLED}; font-size: 12px; background: transparent;")
            self._model_status_container.addWidget(lbl)
            return

        for key, data in statuses.items():
            info = data["info"]
            cached = data["cached"]
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(8, 2, 8, 2)
            name_lbl = QLabel(info["name"])
            name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent;")
            status_lbl = QLabel("Cached" if cached else "Not downloaded")
            color = COLORS["success"] if cached else TEXT_DISABLED
            symbol = "\u2713" if cached else "\u2717"
            status_lbl.setText(f"{symbol}  {status_lbl.text()}")
            status_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600; background: transparent;")
            r_lay.addWidget(name_lbl, 1)
            r_lay.addWidget(status_lbl)
            self._model_status_container.addWidget(row)

    # ── Load / Save ─────────────────────────────────────────────────

    def _load_values(self):
        """Populate controls from settings manager."""
        s = self._sm.to_dict()

        # General
        self._controls["auto_index_on_change"].setChecked(s.get("auto_index_on_change", True))
        self._set_combo(self._controls["language_preference"],
                        s.get("language_preference", "auto"), case_insensitive=True)

        # AI
        self._set_combo(self._controls["device"], s.get("device", "auto"), case_insensitive=True)
        self._set_combo(self._controls["model_quality"], s.get("model_quality", "balanced"),
                        case_insensitive=True)
        self._controls["blip_variant"].setChecked(s.get("blip_variant") == "blip-2")
        self._set_combo(self._controls["whisper_model"], s.get("whisper_model", "large-v3"))

        # Indexing
        self._set_combo(self._controls["batch_size"],
                        str(s.get("batch_size", "auto")), case_insensitive=True)
        self._controls["generate_proxies"].setChecked(s.get("generate_proxies", False))
        self._controls["generate_thumbnails"].setChecked(s.get("generate_thumbnails", True))
        self._controls["keyframe_interval"].setValue(s.get("keyframe_interval", 2))

        # Appearance
        self._set_combo(self._controls["theme"], s.get("theme", "dark"), case_insensitive=True)
        accent = s.get("accent_color", "#6366f1").lower()
        for btn in self._color_group.buttons():
            if btn.property("hex_color") == accent:
                btn.setChecked(True)
                break

        self._set_combo(self._controls["sidebar_default"],
                        s.get("sidebar_default", "expanded"), case_insensitive=True)

        # Keys
        self._controls["deepl_api_key"].setText(s.get("deepl_api_key", ""))

    def _save_and_close(self):
        """Read all controls and persist to settings manager."""
        # General
        self._sm.set("auto_index_on_change", self._controls["auto_index_on_change"].isChecked())
        self._sm.set("language_preference",
                     self._controls["language_preference"].currentText().lower())

        # AI
        self._sm.set("device", self._controls["device"].currentText().lower())
        self._sm.set("model_quality", self._controls["model_quality"].currentText().lower())
        self._sm.set("blip_variant", "blip-2" if self._controls["blip_variant"].isChecked() else "blip-large")
        self._sm.set("whisper_model", self._controls["whisper_model"].currentText())

        # Indexing
        batch_text = self._controls["batch_size"].currentText().lower()
        self._sm.set("batch_size", batch_text if batch_text == "auto" else int(batch_text))
        self._sm.set("generate_proxies", self._controls["generate_proxies"].isChecked())
        self._sm.set("generate_thumbnails", self._controls["generate_thumbnails"].isChecked())
        self._sm.set("keyframe_interval", self._controls["keyframe_interval"].value())

        # Appearance
        self._sm.set("theme", self._controls["theme"].currentText().lower())
        checked_color_btn = self._color_group.checkedButton()
        if checked_color_btn:
            self._sm.set("accent_color", checked_color_btn.property("hex_color"))
        self._sm.set("sidebar_default",
                     self._controls["sidebar_default"].currentText().lower())

        # Keys
        self._sm.set("deepl_api_key", self._controls["deepl_api_key"].text().strip())

        self._sm.save()
        self.accept()

    # ── Widget helpers ──────────────────────────────────────────────

    @staticmethod
    def _setting_row(label_text, description, control_widget):
        """A row with label+description on the left and control on the right."""
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 6, 0, 6)
        lay.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(2)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent;")
        desc = QLabel(description)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        desc.setWordWrap(True)
        left.addWidget(lbl)
        left.addWidget(desc)
        lay.addLayout(left, 1)

        lay.addWidget(control_widget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return row

    @staticmethod
    def _section_header(text):
        """Category subsection header with a thin divider line."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 4)
        lay.setSpacing(4)
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; background: transparent;"
        )
        lay.addWidget(lbl)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BORDER}; background: transparent;")
        line.setFixedHeight(1)
        lay.addWidget(line)
        return w

    @staticmethod
    def _color_button(hex_color, size=28):
        """A round, checkable color swatch button."""
        btn = QPushButton()
        btn.setFixedSize(size, size)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("hex_color", hex_color.lower())
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {hex_color};
                border: 2px solid transparent;
                border-radius: {size // 2}px;
            }}
            QPushButton:hover {{
                border-color: {TEXT_SECONDARY};
            }}
            QPushButton:checked {{
                border-color: {TEXT_PRIMARY};
            }}
        """)
        return btn

    def _make_scroll_page(self):
        """Return a QScrollArea wrapping a QVBoxLayout page widget."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background: {BACKGROUND}; }}")
        inner = QWidget()
        inner.setStyleSheet(f"background: {BACKGROUND};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 12, 24, 12)
        lay.setSpacing(4)
        scroll.setWidget(inner)
        return scroll

    @staticmethod
    def _set_combo(combo, value, case_insensitive=False):
        """Select a combo item matching value."""
        for i in range(combo.count()):
            text = combo.itemText(i)
            if case_insensitive:
                if text.lower() == str(value).lower():
                    combo.setCurrentIndex(i)
                    return
            else:
                if text == str(value):
                    combo.setCurrentIndex(i)
                    return

    # ── Navigation ──────────────────────────────────────────────────

    def _on_nav_changed(self, btn_id, checked):
        if checked:
            self._pages.setCurrentIndex(btn_id)

    # ── Stylesheets ─────────────────────────────────────────────────

    @staticmethod
    def _nav_btn_style():
        return f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                background: {SURFACE_HOVER};
            }}
            QPushButton:checked {{
                color: {ACCENT};
                border-left: 3px solid {ACCENT};
                background: {SURFACE_HOVER};
            }}
        """

    @staticmethod
    def _accent_btn_style():
        return f"""
            QPushButton {{
                background: {ACCENT};
                color: {TEXT_ON_ACCENT};
                border: none;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {ACCENT_HOVER};
            }}
        """

    @staticmethod
    def _secondary_btn_style():
        return f"""
            QPushButton {{
                background: {SURFACE_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {ACCENT};
                background: {SURFACE_HOVER};
            }}
        """
