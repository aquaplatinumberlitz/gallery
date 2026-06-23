"""Warm folder index state and scan-result indexing helpers."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from ..files import is_image_path
from ..models import FileNode, VideoFileNode
from ._db import _DB_LOCK, _connect

logger = logging.getLogger(__name__)


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _warm_indexed_listing_enabled() -> bool:
    from . import ENABLE_WARM_INDEXED_LISTING

    return bool(ENABLE_WARM_INDEXED_LISTING)


def _file_index_path_value(item: Any, key: str, default: Any = None) -> Any:
    from . import _path_value

    return _path_value(item, key, default)


def _file_index_normalize_file_type(type_value: str) -> str:
    from . import _normalize_file_type

    return _normalize_file_type(type_value)


def _file_index_index_file(*args: Any, **kwargs: Any) -> bool:
    from . import index_file

    return index_file(*args, **kwargs)


def update_folder_index_state(
    folder_path: str | Path,
    *,
    dir_mtime_ns: int | None = None,
    complete: bool = False,
    child_count: int = 0,
    folder_count: int = 0,
    image_count: int = 0,
    last_error: str | None = None,
) -> bool:
    """Upsert warm-listing state for a folder and return whether it was persisted."""
    _initialize_database()
    now = time.time()
    try:
        resolved = str(Path(folder_path).resolve())
        if dir_mtime_ns is None:
            try:
                dir_mtime_ns = Path(folder_path).stat().st_mtime_ns
            except OSError:
                return False
        with _DB_LOCK, _connect() as conn:
            conn.execute(
                """
                INSERT INTO folder_index_state (
                  path, dir_mtime_ns, indexed_at, complete,
                  child_count, folder_count, image_count,
                  last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  dir_mtime_ns=excluded.dir_mtime_ns,
                  indexed_at=excluded.indexed_at,
                  complete=excluded.complete,
                  child_count=excluded.child_count,
                  folder_count=excluded.folder_count,
                  image_count=excluded.image_count,
                  last_error=excluded.last_error,
                  updated_at=excluded.updated_at
                """,
                (
                    resolved,
                    dir_mtime_ns,
                    now,
                    1 if complete else 0,
                    child_count,
                    folder_count,
                    image_count,
                    last_error,
                    now,
                ),
            )
        return True
    except Exception:  # noqa: BLE001
        return False


def get_folder_index_state(folder_path: str | Path) -> dict | None:
    """Return persisted warm-listing state for a folder, or None on miss/error."""
    _initialize_database()
    try:
        resolved = str(Path(folder_path).resolve())
        with _DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT * FROM folder_index_state WHERE path = ?",
                (resolved,),
            ).fetchone()
            if row is None:
                return None
            return dict(row)
    except Exception:  # noqa: BLE001
        return None


# TODO: Future optimization — add a persisted natural sort key column to file_index
# so very large warm folders can use DB-level ORDER BY + LIMIT without loading all
# direct child rows into Python.
def get_warm_folder_listing(
    folder_path: str | Path,
    *,
    limit: int | None = None,
    sort: str = "name",
    media_cursor: int | None = None,
) -> dict | None:
    """Return a folder listing from SQLite when the persisted folder state is current."""
    if not _warm_indexed_listing_enabled():
        return None

    try:
        resolved = str(Path(folder_path).resolve())
        resolved_path = Path(folder_path)
    except OSError:
        return None

    state = get_folder_index_state(resolved)
    if state is None:
        return None
    if not state["complete"]:
        return None

    try:
        current_stat = resolved_path.stat()
        current_mtime_ns = current_stat.st_mtime_ns
    except OSError:
        return None

    if state["dir_mtime_ns"] != current_mtime_ns:
        return None

    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        f"{resolved.rstrip(os.sep)}{os.sep}"

        raw_folders = list(
            conn.execute(
                """
                SELECT path, name, mtime
                FROM file_index
                WHERE parent_path = ? AND type = 'folder'
                """,
                (resolved,),
            )
        )

        total_images_row = conn.execute(
            "SELECT count(*) AS total FROM file_index WHERE parent_path = ? AND type IN ('image', 'photo')",
            (resolved,),
        ).fetchone()
        total_images = int(total_images_row["total"])

        raw_images = list(
            conn.execute(
                """
                SELECT fi.path, fi.name, fi.mtime, fi.size,
                       COALESCE(fi.width, im.width) AS width,
                       COALESCE(fi.height, im.height) AS height
                FROM file_index AS fi
                LEFT JOIN image_metadata AS im ON im.path = fi.path
                WHERE fi.parent_path = ? AND fi.type IN ('image', 'photo')
                """,
                (resolved,),
            )
        )
        raw_videos = list(
            conn.execute(
                """
                SELECT fi.path, fi.name, fi.mtime, fi.width, fi.height,
                       a.duration_ms, a.mime_type
                FROM file_index AS fi
                LEFT JOIN assets AS a ON a.path = fi.path
                WHERE fi.parent_path = ? AND fi.type = 'video'
                """,
                (resolved,),
            )
        )

        # Sort in Python with natural_sort_key to match direct scan order
        from ..files import natural_sort_key

        raw_folders.sort(key=lambda x: natural_sort_key(x["name"]))
        raw_images.sort(key=lambda x: natural_sort_key(x["name"]))
        raw_videos.sort(key=lambda x: natural_sort_key(x["name"]))

        raw_media = sorted([*raw_images, *raw_videos], key=lambda row: natural_sort_key(row["name"]))
        media_start = media_cursor or 0
        media_end = media_start + limit if limit is not None else len(raw_media)
        media_page = raw_media[media_start:media_end]
        image_paths = {item["path"] for item in raw_images}
        warm_media = [
            FileNode(
                name=item["name"],
                path=item["path"],
                type="image",
                has_children=False,
                cover_images=[],
                mtime=item["mtime"] or 0,
                width=item["width"],
                height=item["height"],
            )
            if item["path"] in image_paths
            else VideoFileNode(
                name=item["name"],
                path=item["path"],
                type="video",
                has_children=False,
                cover_images=[],
                mtime=item["mtime"] or 0,
                width=item["width"],
                height=item["height"],
                duration_ms=item["duration_ms"],
                mime_type=item["mime_type"],
            )
            for item in media_page
        ]

        # Build DB-derived folder metadata — no filesystem access
        child_paths = [f["path"] for f in raw_folders]
        child_cover_images: dict[str, list[str]] = {}
        child_counts: dict[str, dict] = {}
        if child_paths:
            placeholders = ",".join("?" for _ in child_paths)
            cover_rows = conn.execute(
                f"""
                SELECT parent_path, path
                FROM file_index
                WHERE parent_path IN ({placeholders}) AND type IN ('image', 'photo')
                ORDER BY mtime DESC
                """,
                child_paths,
            ).fetchall()
            for r in cover_rows:
                pp = r["parent_path"]
                if pp not in child_cover_images:
                    child_cover_images[pp] = []
                if len(child_cover_images[pp]) < 3:
                    child_cover_images[pp].append(r["path"])

            count_rows = conn.execute(
                f"""
                SELECT parent_path,
                       count(*) AS total,
                       sum(CASE WHEN type = 'folder' THEN 1 ELSE 0 END) AS subfolder_count,
                       sum(CASE WHEN type IN ('image', 'photo') THEN 1 ELSE 0 END) AS photo_count
                FROM file_index
                WHERE parent_path IN ({placeholders})
                GROUP BY parent_path
                """,
                child_paths,
            ).fetchall()
            for r in count_rows:
                child_counts[r["parent_path"]] = {
                    "child_count": int(r["total"]),
                    "folder_count": int(r["subfolder_count"]),
                    "image_count": int(r["photo_count"]),
                }

        warm_folders: list[FileNode] = []
        for fld in raw_folders:
            fp = fld["path"]
            cc = child_counts.get(fp, {})
            warm_folders.append(
                FileNode(
                    name=fld["name"],
                    path=fp,
                    type="folder",
                    has_children=cc.get("child_count", 0) > 0,
                    cover_images=child_cover_images.get(fp, []),
                    mtime=fld["mtime"] or 0,
                    image_count=cc.get("image_count", 0),
                )
            )

    result = {
        "folders": warm_folders,
        "media": warm_media,
        "next_media_cursor": media_end if media_end < len(raw_media) else None,
        "total_images": total_images,
        "total_videos": len(raw_videos),
        "total_assets": total_images + len(raw_videos),
        "index_source": "warm_db",
    }
    return result


def get_folder_indexed_paths() -> list[dict]:
    """Return persisted folder index state rows ordered by most recent update."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT path, dir_mtime_ns, complete, image_count, updated_at FROM folder_index_state ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_folder_index_incomplete(folder_path: str | Path, last_error: str | None = None) -> bool:
    """Mark a folder's warm-listing state incomplete after a change or refresh failure."""
    return update_folder_index_state(folder_path, complete=False, last_error=last_error)


def _scan_folder_counts(folder_path: Path) -> dict:
    folders = 0
    images = 0
    total = 0
    try:
        for entry in os.scandir(folder_path):
            if entry.name.startswith("."):
                continue
            total += 1
            try:
                if entry.is_dir():
                    folders += 1
                elif entry.is_file() and is_image_path(Path(entry.path)):
                    images += 1
            except OSError:
                pass
    except OSError:
        pass
    return {"child_count": total, "folder_count": folders, "image_count": images}


def index_files_from_scan(folders: list[Any], media: list[Any], *, scan_folder_path: str | Path | None = None) -> int:
    """Persist file index rows produced by a scan response and update folder state."""
    indexed = 0
    for item in [*folders, *media]:
        raw_path = _file_index_path_value(item, "path")
        if not raw_path:
            continue
        path = Path(raw_path)
        try:
            stat = path.stat()
        except OSError:
            stat = None
        try:
            if _file_index_index_file(
                path=path,
                name=_file_index_path_value(item, "name", path.name),
                parent_path=path.parent,
                type=_file_index_path_value(item, "type", "photo"),
                mtime=_file_index_path_value(item, "mtime", stat.st_mtime if stat else None),
                size=stat.st_size if stat and path.is_file() else None,
                width=_file_index_path_value(item, "width", None),
                height=_file_index_path_value(item, "height", None),
            ):
                indexed += 1
        except (OSError, sqlite3.Error):
            logger.exception("Failed to index file")
            continue

    if scan_folder_path is not None:
        image_count = sum(
            1
            for item in media
            if _file_index_normalize_file_type(_file_index_path_value(item, "type", "image")) == "image"
        )
        with suppress(Exception):
            update_folder_index_state(
                scan_folder_path,
                complete=True,
                child_count=len(folders) + len(media),
                folder_count=len(folders),
                image_count=image_count,
            )
    return indexed
