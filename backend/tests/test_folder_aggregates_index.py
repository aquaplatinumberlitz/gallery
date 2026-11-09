"""Folder aggregate equivalence and the schema v15 folder-image index (BL-13).

Purpose:
Lock that the cheap folder aggregate paths (owned-folder prefix test, partial folder-image index) return exactly
what the general predicates return, and that the v14-to-v15 migration backs up, builds the index and keeps data.

Guarantees:
* image counts, has-children flags, covers and cover versions equal the general-predicate result for folders
  holding images, only videos, only subfolders, nothing, offline or deleted assets, unreadable images, mtime ties
  and rows whose path is not a direct child of their recorded parent
* folders outside every import path and offline-inclusive aggregates keep the general predicates
* the aggregate queries run on `idx_assets_folder_images`
* the v14-to-v15 migration writes `.v14.bak`, builds the index idempotently and sets user_version 15

Run when:
* changing `browse_store` folder aggregates, `_ensure_folder_image_index`, or the v15 migration
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from backend.metadata_store import _connect, browse_store, initialize_database, register_library
from backend.metadata_store._schema import CATALOG_SCHEMA_VERSION
from backend.metadata_store._schema_ensure import FOLDER_IMAGE_INDEX_NAME

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")

BASE_MTIME_NS = 1_760_000_000_000_000_000


def _insert_asset(
    conn: sqlite3.Connection,
    library_id: int,
    path: Path,
    parent: Path,
    *,
    kind: str = "image",
    mtime_ns: int = BASE_MTIME_NS,
    offline: int = 0,
    deleted: bool = False,
    state: str = "ready",
) -> None:
    conn.execute(
        "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, indexed_at, "
        "metadata_state, offline, deleted_at) VALUES (?, ?, ?, ?, ?, ?, 100, 8, 8, 1.0, ?, ?, ?)",
        (library_id, str(path), str(parent), path.name, kind, mtime_ns, state, offline, 1.0 if deleted else None),
    )


def _build_library(root: Path) -> tuple[int, dict[str, Path]]:
    library_id = int(register_library(root, name="Aggregates")["id"])
    base = root.resolve()
    folders = {
        name: base / name
        for name in (
            "images",
            "videos_only",
            "subfolders_only",
            "empty",
            "mixed",
            "ties",
            "hidden",
            "unreadable",
            "odd",
        )
    }
    with closing(_connect()) as conn:
        for index in range(12):
            _insert_asset(
                conn,
                library_id,
                folders["images"] / f"i{index:02d}.png",
                folders["images"],
                mtime_ns=BASE_MTIME_NS + index * 7,
            )
        _insert_asset(conn, library_id, folders["videos_only"] / "a.mp4", folders["videos_only"], kind="video")
        _insert_asset(conn, library_id, folders["subfolders_only"] / "child", folders["subfolders_only"], kind="folder")
        _insert_asset(conn, library_id, folders["mixed"] / "x.png", folders["mixed"], mtime_ns=BASE_MTIME_NS + 3)
        _insert_asset(conn, library_id, folders["mixed"] / "y.mp4", folders["mixed"], kind="video")
        _insert_asset(conn, library_id, folders["mixed"] / "sub", folders["mixed"], kind="folder")
        for name in ("d.png", "c.png", "b.png", "a.png", "e.png"):  # equal mtimes: covers tie-break on path
            _insert_asset(conn, library_id, folders["ties"] / name, folders["ties"], mtime_ns=BASE_MTIME_NS + 50)
        _insert_asset(conn, library_id, folders["hidden"] / "off.png", folders["hidden"], offline=1)
        _insert_asset(conn, library_id, folders["hidden"] / "gone.png", folders["hidden"], deleted=True)
        _insert_asset(conn, library_id, folders["hidden"] / "ok.png", folders["hidden"], mtime_ns=BASE_MTIME_NS + 9)
        _insert_asset(
            conn,
            library_id,
            folders["unreadable"] / "bad.png",
            folders["unreadable"],
            mtime_ns=BASE_MTIME_NS + 99,
            state="failed",
        )
        _insert_asset(
            conn, library_id, folders["unreadable"] / "good.png", folders["unreadable"], mtime_ns=BASE_MTIME_NS + 1
        )
        # Rows whose path is not a direct child of the recorded parent must not count, exactly as before.
        _insert_asset(conn, library_id, folders["odd"] / "deep" / "nested.png", folders["odd"])
        _insert_asset(conn, library_id, folders["odd"] / "..", folders["odd"])
        _insert_asset(conn, library_id, folders["odd"] / "fine.png", folders["odd"])
        _insert_asset(conn, library_id, base / "elsewhere" / "stray.png", folders["odd"])
        conn.commit()
    return library_id, folders


def _aggregates(library_id: int, folders: list[Path], **kwargs: object) -> dict[tuple[int, str], tuple]:
    with closing(_connect()) as conn:
        return browse_store.catalog_folder_aggregates_conn(
            conn, [(library_id, str(path)) for path in folders], **kwargs
        )  # type: ignore[arg-type]


def test_indexed_and_prefix_aggregates_equal_the_general_predicates(
    isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_id, folders = _build_library(isolated_gallery_root)
    outside = isolated_gallery_root.resolve() / "not_a_folder_in_any_library"
    every = [*folders.values(), outside]
    fast = _aggregates(library_id, every)
    monkeypatch.setattr(browse_store, "_owned_canonical_folders", lambda *_args, **_kwargs: set())
    general = _aggregates(library_id, every)
    assert fast == general
    assert fast[(library_id, str(folders["images"]))][1] == 12
    assert fast[(library_id, str(folders["videos_only"]))][:2] == (True, 0)
    assert fast[(library_id, str(folders["subfolders_only"]))][:2] == (True, 0)
    assert fast[(library_id, str(folders["empty"]))][:2] == (False, 0)
    assert fast[(library_id, str(folders["hidden"]))][1] == 1
    assert [Path(cover).name for cover in fast[(library_id, str(folders["ties"]))][2]] == ["a.png", "b.png", "c.png"]
    assert [Path(cover).name for cover in fast[(library_id, str(folders["unreadable"]))][2]] == ["good.png"]
    assert fast[(library_id, str(folders["odd"]))][1] == 1


def test_offline_inclusive_aggregates_keep_the_general_predicates(
    isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_id, folders = _build_library(isolated_gallery_root)
    every = list(folders.values())
    inclusive = _aggregates(library_id, every, include_offline=True)
    monkeypatch.setattr(browse_store, "_owned_canonical_folders", lambda *_args, **_kwargs: set())
    assert inclusive == _aggregates(library_id, every, include_offline=True)
    assert inclusive[(library_id, str(folders["hidden"]))][1] == 2  # offline included, deleted still hidden


def test_aggregate_queries_use_the_folder_image_index(isolated_gallery_root: Path) -> None:
    library_id, folders = _build_library(isolated_gallery_root)
    statements: list[str] = []
    with closing(_connect()) as conn:
        conn.set_trace_callback(statements.append)
        browse_store.catalog_folder_aggregates_conn(conn, [(library_id, str(folders["images"]))])
    assert any(FOLDER_IMAGE_INDEX_NAME in statement for statement in statements)
    with closing(_connect()) as conn:
        plan = " ".join(
            str(row[3])
            for row in conn.execute(
                f"""EXPLAIN QUERY PLAN SELECT a.parent_path, count(*) FROM assets AS a
                    INDEXED BY {FOLDER_IMAGE_INDEX_NAME}
                    WHERE a.library_id = ? AND a.parent_path IN (?) AND a.type IN ('image', 'photo')
                      AND a.offline = 0 AND a.deleted_at IS NULL GROUP BY a.parent_path""",
                (library_id, str(folders["images"])),
            )
        )
    assert FOLDER_IMAGE_INDEX_NAME in plan


def test_v14_database_migrates_to_v15_with_backup_and_index(
    isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    library_id, folders = _build_library(isolated_gallery_root)
    before = _aggregates(library_id, list(folders.values()))
    with closing(_connect()) as conn:
        conn.execute(f"DROP INDEX {FOLDER_IMAGE_INDEX_NAME}")
        conn.execute("PRAGMA user_version = 14")
        conn.commit()
    from backend.metadata_store import _db

    _db._DB_INITIALIZED = False
    initialize_database()
    after = _aggregates(library_id, list(folders.values()))
    assert after == before
    with closing(sqlite3.connect(isolated_metadata_db)) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == CATALOG_SCHEMA_VERSION == 15
        index_sql = raw.execute("SELECT sql FROM sqlite_master WHERE name = ?", (FOLDER_IMAGE_INDEX_NAME,)).fetchone()
    assert index_sql is not None
    assert "WHERE type IN ('image', 'photo') AND offline = 0 AND deleted_at IS NULL" in " ".join(index_sql[0].split())
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v14.bak").exists()
