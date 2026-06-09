import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import MAX_IMAGE_FILE_BYTES, MAX_IMAGE_PIXELS
from .errors import APIError, ErrorType


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


is_image_path = is_image


def natural_sort_key(s: str) -> list:
    """
    Split string into text and numeric chunks for natural sorting.
    e.g. "10.png" -> [10, ".png"]
    """
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


def check_image_limits(path: Path) -> None:
    """
    Guardrails against oversized files or decompression bombs.
    Raises APIError with user-friendly message on violation.
    """
    try:
        stat = path.stat()
    except OSError:
        return

    if stat.st_size > MAX_IMAGE_FILE_BYTES:
        raise APIError(
            400,
            ErrorType.INVALID_FILE,
            f"Image is too large (> {MAX_IMAGE_FILE_BYTES // (1024 * 1024)} MB)",
        )

    try:
        with Image.open(path) as img:
            width, height = img.size
    except Image.DecompressionBombError as exc:
        raise APIError(400, ErrorType.INVALID_FILE, f"Image too large: {exc}") from exc
    except UnidentifiedImageError as exc:
        raise APIError(400, ErrorType.INVALID_FILE, "Not a valid image file") from exc

    if width * height > MAX_IMAGE_PIXELS:
        raise APIError(
            400,
            ErrorType.INVALID_FILE,
            f"Image dimensions exceed limit (> {MAX_IMAGE_PIXELS:,} pixels)",
        )
