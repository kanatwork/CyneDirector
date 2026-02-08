# [FILE: core/settings_manager.py]
# Per-project settings persistence — load/save JSON, defaults merging.

import json
import logging
import os

logger = logging.getLogger(__name__)

DEFAULTS = {
    # General
    "auto_index_on_change": True,
    "language_preference": "auto",

    # AI / Models
    "device": "auto",               # auto / cuda / mps / cpu
    "model_quality": "balanced",     # fast / balanced / quality
    "blip_variant": "blip-large",    # blip-large / blip-2
    "whisper_model": "large-v3",     # base / small / medium / large-v3

    # Indexing
    "batch_size": "auto",            # "auto" or int
    "generate_proxies": False,
    "generate_thumbnails": True,
    "keyframe_interval": 2,          # seconds

    # Appearance
    "theme": "dark",                 # dark (light is future)
    "accent_color": "#6366f1",       # indigo default
    "sidebar_default": "expanded",   # expanded / collapsed

    # API Keys
    "deepl_api_key": "",
}


class SettingsManager:
    """Manages per-project settings stored as JSON in _cyne_db/settings.json."""

    def __init__(self, project_path=None):
        self._data = dict(DEFAULTS)
        self._path = None
        if project_path:
            self.load(project_path)

    def load(self, project_path):
        """Load settings from project, merging with defaults for any new keys."""
        db_dir = os.path.join(project_path, "_cyne_db")
        os.makedirs(db_dir, exist_ok=True)
        self._path = os.path.join(db_dir, "settings.json")

        if os.path.isfile(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                # Merge: defaults first, then stored values override
                self._data = {**DEFAULTS, **stored}
                logger.debug(f"Settings loaded from {self._path}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read settings, using defaults: {e}")
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
            logger.debug("No settings file found, using defaults")

    def save(self):
        """Persist current settings to disk."""
        if not self._path:
            logger.warning("Cannot save settings — no project loaded")
            return
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            logger.debug(f"Settings saved to {self._path}")
        except OSError as e:
            logger.error(f"Failed to save settings: {e}")

    def get(self, key, default=None):
        """Get a setting value, falling back to DEFAULTS then to default."""
        return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key, value):
        """Set a setting value in memory (call save() to persist)."""
        self._data[key] = value

    def to_dict(self):
        """Return a copy of all current settings."""
        return dict(self._data)
