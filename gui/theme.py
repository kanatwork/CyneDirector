# [FILE: gui/theme.py]
# Centralized design system for CyneDirector
# All colors, fonts, spacing, and stylesheet generation live here.

# ─── Color Palette ───────────────────────────────────────────────
BACKGROUND      = "#0f0f0f"
SURFACE         = "#1a1a1a"
SURFACE_HOVER   = "#242424"
SURFACE_INPUT   = "#2b2d31"
BORDER          = "#2a2a2a"

TEXT_PRIMARY     = "#e8e8e8"
TEXT_SECONDARY   = "#888888"
TEXT_DISABLED    = "#555555"
TEXT_ON_ACCENT   = "#0f0f0f"

ACCENT           = "#6366f1"
ACCENT_HOVER     = "#818cf8"
SELECTION        = "#2d2b3d"

SUCCESS          = "#22c55e"
SUCCESS_HOVER    = "#16a34a"
WARNING          = "#f59e0b"
WARNING_HOVER    = "#d97706"
ERROR            = "#ef4444"
ERROR_HOVER      = "#dc2626"

SHADOW           = "rgba(0, 0, 0, 0.3)"
GLOW             = "rgba(99, 102, 241, 0.2)"

# ─── Animation Durations (ms) ──────────────────────────────────────
ANIM_FAST   = 150
ANIM_NORMAL = 250
ANIM_SLOW   = 350

# ─── Sidebar Dimensions ────────────────────────────────────────────
SIDEBAR_EXPANDED  = 180   # full width with text labels
SIDEBAR_COLLAPSED = 56    # icon-only width

# ─── Backward-Compatible COLORS Dict ────────────────────────────
# Every GUI file does `from config import COLORS` and accesses keys
# like COLORS['bg_app'], COLORS['accent'], etc.  This dict maps
# those legacy keys to the new palette so nothing breaks.
COLORS = {
    # backgrounds
    "bg_app":       BACKGROUND,
    "bg_panel":     SURFACE,
    "bg_input":     SURFACE_INPUT,
    "bg_workflow":  SURFACE,
    "bg_log":       BACKGROUND,

    # borders / structure
    "border":       BORDER,

    # accent
    "accent":       ACCENT,
    "accent_hover": ACCENT_HOVER,

    # text
    "text_main":    TEXT_PRIMARY,
    "text_dim":     TEXT_SECONDARY,
    "text_disabled": TEXT_DISABLED,
    "text_on_accent": TEXT_ON_ACCENT,

    # selection
    "selection":    SELECTION,

    # semantic
    "success":       SUCCESS,
    "success_hover": SUCCESS_HOVER,
    "warning":       WARNING,
    "warning_hover": WARNING_HOVER,
    "error":         ERROR,
    "error_hover":   ERROR_HOVER,

    # shadows / glow
    "shadow":       SHADOW,
    "glow":         GLOW,

    # spacing (string values for QSS interpolation)
    "spacing_xs":  "4px",
    "spacing_sm":  "8px",
    "spacing_md":  "12px",
    "spacing_lg":  "16px",
    "spacing_xl":  "20px",
    "spacing_xxl": "24px",

    # border radius
    "radius_sm":  "4px",
    "radius_md":  "6px",
    "radius_lg":  "8px",

    # shadows
    "shadow_sm": "0 1px 3px rgba(0, 0, 0, 0.2)",
    "shadow_md": "0 2px 8px rgba(0, 0, 0, 0.3)",
    "shadow_lg": "0 4px 12px rgba(0, 0, 0, 0.4)",

    # surface variants (new convenience keys used in main_window)
    "surface_hover": SURFACE_HOVER,
    "surface_alt":   "#222222",
    "overlay":       "rgba(0, 0, 0, 0.5)",
}

# ─── Font Definitions ────────────────────────────────────────────
FONT_FAMILY  = "'Inter', 'Segoe UI', '-apple-system', sans-serif"
FONT_SIZE_XS = 10   # px
FONT_SIZE_SM = 12
FONT_SIZE_BASE = 13
FONT_SIZE_LG = 15
FONT_SIZE_XL = 18

# ─── Spacing (4px grid) ─────────────────────────────────────────
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32

# ─── Border Radius ───────────────────────────────────────────────
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 12


def generate_stylesheet() -> str:
    """Return a comprehensive QSS string for the entire application."""
    return f"""
    /* ── GLOBAL RESET ─────────────────────────────────────────── */
    QWidget {{
        background-color: {BACKGROUND};
        color: {TEXT_PRIMARY};
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE_BASE}px;
    }}

    /* ── SIDEBAR ──────────────────────────────────────────────── */
    QWidget#Sidebar {{
        background-color: {SURFACE};
        border-right: 1px solid {BORDER};
    }}

    /* ── BUTTONS ──────────────────────────────────────────────── */
    QPushButton {{
        background-color: {SURFACE_INPUT};
        border: 1px solid {BORDER};
        color: {TEXT_PRIMARY};
        border-radius: {RADIUS_SM}px;
        padding: {SPACE_SM}px {SPACE_MD}px;
        font-weight: 600;
        font-size: {FONT_SIZE_SM}px;
    }}
    QPushButton:hover {{
        background-color: {SURFACE_HOVER};
        border-color: {ACCENT};
    }}
    QPushButton:pressed {{
        background-color: {BACKGROUND};
    }}
    QPushButton:disabled {{
        background-color: {SURFACE_INPUT};
        color: {TEXT_DISABLED};
        border-color: {BORDER};
    }}

    /* Accent buttons */
    QPushButton[class="accent"] {{
        background-color: {ACCENT};
        color: {TEXT_ON_ACCENT};
        border: none;
        border-radius: {RADIUS_SM}px;
        padding: {SPACE_SM}px {SPACE_MD}px;
        font-weight: 700;
    }}
    QPushButton[class="accent"]:hover {{
        background-color: {ACCENT_HOVER};
    }}
    QPushButton[class="accent"]:pressed {{
        background-color: {ACCENT};
    }}

    /* ── CHECKBOXES & RADIO BUTTONS ───────────────────────────── */
    QCheckBox {{
        color: {TEXT_PRIMARY};
        font-size: {FONT_SIZE_SM}px;
        font-weight: 600;
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {BORDER};
        border-radius: 4px;
        background: {SURFACE_INPUT};
    }}
    QCheckBox::indicator:hover {{
        border-color: {ACCENT};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    QRadioButton {{
        color: {TEXT_PRIMARY};
        font-size: 11px;
        font-weight: 600;
        spacing: 6px;
    }}
    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {BORDER};
        border-radius: 9px;
        background: {SURFACE_INPUT};
    }}
    QRadioButton::indicator:hover {{
        border-color: {ACCENT};
    }}
    QRadioButton::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    /* ── INPUTS ───────────────────────────────────────────────── */
    QLineEdit, QTextBrowser, QTextEdit {{
        background-color: {SURFACE_INPUT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: {SPACE_SM}px;
        color: {TEXT_PRIMARY};
        selection-background-color: {ACCENT};
        selection-color: {TEXT_ON_ACCENT};
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border: 1px solid {ACCENT};
    }}

    /* ── TREE / LIST VIEWS ────────────────────────────────────── */
    QTreeWidget, QListWidget {{
        background-color: {BACKGROUND};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_MD}px;
        outline: none;
    }}
    QHeaderView::section {{
        background-color: {SURFACE};
        padding: 6px;
        border: none;
        border-bottom: 1px solid {BORDER};
        font-weight: bold;
        color: {TEXT_SECONDARY};
    }}
    QTreeWidget::item, QListWidget::item {{
        padding: 6px;
    }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background-color: {SELECTION};
        color: {ACCENT};
        border-left: 2px solid {ACCENT};
    }}

    /* ── SCROLLBARS ───────────────────────────────────────────── */
    QScrollBar:vertical {{
        background: {BACKGROUND};
        width: 8px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        min-height: 20px;
        border-radius: 4px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {TEXT_SECONDARY};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QScrollBar:horizontal {{
        background: {BACKGROUND};
        height: 8px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER};
        min-width: 20px;
        border-radius: 4px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {TEXT_SECONDARY};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
    }}

    /* ── PROGRESS BAR ─────────────────────────────────────────── */
    QProgressBar {{
        border: 1px solid {BORDER};
        background: {SURFACE_INPUT};
        border-radius: 4px;
        text-align: center;
        color: {TEXT_PRIMARY};
        font-size: 10px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT}, stop:1 {ACCENT_HOVER});
        border-radius: 3px;
    }}

    /* ── MENUS ────────────────────────────────────────────────── */
    QMenuBar {{
        background-color: {SURFACE};
        color: {TEXT_PRIMARY};
        border-bottom: 1px solid {BORDER};
    }}
    QMenuBar::item {{
        padding: 5px 10px;
    }}
    QMenuBar::item:selected {{
        background-color: {SURFACE_HOVER};
    }}
    QMenu {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {ACCENT};
        color: {TEXT_ON_ACCENT};
    }}
    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 4px 8px;
    }}

    /* ── TOOLTIPS ──────────────────────────────────────────────── */
    QToolTip {{
        color: {TEXT_PRIMARY};
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        padding: 5px;
        border-radius: 4px;
    }}

    /* ── COMBOBOX ──────────────────────────────────────────────── */
    QComboBox {{
        background-color: {SURFACE_INPUT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 4px 8px;
        color: {TEXT_PRIMARY};
    }}
    QComboBox:hover {{
        border-color: {ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {SURFACE};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT};
        selection-color: {TEXT_ON_ACCENT};
        outline: none;
    }}

    /* ── SPLITTER ──────────────────────────────────────────────── */
    QSplitter::handle {{
        background: {BORDER};
    }}
    QSplitter::handle:hover {{
        background: {TEXT_SECONDARY};
    }}

    /* ── TAB WIDGET ───────────────────────────────────────────── */
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        background: {BACKGROUND};
    }}
    QTabBar::tab {{
        background: {SURFACE};
        color: {TEXT_SECONDARY};
        padding: 8px 16px;
        border: 1px solid {BORDER};
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {BACKGROUND};
        color: {TEXT_PRIMARY};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover {{
        color: {TEXT_PRIMARY};
    }}
    """
