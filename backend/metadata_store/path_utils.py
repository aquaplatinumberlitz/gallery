"""Path helpers for catalog metadata."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path


def canonicalize_catalog_path(path: str | Path) -> str:
    """Return a stable lexical catalog path without requiring the path to exist."""
    text = unicodedata.normalize("NFC", str(path)).replace("\\", os.sep)
    normalized = os.path.normpath(text)
    if os.name == "nt":
        drive, tail = os.path.splitdrive(normalized)
        normalized = drive.lower() + tail
    return normalized.rstrip(os.sep) if normalized != os.sep else normalized


def catalog_path_contains(root: str | Path, candidate: str | Path) -> bool:
    """Return whether candidate is root or a descendant using path components."""
    root_text = canonicalize_catalog_path(root)
    candidate_text = canonicalize_catalog_path(candidate)
    if candidate_text == root_text:
        return True
    root_parts = Path(root_text).parts
    candidate_parts = Path(candidate_text).parts
    return len(candidate_parts) > len(root_parts) and candidate_parts[: len(root_parts)] == root_parts


def _catalog_paths_overlap(left: str | Path, right: str | Path) -> bool:
    return catalog_path_contains(left, right) or catalog_path_contains(right, left)


def _natural_sort_parts(value: str) -> list[str | int]:
    parts: list[str | int] = []
    for part in re.split(r"(\d+)", value):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part.lower())
    return parts


def _compare_natural_sql(left: str | None, right: str | None) -> int:
    left_parts = _natural_sort_parts(left or "")
    right_parts = _natural_sort_parts(right or "")
    max_len = max(len(left_parts), len(right_parts))
    for index in range(max_len):
        left_part: str | int = left_parts[index] if index < len(left_parts) else ""
        right_part: str | int = right_parts[index] if index < len(right_parts) else ""
        if isinstance(left_part, int) and isinstance(right_part, int):
            if left_part != right_part:
                return -1 if left_part < right_part else 1
        else:
            left_text = str(left_part)
            right_text = str(right_part)
            if left_text != right_text:
                return -1 if left_text < right_text else 1
    return 0


def _path_is_within(path: str, root: str) -> bool:
    return catalog_path_contains(root, path)
