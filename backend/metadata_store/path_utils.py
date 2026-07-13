"""Path helpers for catalog metadata."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any


def canonicalize_catalog_path(path: str | Path) -> str:
    """Return a stable lexical catalog path without requiring the path to exist."""
    text = unicodedata.normalize("NFC", str(path))
    if os.name == "nt":
        text = text.replace("/", os.sep)
    normalized = os.path.normpath(text)
    if os.name == "nt":
        normalized = os.path.normcase(normalized)
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


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def path_scope_sql(
    root: str | Path,
    *,
    column: str = "path",
    leading_and: bool = False,
) -> tuple[str, list[Any]]:
    """Build a component-safe, case-sensitive SQLite path scope predicate."""
    resolved = canonicalize_catalog_path(root)
    prefix = resolved if resolved.endswith(os.sep) else resolved + os.sep
    predicate = f"({column} = ? OR ({column} LIKE ? ESCAPE '\\' COLLATE BINARY AND substr({column}, 1, ?) = ?))"
    if leading_and:
        predicate = f" AND {predicate}"
    return predicate, [resolved, f"{_like_escape(prefix)}%", len(prefix), prefix]


def named_path_scope_sql(
    root: str | Path,
    *,
    column: str = "path",
    parameter_prefix: str = "scope",
    leading_and: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Named-parameter variant of :func:`path_scope_sql`."""
    resolved = canonicalize_catalog_path(root)
    prefix = resolved if resolved.endswith(os.sep) else resolved + os.sep
    root_key = f"{parameter_prefix}_root"
    like_key = f"{parameter_prefix}_prefix"
    length_key = f"{parameter_prefix}_length"
    prefix_key = f"{parameter_prefix}_exact_prefix"
    predicate = (
        f"({column} = :{root_key} OR "
        f"({column} LIKE :{like_key} ESCAPE '\\' COLLATE BINARY "
        f"AND substr({column}, 1, :{length_key}) = :{prefix_key}))"
    )
    if leading_and:
        predicate = f" AND {predicate}"
    return predicate, {
        root_key: resolved,
        like_key: f"{_like_escape(prefix)}%",
        length_key: len(prefix),
        prefix_key: prefix,
    }
