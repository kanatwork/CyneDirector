# [FILE: core/proxy_generator.py]
# FFmpeg-based proxy video generation and thumbnail extraction.
# All functions are non-fatal — return None and log warnings if FFmpeg is missing.

import os
import sys
import subprocess
import re
from pathlib import Path
from core.logger import get_logger

logger = get_logger(__name__)

# Windows: hide the console window that subprocess would otherwise flash
_CREATION_FLAGS = 0x08000000 if sys.platform == "win32" else 0


def check_ffmpeg_available() -> bool:
    """Return True if the ``ffmpeg`` binary is reachable on PATH."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATION_FLAGS,
        )
        return True
    except FileNotFoundError:
        return False


def _get_duration(video_path: str) -> float:
    """Return video duration in seconds via ffprobe, or 0.0 on failure."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "default=noprint_wrappers=1:nokey=1",
        "-show_entries", "format=duration",
        video_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", creationflags=_CREATION_FLAGS,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        logger.debug(f"ffprobe duration query failed: {e}")
    return 0.0


def _safe_stem(video_path: str) -> str:
    """Return a filesystem-safe stem derived from the video filename."""
    stem = Path(video_path).stem
    # Replace anything that isn't alphanumeric, hyphen, underscore, or dot
    return re.sub(r'[^\w\-.]', '_', stem)


# ─── Public API ──────────────────────────────────────────────────────

def generate_thumbnail(video_path: str, output_dir: str, timestamp: float | None = None) -> str | None:
    """Extract a single JPEG thumbnail (320x180) from *video_path*.

    Parameters
    ----------
    video_path : str
        Absolute path to the source video.
    output_dir : str
        Directory where the thumbnail will be written (created if needed).
    timestamp : float or None
        Seek position in seconds.  Defaults to 10 % of the video duration.

    Returns
    -------
    str or None
        Absolute path to the generated thumbnail, or ``None`` on failure.
    """
    if not check_ffmpeg_available():
        logger.warning("FFmpeg not found — skipping thumbnail generation")
        return None

    if not os.path.isfile(video_path):
        logger.warning(f"Video file not found: {video_path}")
        return None

    os.makedirs(output_dir, exist_ok=True)

    # Resolve seek timestamp
    if timestamp is None:
        duration = _get_duration(video_path)
        timestamp = duration * 0.10 if duration > 0 else 0.0

    out_path = os.path.join(output_dir, f"{_safe_stem(video_path)}_thumb.jpg")

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
        out_path,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", creationflags=_CREATION_FLAGS,
        )
        if result.returncode == 0 and os.path.isfile(out_path):
            logger.debug(f"Thumbnail created: {out_path}")
            return out_path
        else:
            logger.warning(f"FFmpeg thumbnail failed (rc={result.returncode}): {result.stderr[:300]}")
    except Exception as e:
        logger.error(f"Thumbnail generation error: {e}")
    return None


def generate_proxy(video_path: str, output_dir: str, resolution: int = 720) -> str | None:
    """Create an H.264 proxy video at the given vertical resolution.

    Parameters
    ----------
    video_path : str
        Absolute path to the source video.
    output_dir : str
        Directory where the proxy will be written (created if needed).
    resolution : int
        Target height in pixels (default 720).  Width is scaled automatically
        with ``scale=-2:{resolution}`` to keep even dimensions.

    Returns
    -------
    str or None
        Absolute path to the generated proxy file, or ``None`` on failure.
    """
    if not check_ffmpeg_available():
        logger.warning("FFmpeg not found — skipping proxy generation")
        return None

    if not os.path.isfile(video_path):
        logger.warning(f"Video file not found: {video_path}")
        return None

    os.makedirs(output_dir, exist_ok=True)

    out_path = os.path.join(output_dir, f"{_safe_stem(video_path)}_proxy.mp4")

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"scale=-2:{resolution}",
        "-c:v", "libx264",
        "-crf", "28",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        out_path,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", creationflags=_CREATION_FLAGS,
            timeout=3600,  # 1-hour safety timeout
        )
        if result.returncode == 0 and os.path.isfile(out_path):
            logger.info(f"Proxy created: {out_path}")
            return out_path
        else:
            logger.warning(f"FFmpeg proxy failed (rc={result.returncode}): {result.stderr[:300]}")
    except subprocess.TimeoutExpired:
        logger.error(f"Proxy generation timed out for: {video_path}")
    except Exception as e:
        logger.error(f"Proxy generation error: {e}")
    return None
