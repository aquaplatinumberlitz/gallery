"""Build folder album metadata for scan and search responses."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .files import is_image, is_index_excluded_path


def has_any_children(dir_path: Path) -> bool:
    """Return whether a directory contains any child entry, ignoring unreadable directories."""
    try:
        next(dir_path.iterdir())
        return True
    except (StopIteration, PermissionError):
        return False


def has_subfolders(dir_path: Path) -> bool:
    """Return True when a directory contains at least one non-hidden child directory."""
    try:
        for entry in os.scandir(dir_path):
            if entry.name.startswith(".") or is_index_excluded_path(entry.path):
                continue
            if entry.is_dir(follow_symlinks=False):
                return True
        return False
    except (PermissionError, OSError):
        return False


def first_images_in_dir(dir_path: Path, limit: int = 3) -> list[str]:
    """Get the most recently modified images in a directory.

    Returns up to `limit` images sorted by modified time (newest first).
    """
    images: list[tuple[float, str]] = []
    try:
        for entry in dir_path.iterdir():
            if is_index_excluded_path(entry):
                continue
            if entry.is_file() and is_image(entry):
                try:
                    mtime = entry.stat().st_mtime
                    images.append((mtime, str(entry.resolve())))
                except OSError:
                    continue
    except PermissionError:
        pass
    images.sort(key=lambda x: x[0], reverse=True)
    return [path for _, path in images[:limit]]


def count_images_in_dir(dir_path: Path) -> int:
    """Count image files directly inside a directory (non-recursive)."""
    try:
        return sum(
            1
            for entry in dir_path.iterdir()
            if not entry.name.startswith(".")
            and not is_index_excluded_path(entry)
            and entry.is_file()
            and is_image(entry)
        )
    except (PermissionError, OSError):
        return 0


def build_album_metadata(path: Path) -> dict[str, Any]:
    """Build cover_images, image_count, has_children, mtime for a folder/album.

    Used by both scan and search to produce identical album node data.
    """
    cover_images = first_images_in_dir(path, limit=3)
    image_count = count_images_in_dir(path)
    children = has_any_children(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    return {
        "cover_images": cover_images,
        "image_count": image_count,
        "has_children": children,
        "mtime": mtime,
    }
