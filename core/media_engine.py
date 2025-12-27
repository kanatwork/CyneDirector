import subprocess
import json
import os
import sys

class MediaEngine:
    """
    Robust wrapper for FFprobe to extract metadata from professional video formats.
    Replaces unreliable OpenCV metadata reading.
    """
    
    @staticmethod
    def is_available():
        """Checks if ffprobe is installed and in PATH."""
        try:
            subprocess.run(["ffprobe", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            return False

    @staticmethod
    def get_metadata(file_path):
        """
        Returns a tuple: (width, height, fps, duration_sec)
        Returns (0, 0, 0.0, 0.0) if reading fails.
        """
        if not os.path.exists(file_path):
            return 0, 0, 0.0, 0.0

        # Command to get JSON output of stream info
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "v:0", # Only video stream
            file_path
        ]

        try:
            # Run process without opening a window on Windows (creationflags)
            if sys.platform == 'win32':
                # CREATE_NO_WINDOW = 0x08000000
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', creationflags=0x08000000)
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                
            if result.returncode != 0:
                return 0, 0, 0.0, 0.0

            data = json.loads(result.stdout)
            
            if not data.get("streams"):
                return 0, 0, 0.0, 0.0

            stream = data["streams"][0]
            
            # 1. Resolution
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
            
            # 2. FPS (FFprobe returns "num/den" string, e.g. "24000/1001")
            r_frame_rate = stream.get("r_frame_rate", "0/0")
            fps = 0.0
            if "/" in r_frame_rate:
                num, den = r_frame_rate.split("/")
                if float(den) > 0:
                    fps = float(num) / float(den)
            else:
                fps = float(r_frame_rate)

            # 3. Duration
            duration = float(stream.get("duration", 0.0))

            return width, height, fps, duration

        except Exception as e:
            print(f"[MediaEngine] Error reading {file_path}: {e}")
            return 0, 0, 0.0, 0.0