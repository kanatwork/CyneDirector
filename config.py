# [FILE: config.py]
import os
from pathlib import Path

# --- Application Info ---
APP_NAME = "CyneDirector"
VERSION = "2.1.0"
FILE_EXT = ".cyne"  # Updated to match project name

# --- Paths ---
# Use .resolve() to get absolute path, safer for some OS environments
ROOT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ROOT_DIR / "assets"
LOG_DIR = ROOT_DIR / "logs"

# Ensure directories exist immediately
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# --- THEME PALETTE (Cinema Dark - Wisteria Edition) ---
COLORS = {
    "bg_app": "#121212",        # Deepest background
    "bg_panel": "#1E1F22",      # Sidebar / Panels
    "bg_input": "#2B2D31",      # Input fields
    "border": "#3F4148",        # Subtle borders
    
    "accent": "#BEAEDB",        # Wisteria (Primary Action)
    "accent_hover": "#A898C8",  # Hover State
    
    "text_main": "#E0E0E0",     # Primary Text
    "text_dim": "#949BA4",      # Secondary/Hint Text
    "selection": "#3A3445",     # List Selection Background
    
    # --- CRITICAL MISSING KEYS ADDED BELOW ---
    "success": "#4CAF50",       # Green (Completed)
    "warning": "#FF9800",       # Orange (Processing/Warning)
    "error": "#F44336"          # Red (Failed)
}

STYLESHEET = f"""
    /* GLOBAL RESET */
    QWidget {{ 
        background-color: {COLORS['bg_app']}; 
        color: {COLORS['text_main']}; 
        font-family: 'Segoe UI', 'Roboto', sans-serif;
        font-size: 13px;
    }}

    /* SIDEBAR */
    QWidget#Sidebar {{ 
        background-color: {COLORS['bg_panel']}; 
        border-right: 1px solid {COLORS['border']}; 
    }}
    
    /* MODERN BUTTONS */
    QPushButton {{ 
        background-color: {COLORS['bg_input']}; 
        border: 1px solid {COLORS['border']}; 
        color: {COLORS['text_main']};
        border-radius: 6px; 
        padding: 8px 16px; 
        font-weight: 600;
    }}
    QPushButton:hover {{ 
        background-color: #35373C; 
        border-color: {COLORS['text_dim']}; 
    }}
    QPushButton:pressed {{ background-color: {COLORS['bg_app']}; }}

    /* ACCENT BUTTONS (Class-based styling) */
    QPushButton[class="accent"] {{ 
        background-color: {COLORS['accent']}; 
        color: #121212; 
        border: none;
    }}
    QPushButton[class="accent"]:hover {{ background-color: {COLORS['accent_hover']}; }}

    /* INPUTS */
    QLineEdit, QTextBrowser, QTextEdit {{ 
        background-color: {COLORS['bg_input']}; 
        border: 1px solid {COLORS['border']}; 
        border-radius: 4px; 
        padding: 8px; 
        color: white; 
        selection-background-color: {COLORS['accent']};
        selection-color: black;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border: 1px solid {COLORS['accent']}; }}

    /* TREE / LIST VIEWS */
    QTreeWidget, QListWidget {{ 
        background-color: {COLORS['bg_app']}; 
        border: 1px solid {COLORS['border']}; 
        border-radius: 6px;
        outline: none;
    }}
    QHeaderView::section {{ 
        background-color: {COLORS['bg_panel']}; 
        padding: 6px; 
        border: none; 
        border-bottom: 1px solid {COLORS['border']}; 
        font-weight: bold; 
        color: {COLORS['text_dim']};
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 6px; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{ 
        background-color: {COLORS['selection']}; 
        color: {COLORS['accent']};
        border-left: 2px solid {COLORS['accent']};
    }}

    /* SCROLLBARS (Subtle) */
    QScrollBar:vertical {{
        background: {COLORS['bg_app']};
        width: 10px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {COLORS['border']};
        min-height: 20px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {COLORS['text_dim']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    
    QScrollBar:horizontal {{
        background: {COLORS['bg_app']};
        height: 10px;
        margin: 0px;
        border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {COLORS['border']};
        min-width: 20px;
        border-radius: 5px;
    }}
    
    /* TOOLTIPS */
    QToolTip {{ 
        color: #fff; background-color: #333; border: 1px solid {COLORS['border']}; padding: 5px; 
    }}
    
    /* MENUS */
    QMenu {{ background-color: {COLORS['bg_panel']}; border: 1px solid {COLORS['border']}; }}
    QMenu::item {{ padding: 5px 20px; }}
    QMenu::item:selected {{ background-color: {COLORS['accent']}; color: black; }}
"""

# Database Config
DB_FOLDER_NAME = "_cyne_db"
THUMBNAIL_SIZE = (320, 180)