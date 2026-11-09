"""Catalog browse listing helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from ..files import content_version
from ..models import FileNode, VideoFileNode
from ._db import _active_asset_where, _connect_read
from ._schema_ensure import FOLDER_IMAGE_INDEX_NAME
from .identity import (
    asset_matches_metadata_job_sql,
    catalog_direct_child_sql,
    catalog_import_path_owns_sql,
    catalog_path_is_canonical_sql,
)
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


COVER_LIMIT = 3
_DESCENDANT_COVER_BATCH = 300


def _cover_readable_sql(alias: str) -> str:
    """Return the predicate that keeps assets known to be unreadable out of folder covers.

    A cover is a readable image. Two failure signals exist and both are cheap indexed probes, so the check
    works the same on a library that was scanned a moment ago and on one that has been indexed for months:

    * metadata: ``assets.metadata_state = 'failed'``, or a ``failed`` metadata job (``path`` is its primary
      key) for the asset's current ``mtime_ns``/``size`` identity; the job is what an undecodable file
      leaves behind (``fail_metadata_job``);
    * derivatives: a ``thumbnail`` derivative of the current identity that ended ``failed`` with the terminal
      ``invalid_source`` result code. Decoding is per source, so one variant is enough; retryable failures
      (``attempts_exhausted``, ``internal_error``) do not hide a cover.

    A fresh scan has no failure signal yet, so a file that is unreadable but not yet processed can still be
    a cover until its metadata job runs. A changed file has a new identity and is judged again.
    """
    job_match = asset_matches_metadata_job_sql(asset_alias=alias, job_alias="cover_mj")
    return f"""{alias}.metadata_state IS NOT 'failed'
        AND NOT EXISTS (
          SELECT 1 FROM metadata_index_jobs AS cover_mj
          WHERE cover_mj.path = {alias}.path AND cover_mj.state = 'failed' AND cover_mj.size = {alias}.size
            AND {job_match}
        )
        AND NOT EXISTS (
          SELECT 1 FROM asset_derivatives AS cover_d
          JOIN derivative_jobs AS cover_dj ON cover_dj.derivative_id = cover_d.id
          WHERE cover_d.asset_id = {alias}.id AND cover_d.kind = 'thumbnail' AND cover_d.status = 'failed'
            AND cover_d.source_mtime_ns = {alias}.mtime_ns AND cover_d.source_size = {alias}.size
            AND cover_dj.result_code = 'invalid_source'
        )"""


def _cover_unreadable_cte(library_id: int) -> str:
    """The set form of ``_cover_readable_sql``: ``cover_unreadable(id)``, built once per query.

    ``CROSS JOIN`` pins the loop order (small sets drive the probes). Failed jobs are few, so scanning them once and probing a set per candidate row is much cheaper than
    running correlated probes for every asset of a large subtree. Same signals, same identity rules.
    """
    lib = int(library_id)
    return f"""cover_unreadable(id) AS (
          SELECT a.id FROM metadata_index_jobs AS cover_mj
          CROSS JOIN assets AS a ON a.library_id = {lib} AND a.path = cover_mj.path AND a.size = cover_mj.size
          WHERE cover_mj.state = 'failed' AND {asset_matches_metadata_job_sql(asset_alias="a", job_alias="cover_mj")}
          UNION
          SELECT a.id FROM asset_derivatives AS cover_d
          CROSS JOIN derivative_jobs AS cover_dj ON cover_dj.derivative_id = cover_d.id
          CROSS JOIN assets AS a ON a.id = cover_d.asset_id
          WHERE cover_d.status = 'failed' AND cover_d.kind = 'thumbnail' AND cover_dj.result_code = 'invalid_source'
            AND cover_d.source_mtime_ns = a.mtime_ns AND cover_d.source_size = a.size
        )"""


def _cover_readable_set_sql(alias: str) -> str:
    return f"{alias}.metadata_state IS NOT 'failed' AND {alias}.id NOT IN (SELECT id FROM cover_unreadable)"


def _descendant_bounds(folder_path: str) -> tuple[str, str]:
    """Half-open ``path`` range ``[lo, hi)`` that holds exactly the paths below ``folder_path``."""
    prefix = folder_path if folder_path.endswith(os.sep) else folder_path + os.sep
    return prefix, prefix[:-1] + chr(ord(prefix[-1]) + 1)


def _browse_descendant_covers_conn(
    conn: sqlite3.Connection,
    library_id: int,
    folder_paths: list[str],
    *,
    include_offline: bool,
) -> list[sqlite3.Row]:
    """Top covers of each folder from its descendants: one ranged query per batch, not one per folder.

    The same order as direct covers (``mtime_ns DESC, path ASC``), over every readable image below the
    folder. The ``assets(library_id, path)`` index serves the ``[lo, hi)`` range of each folder. Import-path
    ownership is inherited: the folders passed in are already owned, and ownership is a path-prefix rule.
    """
    visibility_sql = _browse_visibility_sql("a", include_offline=include_offline)
    readable_sql = _cover_readable_set_sql("a")
    unreadable_cte = _cover_unreadable_cte(library_id)
    rows: list[sqlite3.Row] = []
    for start in range(0, len(folder_paths), _DESCENDANT_COVER_BATCH):
        chunk = folder_paths[start : start + _DESCENDANT_COVER_BATCH]
        values = ", ".join("(?, ?, ?)" for _ in chunk)
        params: list[Any] = []
        for folder_path in chunk:
            params.extend((folder_path, *_descendant_bounds(folder_path)))
        rows.extend(
            conn.execute(
                f"""
                WITH {unreadable_cte}, folders(folder_path, lo, hi) AS (VALUES {values})
                SELECT folder_path, path, mtime_ns, size
                FROM (
                  SELECT f.folder_path, a.path, a.mtime_ns, a.size,
                         row_number() OVER (
                           PARTITION BY f.folder_path ORDER BY a.mtime_ns DESC, a.path ASC
                         ) AS cover_rank
                  FROM folders AS f
                  CROSS JOIN assets AS a ON a.library_id = ? AND a.path >= f.lo AND a.path < f.hi
                  WHERE a.type IN ('image', 'photo')
                    AND {visibility_sql} AND {readable_sql}
                )
                WHERE cover_rank <= {COVER_LIMIT}
                ORDER BY folder_path, cover_rank
                """,
                (*params, library_id),
            )
        )
    return rows


def _browse_folder_counts_conn(
    conn: sqlite3.Connection,
    library_id: int,
    folder_path: str,
    *,
    include_offline: bool,
) -> tuple[bool, int, list[str]]:
    visibility_sql = _browse_visibility_sql("a", include_offline=include_offline)
    direct_child_sql = catalog_direct_child_sql(parent_path_sql=":folder_path", path_sql="a.path")
    import_ownership_sql = catalog_import_path_owns_sql(library_id_sql="a.library_id", path_sql="a.path")
    counts = conn.execute(
        f"""
        SELECT count(*) AS children,
               sum(CASE WHEN a.type IN ('image', 'photo') THEN 1 ELSE 0 END) AS images
        FROM assets AS a
        WHERE a.library_id = :library_id AND a.parent_path = :folder_path
          AND {direct_child_sql} AND {import_ownership_sql} AND {visibility_sql}
        """,
        {"library_id": library_id, "folder_path": folder_path},
    ).fetchone()
    covers = [
        str(row["path"])
        for row in conn.execute(
            f"""
            SELECT a.path FROM assets AS a
            WHERE a.library_id = :library_id AND a.parent_path = :folder_path
              AND a.type IN ('image', 'photo') AND {direct_child_sql}
              AND {import_ownership_sql} AND {visibility_sql} AND {_cover_readable_sql("a")}
            ORDER BY mtime_ns DESC LIMIT {COVER_LIMIT}
            """,
            {"library_id": library_id, "folder_path": folder_path},
        )
    ]
    return bool(counts["children"]), int(counts["images"] or 0), covers


def _owned_canonical_folders(conn: sqlite3.Connection, library_id: int, folder_paths: list[str]) -> set[str]:
    """Return the folders that are canonical, are not the filesystem root and sit inside an import path.

    For such a folder ``P`` the per-row direct-child and import-ownership predicates of its children reduce to
    cheap prefix tests (see ``_direct_child_of_owned_folder_sql``), which is what makes the album aggregates of a
    large search result cheap. Windows keeps the general predicates: its drive and UNC roots need them.
    """
    if os.sep != "/" or not folder_paths:
        return set()
    values = ", ".join("(?)" for _ in folder_paths)
    canonical = catalog_path_is_canonical_sql(path_sql="owned_folders.p")
    ownership = catalog_import_path_owns_sql(library_id_sql=str(int(library_id)), path_sql="owned_folders.p")
    rows = conn.execute(
        f"""
        WITH owned_folders(p) AS (VALUES {values})
        SELECT p FROM owned_folders WHERE p != '/' AND {canonical} AND {ownership}
        """,
        folder_paths,
    ).fetchall()
    return {str(row[0]) for row in rows}


def _direct_child_of_owned_folder_sql(*, path_sql: str, parent_path_sql: str) -> str:
    """Direct-child test for a path whose ``parent_path`` is an owned canonical folder.

    Equivalent to ``catalog_direct_child_sql`` AND ``catalog_import_path_owns_sql`` for such a parent: the path
    must be ``parent/name`` with one non-empty, non-traversal segment (a canonical path then follows from the
    parent being canonical), and ownership is inherited from the parent's import path.
    """
    remainder = f"substr({path_sql}, length({parent_path_sql}) + 2)"
    return (
        f"(substr({path_sql}, 1, length({parent_path_sql}) + 1) = {parent_path_sql} || '/' "
        f"AND instr({remainder}, '/') = 0 AND {remainder} NOT IN ('', '.', '..'))"
    )


_FOLDER_IMAGE_COVER_CHUNK = 100


def _indexed_folder_aggregates(
    conn: sqlite3.Connection,
    library_id: int,
    folder_paths: list[str],
    owned_child_sql: str,
) -> tuple[dict[str, int], list[sqlite3.Row]]:
    """Visible image counts and covers of owned folders from the partial folder-image index (schema v15).

    The count is an index-only scan of the folder's range; the three covers are the first readable rows of that
    range, which the index keeps in cover order (newest first, then path). Both use the visible-image predicate
    the index is built on, so they equal the general ``assets`` scans.
    """
    visible = "a.type IN ('image', 'photo') AND a.offline = 0 AND a.deleted_at IS NULL"
    placeholders = ", ".join("?" for _ in folder_paths)
    image_counts = {
        str(row["parent_path"]): int(row["images"])
        for row in conn.execute(
            f"""
            SELECT a.parent_path, count(*) AS images
            FROM assets AS a INDEXED BY {FOLDER_IMAGE_INDEX_NAME}
            WHERE a.library_id = ? AND a.parent_path IN ({placeholders}) AND {visible} AND {owned_child_sql}
            GROUP BY a.parent_path
            """,
            (library_id, *folder_paths),
        )
    }
    cover_rows: list[sqlite3.Row] = []
    with_images = [path for path in folder_paths if image_counts.get(path)]
    for start in range(0, len(with_images), _FOLDER_IMAGE_COVER_CHUNK):
        chunk = with_images[start : start + _FOLDER_IMAGE_COVER_CHUNK]
        branches = " UNION ALL ".join(
            f"""SELECT * FROM (
                  SELECT a.parent_path AS parent_path, a.path AS path, a.mtime_ns AS mtime_ns, a.size AS size
                  FROM assets AS a INDEXED BY {FOLDER_IMAGE_INDEX_NAME}
                  WHERE a.library_id = ? AND a.parent_path = ? AND {visible} AND {owned_child_sql}
                    AND {_cover_readable_set_sql("a")}
                  ORDER BY a.mtime_ns DESC, a.path ASC
                  LIMIT {COVER_LIMIT}
                )"""
            for _ in chunk
        )
        params: list[Any] = []
        for path in chunk:
            params.extend((library_id, path))
        cover_rows.extend(conn.execute(f"WITH {_cover_unreadable_cte(library_id)} {branches}", params).fetchall())
    return image_counts, cover_rows


def _browse_folder_counts_batch_conn(
    conn: sqlite3.Connection,
    library_id: int,
    folder_paths: list[str],
    *,
    include_offline: bool,
    descendant_covers: bool = False,
) -> dict[str, tuple[bool, int, list[str], list[str]]]:
    if not folder_paths:
        return {}
    visibility_sql = _browse_visibility_sql("a", include_offline=include_offline)
    general_child_sql = (
        f"{catalog_direct_child_sql(parent_path_sql='a.parent_path', path_sql='a.path')} "
        f"AND {catalog_import_path_owns_sql(library_id_sql='a.library_id', path_sql='a.path')}"
    )
    owned_child_sql = _direct_child_of_owned_folder_sql(path_sql="a.path", parent_path_sql="a.parent_path")
    owned_folders = _owned_canonical_folders(conn, library_id, folder_paths)
    owned_paths = [path for path in folder_paths if path in owned_folders]
    counts = dict.fromkeys(folder_paths, (False, 0))
    cover_rows: list[sqlite3.Row] = []
    # Owned canonical folders read the partial folder-image index; a folder it reports no image for still
    # needs the general count (its children may be videos or subfolders), as does any other folder.
    general_paths = [path for path in folder_paths if path not in owned_folders]
    indexed: tuple[dict[str, int], list[sqlite3.Row]] | None = None
    if owned_paths and not include_offline:
        try:
            indexed = _indexed_folder_aggregates(conn, library_id, owned_paths, owned_child_sql)
        except sqlite3.OperationalError:
            indexed = None  # a database whose schema init has not built the index yet: use the general scans
    if indexed is not None:
        image_counts, indexed_covers = indexed
        cover_rows.extend(indexed_covers)
        for path, images in image_counts.items():
            counts[path] = (True, images)
        child_sql_by_paths = [
            (owned_child_sql, [path for path in owned_paths if path not in image_counts]),
            (general_child_sql, general_paths),
        ]
        cover_partitions: list[tuple[str, list[str]]] = [(general_child_sql, general_paths)]
    else:
        child_sql_by_paths = [(owned_child_sql, owned_paths), (general_child_sql, general_paths)]
        cover_partitions = child_sql_by_paths
    for child_sql, paths in child_sql_by_paths:
        if not paths:
            continue
        placeholders = ", ".join("?" for _ in paths)
        count_rows = conn.execute(
            f"""
            SELECT a.parent_path,
                   count(*) AS children,
                   sum(CASE WHEN a.type IN ('image', 'photo') THEN 1 ELSE 0 END) AS images
            FROM assets AS a
            WHERE a.library_id = ? AND a.parent_path IN ({placeholders})
              AND {visibility_sql} AND {child_sql}
            GROUP BY a.parent_path
            """,
            (library_id, *paths),
        ).fetchall()
        for row in count_rows:
            counts[str(row["parent_path"])] = (bool(row["children"]), int(row["images"] or 0))

    for child_sql, paths in cover_partitions:
        if not paths:
            continue
        placeholders = ", ".join("?" for _ in paths)
        cover_rows.extend(
            conn.execute(
                f"""
                WITH {_cover_unreadable_cte(library_id)}
                SELECT parent_path, path, mtime_ns, size
                FROM (
                  SELECT a.parent_path, a.path, a.mtime_ns, a.size,
                         row_number() OVER (PARTITION BY a.parent_path ORDER BY a.mtime_ns DESC, a.path ASC) AS cover_rank
                  FROM assets AS a
                  WHERE a.library_id = ?
                    AND a.parent_path IN ({placeholders})
                    AND a.type IN ('image', 'photo')
                    AND {visibility_sql}
                    AND {child_sql}
                    AND {_cover_readable_set_sql("a")}
                )
                WHERE cover_rank <= {COVER_LIMIT}
                ORDER BY parent_path, cover_rank
                """,
                (library_id, *paths),
            ).fetchall()
        )
    # A folder without direct images (only subfolders) borrows covers from its descendants. A folder whose
    # direct images are all unreadable keeps no covers: it still holds images, so it shows the placeholder.
    # Only folder listings ask for it: ranking a whole tree is a scan of the subtree, which the virtual root
    # (import roots can hold the entire library) and search albums must not pay.
    descendant_rows = (
        _browse_descendant_covers_conn(
            conn,
            library_id,
            [folder_path for folder_path, (_has_children, image_count) in counts.items() if image_count == 0],
            include_offline=include_offline,
        )
        if descendant_covers
        else []
    )
    covers: dict[str, list[str]] = {folder_path: [] for folder_path in folder_paths}
    cover_versions: dict[str, list[str]] = {folder_path: [] for folder_path in folder_paths}
    for parent_key, rows in (("parent_path", cover_rows), ("folder_path", descendant_rows)):
        for row in rows:
            parent = str(row[parent_key])
            covers.setdefault(parent, []).append(str(row["path"]))
            # Aligned with ``covers``: an asset without a recorded identity gets "" (no version to offer).
            cover_versions.setdefault(parent, []).append(content_version(row["mtime_ns"], row["size"]) or "")

    return {
        folder_path: (has_children, image_count, covers.get(folder_path, []), cover_versions.get(folder_path, []))
        for folder_path, (has_children, image_count) in counts.items()
    }


def catalog_folder_aggregates_conn(
    conn: sqlite3.Connection,
    folders: list[tuple[int, str]],
    *,
    include_offline: bool = False,
) -> dict[tuple[int, str], tuple[bool, int, list[str], list[str]]]:
    """Return browse-equivalent direct folder counts, covers and cover versions in bounded batches."""
    grouped: dict[int, list[str]] = {}
    for library_id, folder_path in folders:
        paths = grouped.setdefault(library_id, [])
        if folder_path not in paths:
            paths.append(folder_path)

    aggregates: dict[tuple[int, str], tuple[bool, int, list[str], list[str]]] = {}
    for library_id, folder_paths in grouped.items():
        values = _browse_folder_counts_batch_conn(
            conn,
            library_id,
            folder_paths,
            include_offline=include_offline,
        )
        aggregates.update({(library_id, path): aggregate for path, aggregate in values.items()})
    return aggregates


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
        has_children, image_count, cover_images, cover_versions = folder_counts.get(root_path, (False, 0, [], []))
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
                "cover_versions": cover_versions,
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
    direct_child_sql = catalog_direct_child_sql(parent_path_sql=":scope_path", path_sql="a.path")
    import_ownership_sql = catalog_import_path_owns_sql(library_id_sql="a.library_id", path_sql="a.path")
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
            WHERE a.library_id = :library_id AND a.parent_path = :scope_path
              AND {direct_child_sql} AND {import_ownership_sql}
              AND {visibility_sql}
        )
        WHERE rn = 1
        """,
        {"library_id": int(library["id"]), "scope_path": scope_path},
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
        descendant_covers=True,
    )
    for row in folder_rows:
        has_children, image_count, cover_images, cover_versions = folder_counts.get(
            str(row["path"]), (False, 0, [], [])
        )
        folders.append(
            FileNode(
                name=row["name"],
                path=row["path"],
                type="folder",
                has_children=has_children,
                cover_images=cover_images,
                cover_versions=cover_versions,
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
            content_version=content_version(row["mtime_ns"], row["size"]),
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
            content_version=content_version(row["mtime_ns"], row["size"]),
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
    with _connect_read() as conn:
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
    with _connect_read() as conn:
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
            cover_rows = conn.execute(
                f"""
                SELECT a.path, a.mtime_ns, a.size FROM assets AS a
                WHERE a.library_id = ? AND a.parent_path = ? AND a.type = 'image' AND {_active_asset_where("a")}
                  AND {_cover_readable_sql("a")}
                ORDER BY a.mtime_ns DESC LIMIT {COVER_LIMIT}
                """,
                (library["id"], row["path"]),
            ).fetchall()
            covers = [cover["path"] for cover in cover_rows]
            cover_versions = [content_version(cover["mtime_ns"], cover["size"]) or "" for cover in cover_rows]
            folders.append(
                FileNode(
                    name=row["name"],
                    path=row["path"],
                    type="folder",
                    has_children=bool(counts["children"]),
                    cover_images=covers,
                    cover_versions=cover_versions,
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
                content_version=content_version(row["mtime_ns"], row["size"]),
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
                content_version=content_version(row["mtime_ns"], row["size"]),
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
