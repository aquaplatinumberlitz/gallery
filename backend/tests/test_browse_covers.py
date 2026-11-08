"""MD-01 / UX-3 regression: album covers skip unreadable files and fall back to descendants.

Purpose:
Pin the folder cover rules of `/api/browse` (`cover_images` / `cover_versions`) described in
``ARCHITECTURE.md`` (Browse covers): a cover is a readable image, and a folder without direct images borrows
its covers from its descendants.

Guarantees:
* an asset whose metadata job failed (``metadata_state = 'failed'`` or a ``failed`` job for the current
  identity) or whose thumbnail derivative terminally failed with ``invalid_source`` is never a cover;
* a folder whose direct images are all unreadable has no covers (the placeholder), never descendant covers;
* a folder with no direct images gets up to 3 covers from its descendants, readable only, ordered
  ``mtime_ns DESC, path ASC`` like direct covers, with ``cover_versions`` aligned index-for-index;
* covers stay bounded (3) and deterministic, and one browse page runs a fixed number of cover queries.

Run when:
Changing the cover query in ``backend/metadata_store/browse_store.py``, the metadata failure path, or the
derivative ``invalid_source`` outcome.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from backend.indexer import MetadataLifecycleWorker
from backend.metadata_store import (
    _connect_read,
    _persist_metadata_index_jobs,
    create_library,
    index_directory_tree,
)
from backend.metadata_store.browse_store import _browse_folder_counts_batch_conn
from tests.conftest import create_test_png

BASE_NS = 1_700_000_000_000_000_000
STEP_NS = 1_000_000_000


def _png(path: Path, rank: int) -> Path:
    """A readable PNG whose mtime ranks it: higher ``rank`` is newer."""
    create_test_png(path, size=(24, 24))
    stamp = BASE_NS + rank * STEP_NS
    os.utime(path, ns=(stamp, stamp))
    return path


def _garbage(path: Path, rank: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not an image")
    stamp = BASE_NS + rank * STEP_NS
    os.utime(path, ns=(stamp, stamp))
    return path


def _index(root: Path) -> int:
    library_id = int(create_library([root], name="covers")["id"])
    index_directory_tree(root)
    return library_id


def _run_metadata_jobs(root: Path, paths: list[Path]) -> None:
    assert _persist_metadata_index_jobs([p.resolve() for p in paths], root).enqueued
    worker = MetadataLifecycleWorker(worker_count=1, lease_seconds=30, write_retry_delays=())
    while (job := worker._claim_job()) is not None:
        worker._run_job(job)


def _folders(client: TestClient, library_id: int, path: Path) -> dict[str, dict]:
    response = client.get("/api/browse", params={"library_id": library_id, "path": str(path)})
    assert response.status_code == 200, response.text
    return {folder["name"]: folder for folder in response.json()["folders"]}


def _names(folder: dict) -> list[str]:
    return [Path(cover).name for cover in folder["cover_images"]]


def _identity(db_path: Path, path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        mtime_ns, size = conn.execute(
            "SELECT mtime_ns, size FROM assets WHERE path = ?", (str(path.resolve()),)
        ).fetchone()
    return f"{mtime_ns}-{size}"


def _fail_thumbnails_invalid_source(db_path: Path, path: Path) -> None:
    """Seed the terminal derivative outcome the scheduler records for an undecodable source."""
    with sqlite3.connect(db_path) as conn:
        asset_id, mtime_ns, size = conn.execute(
            "SELECT id, mtime_ns, size FROM assets WHERE path = ?", (str(path.resolve()),)
        ).fetchone()
        derivative_id = conn.execute(
            "INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, "
            "max_long_edge, status, last_error) VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 512, 'failed', 'bad')",
            (asset_id, mtime_ns, size),
        ).lastrowid
        conn.execute(
            "INSERT INTO derivative_jobs (derivative_id, state, result_code) VALUES (?, 'failed', 'invalid_source')",
            (derivative_id,),
        )


def test_failed_metadata_assets_are_never_covers(
    isolated_app: TestClient, isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    album = isolated_gallery_root / "Landscapes"
    good = [_png(album / f"good_{i}.png", i) for i in range(3)]
    bad = [_garbage(album / "garbage.png", 50), _garbage(album / "truncated.png", 40)]
    library_id = _index(isolated_gallery_root)

    # Before any worker ran there is no failure signal: the newest files lead.
    assert _names(_folders(isolated_app, library_id, isolated_gallery_root)["Landscapes"])[:2] == [
        "garbage.png",
        "truncated.png",
    ]

    _run_metadata_jobs(isolated_gallery_root, [*good, *bad])

    landscapes = _folders(isolated_app, library_id, isolated_gallery_root)["Landscapes"]
    assert _names(landscapes) == ["good_2.png", "good_1.png", "good_0.png"]
    assert landscapes["image_count"] == 5, "image_count still counts every image"
    assert landscapes["cover_versions"] == [_identity(isolated_metadata_db, p) for p in reversed(good)]


def test_metadata_state_failed_flag_excludes_cover(
    isolated_app: TestClient, isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    album = isolated_gallery_root / "A"
    _png(album / "ok.png", 1)
    flagged = _png(album / "flagged.png", 2)
    library_id = _index(isolated_gallery_root)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE assets SET metadata_state = 'failed' WHERE path = ?", (str(flagged.resolve()),))

    assert _names(_folders(isolated_app, library_id, isolated_gallery_root)["A"]) == ["ok.png"]


def test_invalid_source_derivative_is_never_a_cover(
    isolated_app: TestClient, isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    album = isolated_gallery_root / "A"
    _png(album / "ok.png", 1)
    broken = _png(album / "decode_fails.png", 2)
    library_id = _index(isolated_gallery_root)
    _fail_thumbnails_invalid_source(isolated_metadata_db, broken)

    assert _names(_folders(isolated_app, library_id, isolated_gallery_root)["A"]) == ["ok.png"]


def test_transient_derivative_failure_does_not_hide_cover(
    isolated_app: TestClient, isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    """Only the terminal ``invalid_source`` outcome hides a cover; an exhausted retry may recover."""
    album = isolated_gallery_root / "A"
    flaky = _png(album / "flaky.png", 2)
    library_id = _index(isolated_gallery_root)
    _fail_thumbnails_invalid_source(isolated_metadata_db, flaky)
    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute("UPDATE derivative_jobs SET result_code = 'attempts_exhausted'")

    assert _names(_folders(isolated_app, library_id, isolated_gallery_root)["A"]) == ["flaky.png"]


def test_replaced_file_is_a_cover_again(
    isolated_app: TestClient, isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    """A failure belongs to one identity: a fixed file (new mtime/size) is not hidden by the old failure."""
    album = isolated_gallery_root / "A"
    path = _garbage(album / "later_fixed.png", 5)
    library_id = _index(isolated_gallery_root)
    _run_metadata_jobs(isolated_gallery_root, [path])
    assert _names(_folders(isolated_app, library_id, isolated_gallery_root)["A"]) == []

    _png(path, 9)
    index_directory_tree(isolated_gallery_root)
    assert _names(_folders(isolated_app, library_id, isolated_gallery_root)["A"]) == ["later_fixed.png"]


def test_folder_with_only_unreadable_images_has_no_covers(
    isolated_app: TestClient, isolated_gallery_root: Path
) -> None:
    only_bad = [_garbage(isolated_gallery_root / "Bad" / f"bad_{i}.png", i) for i in range(2)]
    # Descendants must not rescue a folder that has direct (unreadable) images.
    nested = _png(isolated_gallery_root / "Bad" / "sub" / "fine.png", 9)
    library_id = _index(isolated_gallery_root)
    _run_metadata_jobs(isolated_gallery_root, [*only_bad, nested])

    bad = _folders(isolated_app, library_id, isolated_gallery_root)["Bad"]
    assert bad["cover_images"] == []
    assert bad["cover_versions"] == []
    assert bad["image_count"] == 2


def test_subfolder_only_folder_gets_descendant_covers_with_aligned_versions(
    isolated_app: TestClient, isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    root = isolated_gallery_root / "Portraits"
    oct_ = [_png(root / "2026-10" / f"o{i}.png", 10 + i) for i in range(3)]  # newest
    sep = [_png(root / "2026-09" / f"s{i}.png", i) for i in range(3)]
    deep = _png(root / "2026-10" / "deeper" / "d.png", 20)  # newest of all, two levels down
    library_id = _index(isolated_gallery_root)

    portraits = _folders(isolated_app, library_id, isolated_gallery_root)["Portraits"]
    assert portraits["image_count"] == 0
    assert portraits["has_children"] is True
    assert [Path(c) for c in portraits["cover_images"]] == [deep.resolve(), oct_[2].resolve(), oct_[1].resolve()]
    assert portraits["cover_versions"] == [_identity(isolated_metadata_db, p) for p in (deep, oct_[2], oct_[1])]
    assert sep, "older siblings exist but lose to the 3 newest"


def test_descendant_covers_skip_unreadable_and_tie_break_by_path(
    isolated_app: TestClient, isolated_gallery_root: Path
) -> None:
    root = isolated_gallery_root / "Sketches"
    bad = _garbage(root / "rough" / "aaa_bad.png", 7)
    same_a = _png(root / "rough" / "b.png", 5)
    same_b = _png(root / "rough" / "a.png", 5)
    same_c = _png(root / "rough" / "z" / "c.png", 5)
    older = _png(root / "rough" / "old.png", 1)
    library_id = _index(isolated_gallery_root)
    _run_metadata_jobs(isolated_gallery_root, [bad, same_a, same_b, same_c, older])

    first = _folders(isolated_app, library_id, isolated_gallery_root)["Sketches"]
    assert [Path(c) for c in first["cover_images"]] == [same_b.resolve(), same_a.resolve(), same_c.resolve()]
    for _ in range(3):
        assert _folders(isolated_app, library_id, isolated_gallery_root)["Sketches"] == first


def test_descendant_covers_do_not_leak_across_siblings_or_to_folders_with_direct_images(
    isolated_app: TestClient, isolated_gallery_root: Path
) -> None:
    mine = _png(isolated_gallery_root / "Mine" / "sub" / "m.png", 1)
    # "Mine2" shares the "Mine" prefix and must not be mistaken for a descendant of it.
    other = _png(isolated_gallery_root / "Mine2" / "sub" / "x.png", 99)
    direct = _png(isolated_gallery_root / "Direct" / "d.png", 2)
    _png(isolated_gallery_root / "Direct" / "sub" / "newer.png", 50)
    library_id = _index(isolated_gallery_root)

    folders = _folders(isolated_app, library_id, isolated_gallery_root)
    assert [Path(c) for c in folders["Mine"]["cover_images"]] == [mine.resolve()]
    assert [Path(c) for c in folders["Mine2"]["cover_images"]] == [other.resolve()]
    assert [Path(c) for c in folders["Direct"]["cover_images"]] == [direct.resolve()]


def test_empty_folder_has_no_covers(isolated_app: TestClient, isolated_gallery_root: Path) -> None:
    (isolated_gallery_root / "Empty album").mkdir()
    _png(isolated_gallery_root / "x" / "x.png", 1)
    library_id = _index(isolated_gallery_root)

    empty = _folders(isolated_app, library_id, isolated_gallery_root)["Empty album"]
    assert empty["cover_images"] == [] and empty["cover_versions"] == []


def test_cover_queries_do_not_grow_with_folder_count(isolated_app: TestClient, isolated_gallery_root: Path) -> None:
    """No N+1: the number of statements for one page is the same for 2 and for 25 subfolder-only folders."""
    for index in range(25):
        _png(isolated_gallery_root / f"f{index:02d}" / "sub" / "i.png", index)
    library_id = _index(isolated_gallery_root)
    paths = [str((isolated_gallery_root / f"f{index:02d}").resolve()) for index in range(25)]

    def statements(folder_paths: list[str]) -> int:
        seen: list[str] = []
        with _connect_read() as conn:
            conn.set_trace_callback(seen.append)
            result = _browse_folder_counts_batch_conn(
                conn, library_id, folder_paths, include_offline=False, descendant_covers=True
            )
            conn.set_trace_callback(None)
        assert all(len(result[path][2]) == 1 for path in folder_paths)
        return len(seen)

    assert statements(paths[:2]) == statements(paths)
    assert statements(paths) <= 4
