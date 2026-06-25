"""Phase 6 regression tests for tolerant mtime_ns identity joins in status queries.

Verifies that the status builder's asset-to-image_metadata and asset-to-metadata_index_jobs
joins use the tolerant identity rule (ABS(mtime_ns difference) < 1000) instead of
exact equality, matching the Phase 3 lifecycle invariant used elsewhere.

See: status_store.py _metadata_counts_for_scope, _batch_metadata_counts,
     _last_index_at_for_scope, _batch_last_index_at,
     _latest_metadata_issue_for_scope, _batch_metadata_issues

Run when:
  Changing metadata freshness joins, ready/not-ready counts, or identity rules.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.metadata_store import _connect, create_library


def _asset_row(
    library_id: int,
    path: Path,
    *,
    parent_path: Path | None = None,
    mtime_ns: int = 1000,
    size: int = 128,
    metadata_state: str = "done",
) -> tuple[Any, ...]:
    resolved = str(path.resolve())
    parent = str((parent_path or path.parent).resolve())
    now = time.time()
    return (
        library_id,
        resolved,
        parent,
        path.name,
        "image",
        mtime_ns,
        size,
        None,
        None,
        now,
        metadata_state,
        0,
        None,
        None,
        None,
        None,
    )


def _insert_assets(*rows: tuple[Any, ...]) -> None:
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              width, height, indexed_at, metadata_state, offline, deleted_at,
              mime_type, duration_ms, codec
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _insert_image_metadata(
    path: Path,
    *,
    mtime_ns: int | None,
    size: int,
    width: int = 640,
    height: int = 480,
) -> None:
    resolved = str(path.resolve())
    now = time.time()
    with _connect() as conn:
        if mtime_ns is not None:
            conn.execute(
                """
                INSERT INTO image_metadata (
                  path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (resolved, path.name, mtime_ns / 1_000_000_000, mtime_ns, size, width, height, now, now),
            )
        else:
            conn.execute(
                """
                INSERT INTO image_metadata (
                  path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (resolved, path.name, 1.0, None, size, width, height, now, now),
            )


def _insert_metadata_job(
    path: Path,
    *,
    mtime_ns: int | None,
    size: int,
    state: str,
    root: Path,
) -> None:
    resolved = str(path.resolve())
    now = time.time()
    with _connect() as conn:
        if mtime_ns is not None:
            conn.execute(
                """
                INSERT OR REPLACE INTO metadata_index_jobs
                  (path, name, parent_path, folder_path, root_path, mtime, mtime_ns, size, state, queued_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved, path.name, str(path.parent), str(path.parent), str(root),
                    mtime_ns / 1_000_000_000, mtime_ns, size, state, now, now,
                ),
            )
        else:
            conn.execute(
                """
                INSERT OR REPLACE INTO metadata_index_jobs
                  (path, name, parent_path, folder_path, root_path, mtime, size, state, queued_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved, path.name, str(path.parent), str(path.parent), str(root),
                    1.0, size, state, now, now,
                ),
            )


def _enable_metadata_status(monkeypatch) -> None:
    import backend.config as config_module

    monkeypatch.setattr(config_module, "METADATA_INDEXER_ENABLED", True)


def _single_scope_metadata(isolated_app: TestClient, library_id: int) -> dict[str, Any]:
    response = isolated_app.get(f"/api/libraries/{library_id}/status")
    assert response.status_code == 200, response.text
    return response.json()["status"]["metadata"]


def _single_scope_status(isolated_app: TestClient, library_id: int) -> dict[str, Any]:
    response = isolated_app.get(f"/api/libraries/{library_id}/status")
    assert response.status_code == 200, response.text
    return response.json()["status"]


def _batch_metadata(isolated_app: TestClient, library_id: int) -> dict[str, Any]:
    response = isolated_app.get("/api/libraries/status")
    assert response.status_code == 200, response.text
    items = {item["library_id"]: item["status"]["metadata"] for item in response.json()["items"]}
    return items[library_id]


def test_tolerant_mtime_ns_join_for_ready_assets(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """ready_assets counts asset when mtime_ns differs by <1000 ns from image_metadata."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=1500, size=100)

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["total_assets"] == 1
    assert single["ready_assets"] == 1, "Should count as ready when mtime_ns differs by 500ns (< 1000)"
    assert batch["total_assets"] == 1
    assert batch["ready_assets"] == 1


def test_tolerant_mtime_ns_join_exact_differ_by_999_ns(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """ready_assets counts asset when mtime_ns differs by 999 ns (boundary just under 1000)."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=0, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=999, size=100)

    single = _single_scope_metadata(isolated_app, library_id)
    assert single["ready_assets"] == 1, "999ns diff should still match (< 1000)"


def test_mtime_ns_difference_of_1000_ns_does_not_match(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """ready_assets excludes asset when mtime_ns differs by exactly 1000 ns (boundary)."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=0, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=1000, size=100)

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["ready_assets"] == 0, "1000ns diff should NOT match (< 1000 is strict)"
    assert batch["ready_assets"] == 0


def test_tolerant_mtime_ns_join_for_queued_job(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """queued_assets counted when metadata_index_jobs matches by tolerant mtime_ns."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="pending"),
    )
    _insert_metadata_job(image, mtime_ns=1500, size=100, state="queued", root=root)

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["queued_assets"] == 1, "Queued job should match via tolerant mtime_ns"
    assert single["total_assets"] == 1
    assert batch["queued_assets"] == 1


def test_tolerant_mtime_ns_join_for_running_job(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """running_assets counted when metadata_index_jobs matches by tolerant mtime_ns."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="pending"),
    )
    _insert_metadata_job(image, mtime_ns=1500, size=100, state="running", root=root)

    single = _single_scope_metadata(isolated_app, library_id)
    assert single["running_assets"] == 1, "Running job should match via tolerant mtime_ns"


def test_tolerant_mtime_ns_join_for_failed_job_with_metadata_issue(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """Failed metadata job matches via tolerant mtime_ns and produces a metadata issue."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="pending"),
    )
    _insert_metadata_job(image, mtime_ns=1500, size=100, state="failed", root=root)

    status = _single_scope_status(isolated_app, library_id)

    assert status["metadata"]["failed_assets"] == 1, "Failed job should match via tolerant mtime_ns"
    assert status["issues"]["metadata"] == 1
    assert status["latest_issue"] is not None
    assert status["latest_issue"]["source"] == "metadata"


def test_legacy_image_metadata_with_null_mtime_ns_matches_asset_mtime_ns(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """image_metadata row with mtime_ns=NULL matches asset mtime_ns via seconds fallback."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1_000_000_000, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=None, size=100)

    single = _single_scope_metadata(isolated_app, library_id)
    batch = _batch_metadata(isolated_app, library_id)

    assert single["ready_assets"] == 1, "Legacy image_metadata (mtime_ns=NULL) should match via seconds"
    assert batch["ready_assets"] == 1


def test_legacy_metadata_job_with_null_mtime_ns_matches_asset_mtime_ns(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """metadata_index_jobs row with mtime_ns=NULL matches asset mtime_ns via seconds fallback."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1_000_000_000, size=100, metadata_state="pending"),
    )
    _insert_metadata_job(image, mtime_ns=None, size=100, state="queued", root=root)

    single = _single_scope_metadata(isolated_app, library_id)
    assert single["queued_assets"] == 1, "Legacy metadata job (mtime_ns=NULL) should match via seconds"


def test_legacy_metadata_job_null_mtime_ns_matches_for_failed_issue(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """Legacy metadata job with mtime_ns=NULL produces issue via seconds fallback."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1_000_000_000, size=100, metadata_state="pending"),
    )
    _insert_metadata_job(image, mtime_ns=None, size=100, state="failed", root=root)

    status = _single_scope_status(isolated_app, library_id)
    assert status["issues"]["metadata"] == 1
    assert status["latest_issue"] is not None
    assert status["latest_issue"]["source"] == "metadata"


def test_batch_tolerant_mtime_ns_join_for_ready(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """Batch endpoint also counts ready_assets with tolerant mtime_ns join."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1000, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=1500, size=100)

    batch = _batch_metadata(isolated_app, library_id)
    assert batch["total_assets"] == 1
    assert batch["ready_assets"] == 1


def test_batch_legacy_null_mtime_ns(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch,
):
    """Batch endpoint matches legacy image_metadata (mtime_ns=NULL) via seconds fallback."""
    _enable_metadata_status(monkeypatch)
    root = isolated_gallery_root / "library"
    root.mkdir()
    library = create_library([root], name="Library")
    library_id = int(library["id"])
    image = root / "asset.png"
    _insert_assets(
        _asset_row(library_id, image, parent_path=root, mtime_ns=1_000_000_000, size=100, metadata_state="done"),
    )
    _insert_image_metadata(image, mtime_ns=None, size=100)

    batch = _batch_metadata(isolated_app, library_id)
    assert batch["ready_assets"] == 1
