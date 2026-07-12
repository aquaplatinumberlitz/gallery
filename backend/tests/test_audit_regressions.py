"""Regression tests for backend audit findings.

Purpose:
Lock down file identity, case-sensitive scopes, sidecar freshness, disabled
metadata indexing, and refresh thread lifecycle.

Guarantees:
Replaced media cannot expose stale metadata, Linux case-colliding folders stay
isolated, sidecar edits invalidate caches, disabled indexing does not queue
work, and refresh restarts do not leak threads.

Run when:
Changing catalog scans, metadata identity/cache logic, path scopes, indexer
configuration, or scheduled refresh lifecycle.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from backend import indexer, refresh
from backend.metadata_parse import parse_metadata
from backend.metadata_store import (
    _connect,
    get_library_inspector_metadata,
    index_directory_tree,
    reconcile_library_assets,
    register_library,
    search_metadata,
    upsert_metadata_result,
)
from tests.conftest import create_test_png


def test_same_path_replacement_resets_asset_and_hides_stale_metadata(
    isolated_metadata_db: Path,
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    root.mkdir()
    image = root / "replace.png"
    create_test_png(image, size=(40, 30))
    register_library(root)
    index_directory_tree(root, include_metadata=False)
    assert upsert_metadata_result(image, {"prompt": "old audit prompt", "width": 40, "height": 30})
    assert search_metadata("old audit prompt")["total"] == 1

    original_ns = image.stat().st_mtime_ns
    create_test_png(image, size=(90, 20))
    os.utime(image, ns=(original_ns + 1_000_000, original_ns + 1_000_000))
    index_directory_tree(root, include_metadata=False)

    with _connect() as conn:
        asset = conn.execute(
            "SELECT metadata_state, width, height FROM assets WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert dict(asset) == {"metadata_state": "pending", "width": None, "height": None}
    assert search_metadata("old audit prompt")["total"] == 0
    assert get_library_inspector_metadata(image) is None


def test_case_colliding_scope_does_not_offline_sibling_library_assets(
    isolated_metadata_db: Path,
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    upper = root / "Album"
    lower = root / "album"
    upper.mkdir(parents=True)
    lower.mkdir()
    create_test_png(upper / "upper.png")
    create_test_png(lower / "lower.png")
    library = register_library(root)
    index_directory_tree(root, include_metadata=False)

    assert reconcile_library_assets(int(library["id"]), [], scope_path=upper) == 2

    with _connect() as conn:
        rows = {
            Path(row["path"]).name: int(row["offline"])
            for row in conn.execute("SELECT path, offline FROM assets WHERE type = 'image'")
        }
    assert rows == {"upper.png": 1, "lower.png": 0}


def test_sidecar_edit_invalidates_memory_and_database_metadata_cache(
    isolated_metadata_db: Path,
    tmp_path: Path,
) -> None:
    image = tmp_path / "sidecar.png"
    sidecar = tmp_path / "sidecar.txt"
    create_test_png(image)
    sidecar.write_text("first prompt\nSteps: 10, Sampler: Euler, Seed: 1", encoding="utf-8")
    assert parse_metadata(image)["prompt"] == "first prompt"

    previous_ns = sidecar.stat().st_mtime_ns
    sidecar.write_text("second prompt\nSteps: 11, Sampler: Euler, Seed: 2", encoding="utf-8")
    os.utime(sidecar, ns=(previous_ns + 1_000_000, previous_ns + 1_000_000))

    assert parse_metadata(image)["prompt"] == "second prompt"


def test_disabled_metadata_indexer_does_not_persist_jobs(
    isolated_metadata_db: Path,
    tmp_path: Path,
    monkeypatch,
) -> None:
    image = tmp_path / "disabled.png"
    create_test_png(image)
    monkeypatch.setattr(indexer, "METADATA_INDEXER_ENABLED", False)

    result = indexer.dispatch_metadata_index_paths([image], tmp_path)

    assert result == {"queued": 0, "coalesced": 0, "skipped": 1, "failed": 0}
    with _connect() as conn:
        assert conn.execute("SELECT count(*) FROM metadata_index_jobs").fetchone()[0] == 0


def test_refresh_restarts_do_not_leave_old_threads_alive(monkeypatch) -> None:
    monkeypatch.setattr(refresh, "ENABLE_SCHEDULED_REFRESH", True)
    monkeypatch.setattr(refresh, "SCHEDULED_REFRESH_INTERVAL_SECONDS", 60)
    refresh.stop_refresh()

    for _ in range(5):
        refresh.start_refresh()
        assert refresh.stop_refresh(join_timeout=1.0)

    assert not [thread for thread in threading.enumerate() if thread.name == "gallery-scheduled-refresh"]
    time.sleep(0.01)
