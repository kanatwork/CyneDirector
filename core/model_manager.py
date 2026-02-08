# [FILE: core/model_manager.py]
# Model registry, cache detection, and download worker for AI models.
# Lightweight — avoids importing torch/transformers/ultralytics at module level.

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from core.logger import get_logger

logger = get_logger(__name__)

# ─── Model Registry ─────────────────────────────────────────────────
MODEL_REGISTRY = {
    "clip": {
        "name": "CLIP ViT-L/14",
        "description": "Visual search and tag matching",
        "hf_id": "openai/clip-vit-large-patch14",
        "size_mb": 600,
        "required": True,
    },
    "blip": {
        "name": "BLIP-large",
        "description": "Scene captioning",
        "hf_id": "Salesforce/blip-image-captioning-large",
        "size_mb": 990,
        "required": True,
    },
    "whisper": {
        "name": "Faster Whisper large-v3",
        "description": "Speech transcription",
        "hf_id": "Systran/faster-whisper-large-v3",
        "size_mb": 1500,
        "required": True,
    },
    "yolo": {
        "name": "YOLOv8m",
        "description": "Object detection",
        "yolo_model": "yolov8m.pt",
        "size_mb": 50,
        "required": True,
    },
    "blip2": {
        "name": "BLIP-2 OPT-2.7B",
        "description": "Higher-quality scene captioning",
        "hf_id": "Salesforce/blip2-opt-2.7b",
        "size_mb": 3000,
        "required": False,
    },
    "llm": {
        "name": "Llama-3.2 3B (4-bit)",
        "description": "Video summarization",
        "hf_id": "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
        "size_mb": 2000,
        "required": False,
    },
}


# ─── Cache Detection ────────────────────────────────────────────────

def _get_hf_cache_dir() -> Path:
    """Resolve the HuggingFace Hub cache directory."""
    # 1. Explicit override
    env = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if env:
        return Path(env)
    # 2. HF_HOME/hub
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    # 3. Default
    return Path.home() / ".cache" / "huggingface" / "hub"


def _is_hf_cached(repo_id: str) -> bool:
    """Check if a HuggingFace model has been downloaded (fast stat check)."""
    cache_dir = _get_hf_cache_dir()
    # HF stores repos as models--org--name
    folder_name = "models--" + repo_id.replace("/", "--")
    snapshots_dir = cache_dir / folder_name / "snapshots"
    if not snapshots_dir.is_dir():
        return False
    # Must have at least one snapshot child
    try:
        return any(snapshots_dir.iterdir())
    except OSError:
        return False


def _is_yolo_cached(model_name: str) -> bool:
    """Check if a YOLO model weight file exists in common locations."""
    # 1. Current working directory
    if Path(model_name).exists():
        return True
    # 2. Try ultralytics settings if importable (lightweight check)
    try:
        from ultralytics.utils import SETTINGS
        weights_dir = Path(SETTINGS.get("weights_dir", ""))
        if (weights_dir / model_name).exists():
            return True
    except Exception:
        pass
    # 3. Windows: %APPDATA%\Ultralytics
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            p = Path(appdata) / "Ultralytics" / model_name
            if p.exists():
                return True
    # 4. ~/.config/Ultralytics (Linux/macOS)
    config_path = Path.home() / ".config" / "Ultralytics" / model_name
    if config_path.exists():
        return True
    return False


def is_model_cached(key: str) -> bool:
    """Check if a specific model is already downloaded."""
    info = MODEL_REGISTRY.get(key)
    if not info:
        return False
    if "yolo_model" in info:
        return _is_yolo_cached(info["yolo_model"])
    return _is_hf_cached(info["hf_id"])


def get_model_status() -> dict:
    """Return {key: {"cached": bool, "info": dict}} for all registered models."""
    return {
        key: {"cached": is_model_cached(key), "info": info}
        for key, info in MODEL_REGISTRY.items()
    }


def get_missing_required_models() -> list:
    """Return list of required model keys that are NOT cached."""
    return [
        key for key, info in MODEL_REGISTRY.items()
        if info["required"] and not is_model_cached(key)
    ]


# ─── Download Worker ────────────────────────────────────────────────

class ModelDownloadWorker(QThread):
    """Downloads AI models in a background thread."""

    download_progress = pyqtSignal(str, int)    # (model_key, percent 0-100)
    download_complete = pyqtSignal(str)          # model_key
    download_error = pyqtSignal(str, str)        # (model_key, error_message)
    all_complete = pyqtSignal()                  # all downloads done
    status_message = pyqtSignal(str)             # log text

    def __init__(self, model_keys: list):
        super().__init__()
        self.model_keys = model_keys
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        for key in self.model_keys:
            if not self.is_running:
                break

            info = MODEL_REGISTRY.get(key)
            if not info:
                continue

            self.status_message.emit(f"Downloading {info['name']}...")
            self.download_progress.emit(key, 0)

            try:
                if "yolo_model" in info:
                    self._download_yolo(key, info)
                else:
                    self._download_hf(key, info)

                # Verify it actually cached
                if is_model_cached(key):
                    self.download_progress.emit(key, 100)
                    self.download_complete.emit(key)
                    self.status_message.emit(f"{info['name']} ready.")
                else:
                    self.download_error.emit(key, "Download finished but model not found in cache")
            except Exception as e:
                logger.error(f"Failed to download {key}: {e}")
                self.download_error.emit(key, str(e))

        self.all_complete.emit()

    def _download_hf(self, key: str, info: dict):
        """Download a HuggingFace model using snapshot_download (resumable)."""
        self.download_progress.emit(key, 5)
        from huggingface_hub import snapshot_download
        self.download_progress.emit(key, 10)
        snapshot_download(info["hf_id"])
        self.download_progress.emit(key, 95)

    def _download_yolo(self, key: str, info: dict):
        """Download a YOLO model (auto-downloads on first instantiation)."""
        self.download_progress.emit(key, 10)
        from ultralytics import YOLO
        YOLO(info["yolo_model"])
        self.download_progress.emit(key, 95)
