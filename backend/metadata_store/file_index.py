"""File index and directory tree persistence helpers."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import sqlite3
import subprocess
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..files import asset_type_for_path, is_asset_path, is_index_excluded_path
from ..metadata_extract import parse_int
from ._asset_store import _upsert_asset_conn
from ._db import _DB_LOCK, _connect
from .library_store import _find_library_for_path_conn, _library_exclusion_patterns_conn, get_library_for_path
from .metadata_persist import index_images

logger = logging.getLogger(__name__)


def _initialize_database() -> None:
    from . import initialize_database

    initialize_database()


def _search_like_escape(value: str) -> str:
    from . import _like_escape

    return _like_escape(value)


def _search_is_inside_root(path: Path, root: Path) -> bool:
    from . import _is_inside_root

    return _is_inside_root(path, root)


def _path_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _normalize_file_type(type_value: str) -> str:
    if type_value in {"image", "photo", "file"}:
        return "image"
    if type_value == "video":
        return "video"
    return "folder"


def index_file(
    path: str | Path,
    name: str,
    parent_path: str | Path,
    type: str,
    mtime: float | None,
    size: int | None,
    width: int | None,
    height: int | None,
    mime_type: str | None = None,
    duration_ms: int | None = None,
    codec: str | None = None,
) -> bool:
    """Upsert one folder or media row into the file index and asset catalog."""
    if is_index_excluded_path(path):
        return False
    resolved_path = str(Path(path).resolve())
    resolved_parent = str(Path(parent_path).resolve())
    normalized_type = _normalize_file_type(type)
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        library = _find_library_for_path_conn(conn, resolved_path)
        library_id = int(library["id"]) if library is not None else None
        if library is not None and is_index_excluded_path(
            resolved_path,
            library["matched_import_path"],
            _library_exclusion_patterns_conn(conn, int(library["id"])),
        ):
            return False
        mtime_ns = None
        with suppress(OSError):
            mtime_ns = Path(resolved_path).stat().st_mtime_ns
        conn.execute(
            """
            INSERT INTO file_index (
              path, name, parent_path, type, mtime, mtime_ns, size, width,
              height, indexed_at, library_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              name=excluded.name,
              parent_path=excluded.parent_path,
              type=excluded.type,
              mtime=excluded.mtime,
              mtime_ns=excluded.mtime_ns,
              size=excluded.size,
              width=excluded.width,
              height=excluded.height,
              indexed_at=excluded.indexed_at,
              library_id=excluded.library_id
            """,
            (
                resolved_path,
                name,
                resolved_parent,
                normalized_type,
                mtime,
                mtime_ns,
                size,
                width,
                height,
                time.time(),
                library_id,
            ),
        )
        _upsert_asset_conn(
            conn,
            path=resolved_path,
            name=name,
            parent_path=resolved_parent,
            type=normalized_type,
            mtime_ns=mtime,
            size=size,
            width=width,
            height=height,
            mime_type=mime_type,
            duration_ms=duration_ms,
            codec=codec,
        )
        conn.execute("DELETE FROM file_index_fts WHERE path = ?", (resolved_path,))
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, ?, ?)",
            (name, resolved_path, normalized_type, resolved_parent),
        )
    return True


def _cleanup_stale_index_conn(
    conn: sqlite3.Connection,
    root_path: str | Path | None = None,
    *,
    remove_outside_scope: bool = True,
) -> int:
    root = Path(root_path).resolve() if root_path is not None else None
    candidate_paths: set[str] = set()
    for table in ("file_index", "file_index_fts", "image_metadata", "metadata_index_jobs"):
        candidate_paths.update(row["path"] for row in conn.execute(f"SELECT path FROM {table}"))

    stale_paths: list[str] = []

    for path_value in candidate_paths:
        path = Path(path_value)
        if root is not None and not _search_is_inside_root(path, root):
            if remove_outside_scope:
                stale_paths.append(path_value)
            continue
        if not path.exists():
            stale_paths.append(path_value)

    if not stale_paths:
        return 0

    conn.executemany("DELETE FROM file_index_fts WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM file_index WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM image_metadata WHERE path = ?", ((path,) for path in stale_paths))
    conn.executemany("DELETE FROM metadata_index_jobs WHERE path = ?", ((path,) for path in stale_paths))
    return len(stale_paths)


def _cleanup_ignored_index_conn(conn: sqlite3.Connection, root_path: str | Path | None = None) -> int:
    root = Path(root_path).resolve() if root_path is not None else None
    candidate_paths: set[str] = set()
    for table in ("file_index", "file_index_fts", "image_metadata", "metadata_index_jobs", "folder_index_state"):
        candidate_paths.update(row["path"] for row in conn.execute(f"SELECT path FROM {table}"))

    ignored_paths = [
        path_value
        for path_value in candidate_paths
        if (root is None or _search_is_inside_root(Path(path_value), root)) and is_index_excluded_path(path_value)
    ]
    if not ignored_paths:
        return 0

    conn.executemany("DELETE FROM file_index_fts WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM file_index WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM image_metadata WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM metadata_index_jobs WHERE path = ?", ((path,) for path in ignored_paths))
    conn.executemany("DELETE FROM folder_index_state WHERE path = ?", ((path,) for path in ignored_paths))
    return len(ignored_paths)


def cleanup_stale_index(
    state: Any,
    root_path: str | Path | None = None,
    *,
    remove_outside_scope: bool = True,
) -> int:
    """Remove stale database rows for missing or out-of-root paths.

    This only deletes index records. It never deletes filesystem entries.
    """
    _initialize_database()
    if isinstance(state, sqlite3.Connection):
        return _cleanup_stale_index_conn(state, root_path, remove_outside_scope=remove_outside_scope)

    with _DB_LOCK, _connect() as conn:
        return _cleanup_stale_index_conn(conn, root_path, remove_outside_scope=remove_outside_scope)


def cleanup_ignored_index(root_path: str | Path | None = None) -> int:
    """Remove ignored dependency/cache/app-build paths from persisted index rows only."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        return _cleanup_ignored_index_conn(conn, root_path)


def _scoped_path_where(root: Path) -> tuple[str, list[Any]]:
    resolved = str(root.resolve())
    prefix = f"{resolved.rstrip(os.sep)}{os.sep}"
    return "(path = ? OR path LIKE ? ESCAPE '\\')", [resolved, f"{_search_like_escape(prefix)}%"]


def clear_index_records(root_path: str | Path) -> dict[str, int]:
    """Delete persisted index/cache rows under root_path without touching files on disk."""
    _initialize_database()
    root = Path(root_path).resolve()
    where, params = _scoped_path_where(root)
    tables = ("file_index_fts", "file_index", "image_metadata", "metadata_index_jobs", "folder_index_state")
    deleted: dict[str, int] = {}

    with _DB_LOCK, _connect() as conn:
        for table in tables:
            row = conn.execute(f"SELECT count(*) AS total FROM {table} WHERE {where}", params).fetchone()
            deleted[table] = int(row["total"] if row else 0)
            conn.execute(f"DELETE FROM {table} WHERE {where}", params)

    return deleted


def index_directory_tree(
    root: str | Path,
    include_metadata: bool = False,
    collected_image_paths: list[Path] | None = None,
    collected_asset_paths: set[str] | None = None,
) -> int:
    """Recreate file_index rows under root. Optionally extract metadata or collect image paths.

    Symlinked directories are skipped to avoid traversal loops. Hidden files and
    folders are ignored to match the existing scanner behavior.
    """
    root_path = Path(root).resolve()
    indexed = 0
    local_image_paths: list[Path] = [] if include_metadata else None  # type: ignore[assignment]
    library = get_library_for_path(root_path)
    import_root = library["matched_import_path"] if library is not None else None
    exclusion_patterns = library["exclusion_patterns"] if library is not None else []

    def visit(folder: Path, visited_inodes: set[tuple[int, int]]) -> None:
        nonlocal indexed
        if is_index_excluded_path(folder, import_root, exclusion_patterns):
            return
        try:
            stat = folder.stat()
            folder_inode = (stat.st_dev, stat.st_ino)
            if folder_inode in visited_inodes:
                return
            visited_inodes.add(folder_inode)
        except OSError:
            return

        try:
            if index_file(folder, folder.name or str(folder), folder.parent, "folder", stat.st_mtime, None, None, None):
                indexed += 1
            if collected_asset_paths is not None:
                collected_asset_paths.add(str(folder.resolve()))
        except OSError:
            return
        except Exception:  # noqa: BLE001
            pass

        try:
            entries = list(folder.iterdir())
        except (OSError, PermissionError):
            return

        for entry in entries:
            if entry.name.startswith(".") or is_index_excluded_path(entry, import_root, exclusion_patterns):
                continue
            try:
                # Skip symlinked directories to avoid loops; files are still followed.
                if entry.is_dir() and not entry.is_symlink():
                    visit(entry, visited_inodes)
                elif entry.is_file() and is_asset_path(entry):
                    stat = entry.stat()
                    asset_type = asset_type_for_path(entry)
                    width = None
                    height = None
                    duration_ms = None
                    codec = None
                    mime_type = mimetypes.guess_type(entry.name)[0]
                    if asset_type == "video":
                        try:
                            result = subprocess.run(
                                [
                                    "ffprobe",
                                    "-v",
                                    "quiet",
                                    "-print_format",
                                    "json",
                                    "-show_format",
                                    "-show_streams",
                                    str(entry),
                                ],
                                capture_output=True,
                                text=True,
                                timeout=5,
                                check=False,
                            )
                            if result.returncode == 0:
                                probe = json.loads(result.stdout)
                                duration = probe.get("format", {}).get("duration")
                                if duration is not None:
                                    duration_ms = int(float(duration) * 1000)
                                video_stream = next(
                                    (
                                        stream
                                        for stream in probe.get("streams", [])
                                        if stream.get("codec_type") == "video"
                                    ),
                                    None,
                                )
                                if video_stream is not None:
                                    codec = video_stream.get("codec_name")
                                    width = parse_int(video_stream.get("width"))
                                    height = parse_int(video_stream.get("height"))
                        except (OSError, subprocess.SubprocessError, TypeError, ValueError, json.JSONDecodeError):
                            logger.debug("Could not probe video metadata for %s", entry, exc_info=True)
                    if index_file(
                        entry,
                        entry.name,
                        entry.parent,
                        asset_type or "folder",
                        stat.st_mtime,
                        stat.st_size,
                        width,
                        height,
                        mime_type=mime_type,
                        duration_ms=duration_ms,
                        codec=codec,
                    ):
                        indexed += 1
                    if collected_asset_paths is not None:
                        collected_asset_paths.add(str(entry.resolve()))
                    if include_metadata and asset_type == "image":
                        local_image_paths.append(entry)
                    if collected_image_paths is not None and asset_type == "image":
                        collected_image_paths.append(entry)
            except (OSError, PermissionError):
                continue

    visit(root_path, set())
    if include_metadata and local_image_paths:
        indexed += index_images(local_image_paths)
    return indexed
