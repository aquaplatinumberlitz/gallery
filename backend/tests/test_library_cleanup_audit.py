"""Regression coverage for path-owned metadata and generated cache cleanup."""

from __future__ import annotations

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from backend.metadata_store import _DB_LOCK, _connect, create_library, forget_offline_library_assets, unregister_library
from backend.metadata_store import library_store
from backend.integrity_checker import IntegrityCheckAlreadyRunning, IntegrityChecker
from backend.metadata_store import file_index
from tests.conftest import create_test_png


@pytest.mark.parametrize("operation", ["forget", "unregister"])
def test_library_removal_cleans_every_path_owned_table_and_cache_file(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    root = isolated_gallery_root / operation
    root.mkdir()
    source = root / "gone.png"
    cache_root = isolated_gallery_root / "cache"
    cache_file = cache_root / "files" / f"{operation}.webp"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"generated")
    monkeypatch.setattr(library_store, "THUMBNAIL_CACHE_DIR", cache_root)

    library = create_library([root])
    library_id = int(library["id"])
    now = time.time()
    with _DB_LOCK, _connect() as conn:
        asset_id = conn.execute(
            """INSERT INTO assets
               (library_id, path, parent_path, name, type, mtime_ns, size, indexed_at, offline)
               VALUES (?, ?, ?, 'gone.png', 'image', 123, 7, ?, 1)""",
            (library_id, str(source), str(root), now),
        ).lastrowid
        derivative_id = conn.execute(
            """INSERT INTO asset_derivatives
               (asset_id, kind, variant, source_mtime_ns, source_size, max_long_edge, status, cache_path)
               VALUES (?, 'thumbnail', 'default', 123, 7, 512, 'ready', ?)""",
            (asset_id, str(cache_file)),
        ).lastrowid
        conn.execute("INSERT INTO derivative_jobs (derivative_id, state) VALUES (?, 'done')", (derivative_id,))
        conn.execute(
            """INSERT INTO file_index
               (path, name, parent_path, type, mtime, mtime_ns, size, indexed_at, library_id)
               VALUES (?, 'gone.png', ?, 'image', 0, 123, 7, ?, ?)""",
            (str(source), str(root), now, library_id),
        )
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES ('gone.png', ?, 'image', ?)",
            (str(source), str(root)),
        )
        conn.execute(
            "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size) VALUES (?, 'gone.png', 0, 123, 7)",
            (str(source),),
        )
        conn.execute(
            "INSERT INTO image_resources (path, kind, name, updated_at) VALUES (?, 'lora', 'x', ?)",
            (str(source), now),
        )
        conn.execute(
            """INSERT INTO metadata_index_jobs
               (path, name, parent_path, folder_path, root_path, mtime, mtime_ns, size, state, updated_at)
               VALUES (?, 'gone.png', ?, ?, ?, 0, 123, 7, 'done', ?)""",
            (str(source), str(root), str(root), str(root), now),
        )

    if operation == "forget":
        assert len(forget_offline_library_assets(library_id)) == 1
    else:
        assert unregister_library(library_id) is True

    with _DB_LOCK, _connect() as conn:
        for table in (
            "assets",
            "asset_derivatives",
            "derivative_jobs",
            "file_index",
            "file_index_fts",
            "image_metadata",
            "image_resources",
            "metadata_index_jobs",
        ):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0, table
    assert not cache_file.exists()


def test_nanosecond_identity_columns_use_integer_affinity(isolated_metadata_db: Path) -> None:
    with _DB_LOCK, _connect() as conn:
        assets = {row["name"]: row["type"] for row in conn.execute("PRAGMA table_info(assets)")}
        derivatives = {row["name"]: row["type"] for row in conn.execute("PRAGMA table_info(asset_derivatives)")}
    assert assets["mtime_ns"] == "INTEGER"
    assert derivatives["source_mtime_ns"] == "INTEGER"


def test_directory_scan_uses_one_shared_write_connection(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_library([isolated_gallery_root])
    for index in range(8):
        create_test_png(isolated_gallery_root / f"{index}.png")
    calls = 0
    original_connect = file_index._connect

    def counted_connect(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(file_index, "_connect", counted_connect)
    assert file_index.index_directory_tree(isolated_gallery_root) == 9
    assert calls == 1


def test_integrity_run_lock_rejects_concurrent_start(monkeypatch: pytest.MonkeyPatch) -> None:
    checker = IntegrityChecker()
    entered = threading.Event()
    release = threading.Event()

    def blocked_checks():
        entered.set()
        release.wait(timeout=2)
        return {}

    monkeypatch.setattr(checker, "run_all_checks", blocked_checks)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(checker.run_and_persist)
        assert entered.wait(timeout=1)
        with pytest.raises(IntegrityCheckAlreadyRunning):
            checker.run_and_persist()
        release.set()
        first.result(timeout=2)
