"""Resolve private media tools without modifying the machine's PATH or Python."""
from functools import lru_cache
from pathlib import Path
import shutil

APP_ROOT = Path(__file__).resolve().parents[1]


def ffmpeg_path():
    bundled = APP_ROOT / 'runtime' / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
    return str(bundled) if bundled.is_file() else shutil.which('ffmpeg')


@lru_cache(maxsize=1)
def image_support():
    try:
        from PIL import Image
        # Detect broken native wheels as well as missing Pillow.
        Image.new('RGB', (1, 1)).close()
        return True
    except (ImportError, OSError):
        return False
