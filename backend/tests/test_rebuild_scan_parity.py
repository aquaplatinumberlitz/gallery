"""
Purpose:
Verifies that a catalog rebuild produces the same file_index and assets rows as a scan of the same tree.

Guarantees:
* a rebuilt catalog serves filename search (200, correct order) and keeps file_index.mtime populated
* a rebuilt video row carries the same width, height, duration_ms and codec as a scanned one
* scan and rebuild rows are equal for an image, a video, a folder and a nested file, apart from the
  documented timestamp, job-id and rowid columns

Run when:
* changing catalog record building, scan persistence, rebuild staging or activation, or the file_index/assets schema
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.metadata_store import create_library, index_directory_tree
from backend.metadata_store.job_store import claim_next_catalog_job
from backend.scan_worker import execute_rebuild_job, queue_rebuild
from backend.tests.conftest import create_test_png

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
_needs_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe required")

# Columns that legitimately differ between a scan and a rebuild of the same tree.
#   indexed_at              wall-clock time of the write
#   last_seen_scan_job_id   the rebuild stamps its catalog job id; a scan does not record one
#   id                      assets autoincrement rowid (insertion order, not content)
_EXCLUDED_COLUMNS = {"indexed_at", "last_seen_scan_job_id", "id"}


def _rebuild(library_id: int) -> None:
    queue_rebuild(library_id)
    claimed = claim_next_catalog_job(max_queue_wait_seconds=1)
    assert claimed is not None
    assert execute_rebuild_job(claimed)


def _rows(db: Path, sql: str) -> list[dict]:
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql)]


def _make_video(path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "quiet", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=64x48:rate=10", str(path)],
        check=True,
    )


def _clear_catalog(db: Path) -> None:
    # What the admin "Rebuild" does first: empty the catalog tables.
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM assets")
        conn.execute("DELETE FROM file_index")
        conn.execute("DELETE FROM file_index_fts")


def _snapshot(db: Path) -> tuple[list[dict], list[dict]]:
    def strip(rows: list[dict]) -> list[dict]:
        return [{k: v for k, v in row.items() if k not in _EXCLUDED_COLUMNS} for row in rows]

    return (
        strip(_rows(db, "SELECT * FROM file_index ORDER BY path")),
        strip(_rows(db, "SELECT * FROM assets ORDER BY path")),
    )


def _search_names(library_id: int) -> list[str]:
    from backend.app import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "findme",
            "scope": {"kind": "library", "library_id": library_id},
        },
    )
    assert resp.status_code == 200, resp.text
    media = resp.json()["media"]
    assert all(isinstance(item["mtime"], float) for item in media)
    return [item["name"] for item in media]


def test_cp01_search_after_rebuild_returns_200_in_scan_order(isolated_metadata_db, isolated_gallery_root):
    root = isolated_gallery_root / "lib"
    root.mkdir()
    for index, name in enumerate(["findme_old.png", "findme_new.png", "findme_mid.png"]):
        create_test_png(root / name)
        os.utime(root / name, (1_700_000_000 + index * 1000, 1_700_000_000 + index * 1000))
    create_test_png(root / "other.png")
    library_id = int(create_library([root], name="L")["id"])

    index_directory_tree(root, include_metadata=False)
    scanned_order = _search_names(library_id)
    assert sorted(scanned_order) == ["findme_mid.png", "findme_new.png", "findme_old.png"]

    _clear_catalog(isolated_metadata_db)
    _rebuild(library_id)
    assert _search_names(library_id) == scanned_order


def test_cp01_rebuild_populates_file_index_mtime(isolated_metadata_db, isolated_gallery_root):
    root = isolated_gallery_root / "lib"
    root.mkdir()
    create_test_png(root / "a.png")
    library_id = int(create_library([root], name="L")["id"])
    _rebuild(library_id)
    rows = _rows(isolated_metadata_db, "SELECT type, mtime, mtime_ns FROM file_index")
    assert {row["type"] for row in rows} == {"folder", "image"}
    assert all(row["mtime"] is not None for row in rows), rows
    assert all(abs(row["mtime"] - row["mtime_ns"] / 1e9) < 1e-3 for row in rows)


@_needs_ffmpeg
def test_cp02_rebuild_matches_scan_for_video_fields(isolated_metadata_db, isolated_gallery_root):
    root = isolated_gallery_root / "lib"
    root.mkdir()
    _make_video(root / "clip.mp4")
    library_id = int(create_library([root], name="L")["id"])

    index_directory_tree(root, include_metadata=False)
    sql = "SELECT width, height, duration_ms, codec FROM assets WHERE type='video'"
    scanned = _rows(isolated_metadata_db, sql)[0]
    assert scanned["duration_ms"] is not None and scanned["codec"] is not None

    _clear_catalog(isolated_metadata_db)
    _rebuild(library_id)
    assert _rows(isolated_metadata_db, sql)[0] == scanned
    indexed = _rows(isolated_metadata_db, "SELECT width, height FROM file_index WHERE type='video'")[0]
    assert (indexed["width"], indexed["height"]) == (scanned["width"], scanned["height"])


def test_rebuild_rows_equal_scan_rows(isolated_metadata_db, isolated_gallery_root):
    root = isolated_gallery_root / "lib"
    (root / "album" / "deep").mkdir(parents=True)
    create_test_png(root / "top.png")
    create_test_png(root / "album" / "deep" / "nested.png")
    if _HAS_FFMPEG:
        _make_video(root / "clip.mp4")
    library_id = int(create_library([root], name="L")["id"])

    index_directory_tree(root, include_metadata=False)
    scanned = _snapshot(isolated_metadata_db)
    assert {row["type"] for row in scanned[1]} >= {"folder", "image"}
    if _HAS_FFMPEG:
        assert any(row["type"] == "video" and row["duration_ms"] for row in scanned[1])

    _clear_catalog(isolated_metadata_db)
    _rebuild(library_id)
    rebuilt = _snapshot(isolated_metadata_db)

    assert rebuilt[0] == scanned[0]
    assert rebuilt[1] == scanned[1]
