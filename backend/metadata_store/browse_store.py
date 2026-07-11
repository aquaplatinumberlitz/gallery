"""Catalog browse listing helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ..models import FileNode, VideoFileNode
from ._db import _DB_LOCK, _active_asset_where, _connect
from .library_store import _find_library_for_path_conn
from .path_utils import canonicalize_catalog_path, catalog_path_contains
from .types import CatalogBrowseScopeError


def _initialize_database() -> None:
    from ._schema import initialize_database

    initialize_database()


def _browse_import_paths_conn(conn: sqlite3.Connection, library_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, library_id, path, position, created_at, updated_at
        FROM library_import_paths
        WHERE library_id = ?
        ORDER BY position, id
        """,
        (library_id,),
    ).fetchall()


def _validate_browse_scope(import_paths: list[sqlite3.Row], path: str | Path | None) -> str | None:
    if path is None or not str(path).strip():
        return None
    path_text = str(path).strip()
    if not Path(path_text).is_absolute():
        raise CatalogBrowseScopeError("Browse path must be absolute")
    scope = canonicalize_catalog_path(path_text)
    roots = [canonicalize_catalog_path(row["path"]) for row in import_paths]
    if not any(catalog_path_contains(root, scope) for root in roots):
        raise CatalogBrowseScopeError("Browse path is outside this library")
    return scope


def _browse_visibility_sql(alias: str | None, *, include_offline: bool) -> str:
    prefix = f"{alias}." if alias else ""
    clauses = [f"{prefix}deleted_at IS NULL"]
    if not include_offline:
        clauses.append(f"{prefix}offline = 0")
    return " AND ".join(clauses)


def _browse_availability_from_library_state(state: str) -> str:
    if state == "offline":
        return "unavailable"
    if state in {"degraded", "error"}:
        return "degraded"
    return "available"


def _browse_import_root_name(path: str, duplicate_leaf_names: set[str]) -> str:
    leaf = Path(path).name or path
    return path if leaf in duplicate_leaf_names else leaf


def _import_root_availability(root_path: str) -> str:
    """Return the availability state of an import root path.

    Network/offline mounts can raise ``OSError`` from ``Path.is_dir()`` (stale
    NFS handle, permission denied, unreachable host). Treat any such error as
    ``unavailable`` instead of letting the browse request fail.
    """
    try:
        return "available" if Path(root_path).is_dir() else "unavailable"
    except OSError:
        return "unavailable"


def _browse_folder_counts_conn(
    conn: sqlite3.Connection,
    library_id: int,
    folder_path: str,
    *,
    include_offline: bool,
) -> tuple[bool, int, list[str]]:
    visibility_sql = _browse_visibility_sql(None, include_offline=include_offline)
    counts = conn.execute(
        f"""
        SELECT count(*) AS children,
               sum(CASE WHEN type = 'image' THEN 1 ELSE 0 END) AS images
        FROM assets
        WHERE library_id = ? AND parent_path = ? AND {visibility_sql}
        """,
        (library_id, folder_path),
    ).fetchone()
    covers = [
        str(row["path"])
        for row in conn.execute(
            f"""
            SELECT path FROM assets
            WHERE library_id = ? AND parent_path = ? AND type = 'image' AND {visibility_sql}
            ORDER BY mtime_ns DESC LIMIT 3
            """,
            (library_id, folder_path),
        )
    ]
    return bool(counts["children"]), int(counts["images"] or 0), covers


def _browse_folder_counts_batch_conn(
    conn: sqlite3.Connection,
    library_id: int,
    folder_paths: list[str],
    *,
    include_offline: bool,
) -> dict[str, tuple[bool, int, list[str]]]:
    if not folder_paths:
        return {}
    visibility_sql = _browse_visibility_sql(None, include_offline=include_offline)
    placeholders = ", ".join("?" for _ in folder_paths)
    counts = {folder_path: (False, 0, []) for folder_path in folder_paths}
    count_rows = conn.execute(
        f"""
        SELECT parent_path,
               count(*) AS children,
               sum(CASE WHEN type IN ('image', 'photo') THEN 1 ELSE 0 END) AS images
        FROM assets
        WHERE library_id = ? AND parent_path IN ({placeholders}) AND {visibility_sql}
        GROUP BY parent_path
        """,
        (library_id, *folder_paths),
    ).fetchall()
    for row in count_rows:
        counts[str(row["parent_path"])] = (bool(row["children"]), int(row["images"] or 0), [])

    cover_rows = conn.execute(
        f"""
        SELECT parent_path, path
        FROM (
          SELECT parent_path, path,
                 row_number() OVER (PARTITION BY parent_path ORDER BY mtime_ns DESC, path ASC) AS cover_rank
          FROM assets
          WHERE library_id = ?
            AND parent_path IN ({placeholders})
            AND type IN ('image', 'photo')
            AND {visibility_sql}
        )
        WHERE cover_rank <= 3
        ORDER BY parent_path, cover_rank
        """,
        (library_id, *folder_paths),
    ).fetchall()
    covers: dict[str, list[str]] = {folder_path: [] for folder_path in folder_paths}
    for row in cover_rows:
        covers.setdefault(str(row["parent_path"]), []).append(str(row["path"]))

    return {
        folder_path: (has_children, image_count, covers.get(folder_path, []))
        for folder_path, (has_children, image_count, _) in counts.items()
    }


def _catalog_browse_virtual_root_conn(
    conn: sqlite3.Connection,
    library: sqlite3.Row,
    import_paths: list[sqlite3.Row],
    *,
    include_offline: bool,
) -> dict[str, Any]:
    leaf_counts: dict[str, int] = {}
    for row in import_paths:
        leaf = Path(str(row["path"])).name or str(row["path"])
        leaf_counts[leaf] = leaf_counts.get(leaf, 0) + 1
    duplicate_leaf_names = {leaf for leaf, count in leaf_counts.items() if count > 1}
    root_paths = [canonicalize_catalog_path(row["path"]) for row in import_paths]
    folder_counts = _browse_folder_counts_batch_conn(
        conn,
        int(library["id"]),
        root_paths,
        include_offline=include_offline,
    )
    folders: list[dict[str, Any]] = []
    for root_path in root_paths:
        has_children, image_count, cover_images = folder_counts.get(root_path, (False, 0, []))
        display_label = _browse_import_root_name(root_path, duplicate_leaf_names)
        availability = _import_root_availability(root_path)
        folders.append(
            {
                "name": display_label,
                "display_label": display_label,
                "path": root_path,
                "type": "folder",
                "entry_kind": "import_root",
                "availability": availability,
                "has_children": has_children,
                "cover_images": cover_images,
                "mtime": 0,
                "image_count": image_count,
            }
        )
    return {
        "folders": folders,
        "media": [],
        "next_media_cursor": None,
        "next_cursor": None,
        "total_images": 0,
        "total_videos": 0,
        "total_assets": 0,
        "index_source": "catalog",
        "library_id": int(library["id"]),
        "path": None,
        "request_path": None,
    }


def _catalog_browse_path_conn(
    conn: sqlite3.Connection,
    library: sqlite3.Row,
    scope_path: str,
    *,
    limit: int | None,
    cursor: int | None,
    include_offline: bool,
) -> dict[str, Any]:
    visibility_sql = _browse_visibility_sql("a", include_offline=include_offline)
    rows = conn.execute(
        f"""
        SELECT id, path, parent_path, name, type, mtime_ns, size,
               COALESCE(a_width, im_width) AS width,
               COALESCE(a_height, im_height) AS height,
               metadata_state, duration_ms, mime_type
        FROM (
            SELECT a.id, a.path, a.parent_path, a.name, a.type,
                   a.mtime_ns, a.size,
                   a.width AS a_width, a.height AS a_height,
                   im.width AS im_width, im.height AS im_height,
                   a.metadata_state, a.duration_ms, a.mime_type,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.id
                       ORDER BY ABS(im.mtime_ns - a.mtime_ns) ASC, im.id ASC
                   ) AS rn
            FROM assets AS a
            LEFT JOIN image_metadata AS im
              ON im.path = a.path AND im.size = a.size
              AND im.mtime_ns IS NOT NULL
              AND a.mtime_ns IS NOT NULL
              AND im.mtime_ns = a.mtime_ns
            WHERE a.library_id = ? AND a.parent_path = ?
              AND {visibility_sql}
        )
        WHERE rn = 1
        """,
        (int(library["id"]), scope_path),
    ).fetchall()
    from ..files import natural_sort_key

    folder_rows = sorted(
        (row for row in rows if row["type"] == "folder"), key=lambda row: natural_sort_key(row["name"])
    )
    image_rows = sorted((row for row in rows if row["type"] == "image"), key=lambda row: natural_sort_key(row["name"]))
    video_rows = sorted((row for row in rows if row["type"] == "video"), key=lambda row: natural_sort_key(row["name"]))
    media_rows = sorted([*image_rows, *video_rows], key=lambda row: natural_sort_key(row["name"]))
    media_start = cursor or 0
    media_end = media_start + limit if limit is not None else len(media_rows)
    media_page = media_rows[media_start:media_end]

    derivative_ready_by_asset: dict[int, dict[str, bool]] = {
        int(row["id"]): {"thumbnail": False, "preview": False} for row in media_page if row["type"] == "image"
    }
    if derivative_ready_by_asset:
        placeholders = ", ".join("?" for _ in derivative_ready_by_asset)
        derivative_rows = conn.execute(
            f"""
            SELECT d.asset_id, d.kind, d.cache_path
            FROM asset_derivatives d
            JOIN assets a ON a.id = d.asset_id
            WHERE d.asset_id IN ({placeholders})
              AND d.kind IN ('thumbnail', 'preview')
              AND d.status = 'ready'
              AND d.source_mtime_ns = a.mtime_ns
              AND d.source_size = a.size
              AND d.cache_path IS NOT NULL
            GROUP BY d.asset_id, d.kind
            """,
            tuple(derivative_ready_by_asset),
        ).fetchall()
        for derivative in derivative_rows:
            cache = derivative["cache_path"]
            if cache and Path(cache).is_file():
                derivative_ready_by_asset[int(derivative["asset_id"])][str(derivative["kind"])] = True

    folders: list[FileNode] = []
    folder_counts = _browse_folder_counts_batch_conn(
        conn,
        int(library["id"]),
        [str(row["path"]) for row in folder_rows],
        include_offline=include_offline,
    )
    for row in folder_rows:
        has_children, image_count, cover_images = folder_counts.get(str(row["path"]), (False, 0, []))
        folders.append(
            FileNode(
                name=row["name"],
                path=row["path"],
                type="folder",
                has_children=has_children,
                cover_images=cover_images,
                mtime=row["mtime_ns"] or 0,
                image_count=image_count,
            )
        )

    def image_node(row: sqlite3.Row) -> FileNode:
        return FileNode(
            name=row["name"],
            path=row["path"],
            type="image",
            has_children=False,
            mtime=row["mtime_ns"] or 0,
            width=row["width"],
            height=row["height"],
            asset_id=row["id"],
            metadata_state=row["metadata_state"],
            derivative_ready=derivative_ready_by_asset[int(row["id"])],
        )

    def video_node(row: sqlite3.Row) -> VideoFileNode:
        return VideoFileNode(
            name=row["name"],
            path=row["path"],
            type="video",
            has_children=False,
            mtime=row["mtime_ns"] or 0,
            width=row["width"],
            height=row["height"],
            asset_id=row["id"],
            metadata_state=row["metadata_state"],
            duration_ms=row["duration_ms"],
            mime_type=row["mime_type"],
        )

    media = [image_node(row) if row["type"] == "image" else video_node(row) for row in media_page]
    return {
        "folders": folders,
        "media": media,
        "next_media_cursor": media_end if media_end < len(media_rows) else None,
        "next_cursor": media_end if media_end < len(media_rows) else None,
        "total_images": len(image_rows),
        "total_videos": len(video_rows),
        "total_assets": len(image_rows) + len(video_rows),
        "index_source": "catalog",
        "library_id": int(library["id"]),
        "path": scope_path,
        "request_path": scope_path,
    }


def get_catalog_browse_listing(
    library_id: int,
    *,
    path: str | Path | None = None,
    limit: int | None = None,
    cursor: int | None = None,
    include_offline: bool = False,
) -> dict[str, Any]:
    """Return a read-only catalog listing for a library virtual root or folder."""
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        library = conn.execute("SELECT * FROM libraries WHERE id = ?", (library_id,)).fetchone()
        if library is None:
            raise KeyError(library_id)
        import_paths = _browse_import_paths_conn(conn, library_id)
        scope_path = _validate_browse_scope(import_paths, path)
        if scope_path is None:
            return _catalog_browse_virtual_root_conn(
                conn,
                library,
                import_paths,
                include_offline=include_offline,
            )
        return _catalog_browse_path_conn(
            conn,
            library,
            scope_path,
            limit=limit,
            cursor=cursor,
            include_offline=include_offline,
        )


def get_asset_folder_listing(
    folder_path: str | Path,
    *,
    limit: int | None = None,
    media_cursor: int | None = None,
) -> dict[str, Any] | None:
    """Return direct children from the authoritative assets catalog."""
    resolved = str(Path(folder_path).resolve())
    _initialize_database()
    with _DB_LOCK, _connect() as conn:
        library = _find_library_for_path_conn(conn, resolved)
        if library is None:
            return None
        rows = conn.execute(
            f"""
            SELECT id, path, parent_path, name, type, mtime_ns, size,
                   COALESCE(a_width, im_width) AS width,
                   COALESCE(a_height, im_height) AS height,
                   metadata_state, duration_ms, mime_type
            FROM (
                SELECT a.id, a.path, a.parent_path, a.name, a.type,
                       a.mtime_ns, a.size,
                       a.width AS a_width, a.height AS a_height,
                       im.width AS im_width, im.height AS im_height,
                       a.metadata_state, a.duration_ms, a.mime_type,
                       ROW_NUMBER() OVER (
                           PARTITION BY a.id
                           ORDER BY ABS(im.mtime_ns - a.mtime_ns) ASC, im.id ASC
                       ) AS rn
                FROM assets AS a
                LEFT JOIN image_metadata AS im
                  ON im.path = a.path AND im.size = a.size
                  AND im.mtime_ns IS NOT NULL
                  AND a.mtime_ns IS NOT NULL
                  AND im.mtime_ns = a.mtime_ns
                WHERE a.library_id = ? AND a.parent_path = ?
                  AND {_active_asset_where("a")}
            )
            WHERE rn = 1
            """,
            (library["id"], resolved),
        ).fetchall()
        if not rows and library["state"] in {"discovering", "indexing"}:
            # Bootstrap compatibility: the first request seeds both catalogs;
            # subsequent requests for this folder are DB-backed.
            return None
        from ..files import natural_sort_key

        folder_rows = sorted(
            (row for row in rows if row["type"] == "folder"), key=lambda row: natural_sort_key(row["name"])
        )
        image_rows = sorted(
            (row for row in rows if row["type"] == "image"), key=lambda row: natural_sort_key(row["name"])
        )
        video_rows = sorted(
            (row for row in rows if row["type"] == "video"), key=lambda row: natural_sort_key(row["name"])
        )
        total_images = len(image_rows)
        media_rows = sorted([*image_rows, *video_rows], key=lambda row: natural_sort_key(row["name"]))
        media_start = media_cursor or 0
        media_end = media_start + limit if limit is not None else len(media_rows)
        media_page = media_rows[media_start:media_end]

        derivative_ready_by_asset: dict[int, dict[str, bool]] = {
            int(row["id"]): {"thumbnail": False, "preview": False} for row in media_page if row["type"] == "image"
        }
        if derivative_ready_by_asset:
            placeholders = ", ".join("?" for _ in derivative_ready_by_asset)
            derivative_rows = conn.execute(
                f"""
                SELECT d.asset_id, d.kind, d.cache_path
                FROM asset_derivatives d
                JOIN assets a ON a.id = d.asset_id
                WHERE d.asset_id IN ({placeholders})
                  AND d.kind IN ('thumbnail', 'preview')
                  AND d.status = 'ready'
                  AND d.source_mtime_ns = a.mtime_ns
                  AND d.source_size = a.size
                  AND d.cache_path IS NOT NULL
                GROUP BY d.asset_id, d.kind
                """,
                tuple(derivative_ready_by_asset),
            ).fetchall()
            for derivative in derivative_rows:
                cache = derivative["cache_path"]
                if cache and Path(cache).is_file():
                    derivative_ready_by_asset[int(derivative["asset_id"])][str(derivative["kind"])] = True

        folders: list[FileNode] = []
        for row in folder_rows:
            counts = conn.execute(
                f"""
                SELECT count(*) AS children,
                       sum(CASE WHEN type = 'image' THEN 1 ELSE 0 END) AS images
                FROM assets
                WHERE library_id = ? AND parent_path = ? AND {_active_asset_where()}
                """,
                (library["id"], row["path"]),
            ).fetchone()
            covers = [
                cover["path"]
                for cover in conn.execute(
                    f"""
                    SELECT path FROM assets
                    WHERE library_id = ? AND parent_path = ? AND type = 'image' AND {_active_asset_where()}
                    ORDER BY mtime_ns DESC LIMIT 3
                    """,
                    (library["id"], row["path"]),
                )
            ]
            folders.append(
                FileNode(
                    name=row["name"],
                    path=row["path"],
                    type="folder",
                    has_children=bool(counts["children"]),
                    cover_images=covers,
                    mtime=row["mtime_ns"] or 0,
                    image_count=int(counts["images"] or 0),
                )
            )

        def image_node(row: sqlite3.Row) -> FileNode:
            return FileNode(
                name=row["name"],
                path=row["path"],
                type="image",
                has_children=False,
                mtime=row["mtime_ns"] or 0,
                width=row["width"],
                height=row["height"],
                asset_id=row["id"],
                metadata_state=row["metadata_state"],
                derivative_ready=derivative_ready_by_asset[int(row["id"])],
            )

        def video_node(row: sqlite3.Row) -> VideoFileNode:
            return VideoFileNode(
                name=row["name"],
                path=row["path"],
                type="video",
                has_children=False,
                mtime=row["mtime_ns"] or 0,
                width=row["width"],
                height=row["height"],
                asset_id=row["id"],
                duration_ms=row["duration_ms"],
                mime_type=row["mime_type"],
            )

        media = [image_node(row) if row["type"] == "image" else video_node(row) for row in media_page]
        result = {
            "folders": folders,
            "media": media,
            "next_media_cursor": media_end if media_end < len(media_rows) else None,
            "total_images": total_images,
            "total_videos": len(video_rows),
            "total_assets": total_images + len(video_rows),
            "index_source": "warm_db",
        }
        return result
