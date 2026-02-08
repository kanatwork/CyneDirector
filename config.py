# [FILE: config.py]
import os
from pathlib import Path
# Load environment variables from .env file (if python-dotenv is installed)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

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

# --- THEME (Centralized in gui/theme.py) ---
from gui.theme import COLORS, generate_stylesheet
STYLESHEET = generate_stylesheet()

# Database Config
DB_FOLDER_NAME = "_cyne_db"
THUMBNAIL_SIZE = (320, 180)

# AI Model Config
# Set USE_BLIP2=True to use the larger Salesforce/blip2-opt-2.7b (2.7B params, ~3GB VRAM)
# instead of the default Salesforce/blip-image-captioning-large (444M params, ~1GB VRAM).
USE_BLIP2 = False

# Proxy Generation
# Thumbnails are always generated during indexing (fast, single-frame JPEG).
# Set GENERATE_PROXIES=True to also create 720p H.264 proxy videos (slower).
GENERATE_PROXIES = False

# Translation Config
# To use DeepL translation, set DEEPL_API_KEY in a .env file at the project root
# or as a system environment variable. Get a free key at: https://www.deepl.com/pro-api
# If no key is set, Whisper's built-in translation is used as a fallback.
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY", "")

# Translation method preference: "deepl" or "whisper"
# Automatically selects DeepL when a key is available, otherwise falls back to Whisper.
TRANSLATION_METHOD = "deepl" if DEEPL_API_KEY else "whisper"

# --- Per-Project Settings ---
from core.settings_manager import SettingsManager
_settings = SettingsManager()

def load_project_settings(project_path):
    """Load per-project settings from _cyne_db/settings.json."""
    global _settings
    _settings = SettingsManager(project_path)
    return _settings

def get_setting(key, default=None):
    """Get a per-project setting value."""
    return _settings.get(key, default)

def save_settings():
    """Persist current per-project settings to disk."""
    _settings.save()