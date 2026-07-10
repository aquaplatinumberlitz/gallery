"""File classification and safety helpers for gallery image handling."""

import os
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from wcmatch import glob

from .config import MAX_IMAGE_FILE_BYTES, MAX_IMAGE_PIXELS
from .errors import APIError, ErrorType

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"}
DEFAULT_INDEX_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
    }
)
DEFAULT_INDEX_EXCLUDED_SEGMENTS = (
    ("frontend", "public"),
    ("frontend", "dist"),
    ("frontend", "build"),
    ("frontend", "coverage"),
    ("frontend", "test-results"),
    ("frontend", "playwright-report"),
    ("backend", "__pycache__"),
    ("backend", ".cache"),
)


def _configured_excluded_dir_names() -> set[str]:
    configured = {item.strip() for item in os.getenv("GALLERY_INDEX_EXCLUDE_DIRS", "").split(",") if item.strip()}
    return set(DEFAULT_INDEX_EXCLUDED_DIR_NAMES) | configured


def _configured_excluded_segments() -> tuple[tuple[str, ...], ...]:
    configured = tuple(
        tuple(part for part in item.strip().replace("\\", "/").split("/") if part)
        for item in os.getenv("GALLERY_INDEX_EXCLUDE_PATTERNS", "").split(",")
        if item.strip()
    )
    return DEFAULT_INDEX_EXCLUDED_SEGMENTS + configured


def _path_parts(path: str | Path) -> tuple[str, ...]:
    return tuple(part for part in Path(path).parts if part not in {"", Path(path).anchor})


def _contains_segment(parts: tuple[str, ...], segment: tuple[str, ...]) -> bool:
    if not segment or len(segment) > len(parts):
        return False
    return any(parts[index : index + len(segment)] == segment for index in range(len(parts) - len(segment) + 1))


def _matches_library_exclusion(
    path: str | Path,
    import_root: str | Path,
    exclusion_patterns: tuple[str, ...] | list[str],
) -> bool:
    try:
        relative = Path(path).resolve().relative_to(Path(import_root).resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return False
    if relative in {"", "."}:
        return False
    flags = glob.GLOBSTAR
    if os.name == "nt":
        flags |= glob.IGNORECASE
    candidates = (relative, f"{relative.rstrip('/')}/")
    return any(
        glob.globmatch(candidate, pattern, flags=flags) for pattern in exclusion_patterns for candidate in candidates
    )


def is_index_excluded_path(
    path: str | Path,
    import_root: str | Path | None = None,
    exclusion_patterns: tuple[str, ...] | list[str] = (),
) -> bool:
    """Return True for default or per-library paths excluded from the gallery index."""
    parts = _path_parts(path)
    excluded_names = _configured_excluded_dir_names()
    if any(part in excluded_names for part in parts):
        return True
    if any(_contains_segment(parts, segment) for segment in _configured_excluded_segments()):
        return True
    return bool(
        import_root is not None
        and exclusion_patterns
        and _matches_library_exclusion(path, import_root, exclusion_patterns)
    )


def is_image(path: Path) -> bool:
    """Return whether a path has a supported image file extension."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


is_image_path = is_image


def is_video_path(path: Path) -> bool:
    """Return whether a path has a supported video file extension."""
    return path.suffix.lower() in VIDEO_EXTENSIONS


def is_asset_path(path: Path) -> bool:
    """Return whether a path is a supported gallery asset."""
    return is_image_path(path) or is_video_path(path)


def asset_type_for_path(path: Path) -> str | None:
    """Return the catalog asset type for a supported path."""
    if is_video_path(path):
        return "video"
    if is_image_path(path):
        return "image"
    return None


def natural_sort_key(s: str) -> list:
    """Split string into text and numeric chunks for natural sorting.

    e.g. "10.png" -> [10, ".png"]
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def check_image_limits(path: Path) -> None:
    """Guardrails against oversized files or decompression bombs.

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
