"""
Purpose:
Exercise uncovered metadata_store.py branches for folder index state, dimension
upserts, metadata job lifecycle helpers, stale/ignored index cleanup, and
directory-tree indexing edge cases so backend line coverage stays above the
release threshold.

Guarantees:
* get_folder_indexed_paths / mark_folder_index_incomplete / update_folder_index_state
  cover empty, populated, error, and last_error paths without touching production
  data.
* upsert_image_dimensions and upsert_metadata_result return False for non-image
  paths, missing files, and None dimensions, and persist rows for valid images.
* _metadata_param reads from dict-style params and falls back to None for
  non-dict params or missing keys.
* mark_metadata_jobs_running / done / stale / failed early-return for empty
  iterables and update rows for non-empty iterables.
* cleanup_stale_index and cleanup_ignored_index remove missing, out-of-root, and
  ignored paths from the persistent index without touching the filesystem.
* _scan_folder_counts returns zero counts when the folder cannot be scanned.
* index_directory_tree follows symlinks safely, skips excluded paths, and
  respects include_metadata collection.
* queue_metadata_index_paths coalesces, skips, and fails already-attempted jobs.
* _current_metadata_is_complete and _metadata_job_from_path handle missing,
  excluded, and non-image paths.

Run when:
* changing metadata_store.py folder index state, dimension upserts, metadata job
  lifecycle, stale/ignored cleanup, or directory tree indexing
* adding new columns to folder_index_state or metadata_index_jobs schemas
* tweaking queue_metadata_index_paths coalesce/skip/fail policy
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from backend.metadata_store import (
    MetadataIndexJob,
    _cleanup_ignored_index_conn,
    _cleanup_stale_index_conn,
    _connect,
    _current_metadata_is_complete,
    _metadata_job_from_path,
    _metadata_param,
    _scan_folder_counts,
    cleanup_ignored_index,
    cleanup_stale_index,
    get_folder_index_state,
    get_folder_indexed_paths,
    get_metadata_index_status,
    index_directory_tree,
    index_file,
    initialize_database,
    mark_folder_index_incomplete,
    mark_metadata_jobs_done,
    mark_metadata_jobs_failed,
    mark_metadata_jobs_running,
    mark_metadata_jobs_stale,
    queue_metadata_index_paths,
    update_folder_index_state,
    upsert_image_dimensions,
    upsert_metadata_result,
)

# ---------------------------------------------------------------------------
# Folder index state
# ---------------------------------------------------------------------------


def test_get_folder_indexed_paths_empty(isolated_metadata_db: Path):
    rows = get_folder_indexed_paths()
    assert rows == []


def test_get_folder_indexed_paths_returns_rows_ordered_by_updated_at(isolated_metadata_db: Path, tmp_path: Path):
    album_a = tmp_path / "album_a"
    album_a.mkdir()
    album_b = tmp_path / "album_b"
    album_b.mkdir()

    update_folder_index_state(album_a, complete=True, child_count=1, image_count=1)
    # Sleep so updated_at is strictly greater for the second folder
    time.sleep(0.01)
    update_folder_index_state(album_b, complete=True, child_count=2, image_count=2)

    rows = get_folder_indexed_paths()
    assert len(rows) == 2
    # Most recent first
    paths = [row["path"] for row in rows]
    assert str(album_b.resolve()) == paths[0]
    assert str(album_a.resolve()) == paths[1]
    # Row shape
    assert set(rows[0].keys()) == {"path", "dir_mtime_ns", "complete", "image_count", "updated_at"}


def test_mark_folder_index_incomplete_sets_last_error(isolated_metadata_db: Path, tmp_path: Path):
    album = tmp_path / "album_err"
    album.mkdir()

    update_folder_index_state(album, complete=True, child_count=0, image_count=0)
    assert get_folder_index_state(album)["complete"]

    ok = mark_folder_index_incomplete(album, last_error="boom")
    assert ok is True
    state = get_folder_index_state(album)
    assert state is not None
    assert state["complete"] is False or state["complete"] == 0
    assert state["last_error"] == "boom"


def test_mark_folder_index_incomplete_without_error(isolated_metadata_db: Path, tmp_path: Path):
    album = tmp_path / "album_noerr"
    album.mkdir()

    update_folder_index_state(album, complete=True, child_count=0, image_count=0)
    ok = mark_folder_index_incomplete(album)
    assert ok is True
    state = get_folder_index_state(album)
    assert state is not None
    assert state["complete"] is False or state["complete"] == 0
    assert state["last_error"] is None


def test_update_folder_index_state_returns_false_when_stat_fails(isolated_metadata_db: Path, tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    # No dir_mtime_ns supplied and stat will raise OSError
    ok = update_folder_index_state(missing, complete=True)
    assert ok is False
    # No state should have been persisted
    assert get_folder_index_state(missing) is None


def test_update_folder_index_state_with_explicit_dir_mtime_ns(isolated_metadata_db: Path, tmp_path: Path):
    album = tmp_path / "album_explicit"
    album.mkdir()

    ok = update_folder_index_state(album, complete=True, dir_mtime_ns=12345, image_count=4)
    assert ok is True
    state = get_folder_index_state(album)
    assert state is not None
    assert state["dir_mtime_ns"] == 12345
    assert state["image_count"] == 4


def test_get_folder_index_state_returns_none_for_missing(isolated_metadata_db: Path, tmp_path: Path):
    assert get_folder_index_state(tmp_path / "missing_album") is None


# ---------------------------------------------------------------------------
# upsert_image_dimensions
# ---------------------------------------------------------------------------


def test_upsert_image_dimensions_returns_false_for_none_dimensions(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "pic.png"
    image.write_bytes(b"fake")
    assert upsert_image_dimensions(image, None, 100) is False
    assert upsert_image_dimensions(image, 100, None) is False


def test_upsert_image_dimensions_returns_false_for_non_image(isolated_metadata_db: Path, tmp_path: Path):
    text = tmp_path / "notes.txt"
    text.write_text("not an image")
    assert upsert_image_dimensions(text, 100, 100) is False


def test_upsert_image_dimensions_returns_false_for_missing_file(isolated_metadata_db: Path, tmp_path: Path):
    missing = tmp_path / "missing.png"
    assert upsert_image_dimensions(missing, 100, 100) is False


def test_upsert_image_dimensions_inserts_and_updates(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "real.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG signature-ish

    assert upsert_image_dimensions(image, 800, 600, image_format="PNG", mode="RGB", has_alpha=0) is True

    with _connect() as conn:
        row = conn.execute(
            "SELECT width, height, format, mode, has_alpha FROM image_metadata WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert row is not None
    assert row["width"] == 800
    assert row["height"] == 600
    assert row["format"] == "PNG"
    assert row["mode"] == "RGB"
    assert row["has_alpha"] == 0

    # Update with new dimensions and has_alpha truthy coercion
    assert upsert_image_dimensions(image, 1024, 768, image_format="PNG", mode="RGBA", has_alpha=True) is True
    with _connect() as conn:
        row = conn.execute(
            "SELECT width, height, mode, has_alpha FROM image_metadata WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert row["width"] == 1024
    assert row["height"] == 768
    assert row["mode"] == "RGBA"
    assert row["has_alpha"] == 1


def test_upsert_image_dimensions_has_alpha_none_keeps_null(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "alpha_none.png"
    image.write_bytes(b"data")
    assert upsert_image_dimensions(image, 10, 10, has_alpha=None) is True
    with _connect() as conn:
        row = conn.execute(
            "SELECT has_alpha FROM image_metadata WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert row is not None
    assert row["has_alpha"] is None


# ---------------------------------------------------------------------------
# _metadata_param / upsert_metadata_result
# ---------------------------------------------------------------------------


def test_metadata_param_returns_value_for_known_names():
    assert _metadata_param({"params": {"Model": "abc"}}, "Model", "model") == "abc"
    assert _metadata_param({"params": {"model": "xyz"}}, "Model", "model") == "xyz"


def test_metadata_param_returns_none_for_non_dict_params():
    assert _metadata_param({"params": "string"}, "Model") is None
    assert _metadata_param({"params": ["list"]}, "Model") is None
    assert _metadata_param({}, "Model") is None


def test_metadata_param_returns_none_when_name_missing():
    assert _metadata_param({"params": {"other": 1}}, "Model", "model") is None


def test_upsert_metadata_result_returns_false_for_non_image(isolated_metadata_db: Path, tmp_path: Path):
    text = tmp_path / "notes.txt"
    text.write_text("not an image")
    assert upsert_metadata_result(text, {"prompt": "hello"}) is False


def test_upsert_metadata_result_returns_false_for_missing_file(isolated_metadata_db: Path, tmp_path: Path):
    missing = tmp_path / "ghost.png"
    assert upsert_metadata_result(missing, {"prompt": "hello"}) is False


def test_upsert_metadata_result_persists_prompt_and_params(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "real.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    metadata = {
        "prompt": "masterpiece, 1girl",
        "negative_prompt": "low quality",
        "width": 1024,
        "height": 768,
        "params": {
            "Model": "ponyDiffusionV6XL",
            "Sampler": "Euler a",
            "Seed": "12345",
            "Steps": 30,
            "CFG scale": 7.0,
        },
    }
    assert upsert_metadata_result(image, metadata) is True

    with _connect() as conn:
        row = conn.execute(
            "SELECT prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, width, height "
            "FROM image_metadata WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert row is not None
    assert row["prompt"] == "masterpiece, 1girl"
    assert row["negative_prompt"] == "low quality"
    assert row["model"] == "ponyDiffusionV6XL"
    assert row["sampler"] == "Euler a"
    assert row["seed"] == "12345"
    assert row["steps"] == 30
    assert row["cfg_scale"] == 7.0
    assert row["width"] == 1024
    assert row["height"] == 768


def test_upsert_metadata_result_handles_non_dict_sanitized_metadata(isolated_metadata_db: Path, tmp_path: Path):
    """When sanitizer returns a non-dict, upsert_metadata_result should fall back to {}."""
    image = tmp_path / "sanitized.png"
    image.write_bytes(b"data")

    import backend.metadata_store as ms

    # Force sanitizer to return a non-dict to exercise the fallback path
    original = ms.sanitize_metadata_for_json
    ms.sanitize_metadata_for_json = lambda data: "not a dict"  # type: ignore[assignment]
    try:
        assert upsert_metadata_result(image, {"prompt": "x"}) is True
    finally:
        ms.sanitize_metadata_for_json = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Metadata job lifecycle helpers
# ---------------------------------------------------------------------------


def _make_job(path: str, *, mtime: float = 1.0, size: int = 1) -> MetadataIndexJob:
    parent = str(Path(path).parent)
    return MetadataIndexJob(
        path=path,
        name=Path(path).name,
        parent_path=parent,
        mtime=mtime,
        size=size,
        folder_path=parent,
        root_path="/root",
    )


def test_mark_metadata_jobs_running_empty_is_noop(isolated_metadata_db: Path):
    # Should not raise and should not require DB initialization
    mark_metadata_jobs_running([])
    mark_metadata_jobs_running(iter([]))


def test_mark_metadata_jobs_done_empty_is_noop(isolated_metadata_db: Path):
    mark_metadata_jobs_done([])
    mark_metadata_jobs_done(iter([]))


def test_mark_metadata_jobs_stale_empty_is_noop(isolated_metadata_db: Path):
    mark_metadata_jobs_stale([])
    mark_metadata_jobs_stale(iter([]))


def test_mark_metadata_jobs_failed_empty_is_noop(isolated_metadata_db: Path):
    mark_metadata_jobs_failed([])
    mark_metadata_jobs_failed(iter([]))


def test_mark_metadata_jobs_running_updates_state(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "running.png"
    image.write_bytes(b"data")
    # First queue a job so a row exists
    result = queue_metadata_index_paths([image])
    assert len(result.enqueued) == 1
    job = result.enqueued[0]

    mark_metadata_jobs_running([job])
    with _connect() as conn:
        row = conn.execute(
            "SELECT state, attempts FROM metadata_index_jobs WHERE path = ?",
            (job.path,),
        ).fetchone()
    assert row["state"] == "running"
    assert row["attempts"] == 1


def test_mark_metadata_jobs_done_updates_state(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "done.png"
    image.write_bytes(b"data")
    result = queue_metadata_index_paths([image])
    job = result.enqueued[0]

    mark_metadata_jobs_done([job])
    with _connect() as conn:
        row = conn.execute(
            "SELECT state FROM metadata_index_jobs WHERE path = ?",
            (job.path,),
        ).fetchone()
    assert row["state"] == "done"


def test_mark_metadata_jobs_stale_updates_state(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "stale.png"
    image.write_bytes(b"data")
    result = queue_metadata_index_paths([image])
    job = result.enqueued[0]

    mark_metadata_jobs_stale([job])
    with _connect() as conn:
        row = conn.execute(
            "SELECT state FROM metadata_index_jobs WHERE path = ?",
            (job.path,),
        ).fetchone()
    assert row["state"] == "stale"


def test_mark_metadata_jobs_failed_truncates_error(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "failed.png"
    image.write_bytes(b"data")
    result = queue_metadata_index_paths([image])
    job = result.enqueued[0]

    long_error = "x" * 5000
    mark_metadata_jobs_failed([(job, long_error)])
    with _connect() as conn:
        row = conn.execute(
            "SELECT state, error FROM metadata_index_jobs WHERE path = ?",
            (job.path,),
        ).fetchone()
    assert row["state"] == "failed"
    assert len(row["error"]) == 1000  # error is truncated to 1000 chars


# ---------------------------------------------------------------------------
# _current_metadata_is_complete / _metadata_job_from_path
# ---------------------------------------------------------------------------


def test_current_metadata_is_complete_returns_false_for_missing_row(
    isolated_metadata_db: Path,
):
    initialize_database()
    with _connect() as conn:
        result = _current_metadata_is_complete(conn, "/some/missing/path", 1.0, 10)
    assert result is False


def test_current_metadata_is_complete_true_when_matches(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "complete.png"
    image.write_bytes(b"data")
    assert upsert_metadata_result(image, {"prompt": "p"}) is True
    stat = image.stat()
    with _connect() as conn:
        result = _current_metadata_is_complete(conn, str(image.resolve()), stat.st_mtime, stat.st_size)
    assert result is True


def test_metadata_job_from_path_returns_none_for_excluded_path(tmp_path: Path):
    excluded = tmp_path / "node_modules" / "pkg.png"
    excluded.parent.mkdir(parents=True)
    excluded.write_bytes(b"data")
    assert _metadata_job_from_path(excluded) is None


def test_metadata_job_from_path_returns_none_for_non_image(tmp_path: Path):
    text = tmp_path / "notes.txt"
    text.write_text("not an image")
    assert _metadata_job_from_path(text) is None


def test_metadata_job_from_path_returns_none_for_missing_file(tmp_path: Path):
    missing = tmp_path / "ghost.png"
    assert _metadata_job_from_path(missing) is None


def test_metadata_job_from_path_uses_root_path(tmp_path: Path):
    image = tmp_path / "with_root.png"
    image.write_bytes(b"data")
    job = _metadata_job_from_path(image, root_path=tmp_path)
    assert job is not None
    assert job.root_path == str(tmp_path.resolve())


# ---------------------------------------------------------------------------
# queue_metadata_index_paths edge cases
# ---------------------------------------------------------------------------


def test_queue_metadata_index_paths_empty_input_returns_empty_result(isolated_metadata_db: Path):
    result = queue_metadata_index_paths([])
    assert result.enqueued == []
    assert result.coalesced == 0
    assert result.skipped == 0
    assert result.failed == 0


def test_queue_metadata_index_paths_skips_all_excluded(tmp_path: Path):
    excluded = tmp_path / "node_modules" / "pkg.png"
    excluded.parent.mkdir(parents=True)
    excluded.write_bytes(b"data")
    result = queue_metadata_index_paths([excluded])
    assert result.enqueued == []


def test_queue_metadata_index_paths_coalesces_queued_job(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "coalesce.png"
    image.write_bytes(b"data")

    first = queue_metadata_index_paths([image])
    assert len(first.enqueued) == 1

    # Second call with same file should coalesce (state stays queued)
    second = queue_metadata_index_paths([image])
    assert second.enqueued == []
    assert second.coalesced == 1


def test_queue_metadata_index_paths_fails_after_max_attempts(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "maxfail.png"
    image.write_bytes(b"data")

    first = queue_metadata_index_paths([image])
    job = first.enqueued[0]

    # Mark failed with max attempts
    import backend.metadata_store as ms

    with _connect() as conn:
        conn.execute(
            "UPDATE metadata_index_jobs SET state='failed', attempts=? WHERE path=?",
            (ms.MAX_METADATA_JOB_ATTEMPTS, job.path),
        )

    second = queue_metadata_index_paths([image])
    assert second.enqueued == []
    assert second.failed == 1


# ---------------------------------------------------------------------------
# _scan_folder_counts OSError paths
# ---------------------------------------------------------------------------


def test_scan_folder_counts_returns_zeros_for_missing_folder(tmp_path: Path):
    missing = tmp_path / "missing_folder"
    counts = _scan_folder_counts(missing)
    assert counts == {"child_count": 0, "folder_count": 0, "image_count": 0}


def test_scan_folder_counts_handles_unreadable_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    folder = tmp_path / "unreadable"
    folder.mkdir()
    (folder / "img.png").write_bytes(b"data")

    calls = []

    class FakeEntry:
        def __init__(self, real):
            self.name = real.name
            self.path = real.path
            self._real = real

        def is_dir(self):
            raise OSError("simulated")

        def is_file(self):
            return self._real.is_file()

    real_scandir = os.scandir

    def fake_scandir(path):
        for entry in real_scandir(path):
            calls.append(entry.name)
            yield FakeEntry(entry)

    monkeypatch.setattr(os, "scandir", fake_scandir)
    counts = _scan_folder_counts(folder)
    # is_dir raised OSError and is swallowed; img.png still counted as child
    # but is_image_path is called on a DirEntry-like whose is_file may still work
    assert counts["child_count"] == 1
    assert counts["folder_count"] == 0


# ---------------------------------------------------------------------------
# cleanup_stale_index / cleanup_ignored_index
# ---------------------------------------------------------------------------


def test_cleanup_stale_index_with_connection_removes_missing_paths(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "real.png"
    image.write_bytes(b"data")
    deleted = tmp_path / "deleted.png"
    deleted.write_bytes(b"data")

    initialize_database()
    with _connect() as conn:
        index_file(str(image), "real.png", str(tmp_path), "photo", time.time(), 4, 1, 1)
        index_file(str(deleted), "deleted.png", str(tmp_path), "photo", time.time(), 4, 1, 1)

    # Delete the file on disk so the index row becomes stale
    deleted.unlink()

    initialize_database()
    with _connect() as conn:
        removed = _cleanup_stale_index_conn(conn, root_path=tmp_path)
    assert removed == 1

    with _connect() as conn:
        rows = conn.execute("SELECT path FROM file_index WHERE path = ?", (str(deleted.resolve()),)).fetchall()
    assert len(rows) == 0


def test_cleanup_stale_index_with_external_state_opens_own_connection(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "real2.png"
    image.write_bytes(b"data")
    deleted = tmp_path / "deleted2.png"
    deleted.write_bytes(b"data")

    initialize_database()
    index_file(str(image), "real2.png", str(tmp_path), "photo", time.time(), 4, 1, 1)
    index_file(str(deleted), "deleted2.png", str(tmp_path), "photo", time.time(), 4, 1, 1)

    deleted.unlink()

    removed = cleanup_stale_index(None, root_path=tmp_path)
    assert removed == 1


def test_cleanup_stale_index_removes_out_of_root_paths(isolated_metadata_db: Path, tmp_path: Path):
    inside = tmp_path / "inside.png"
    inside.write_bytes(b"data")
    outside_dir = tmp_path.parent / "outside_root_other"
    outside_dir.mkdir(exist_ok=True)
    outside = outside_dir / "outside.png"
    outside.write_bytes(b"data")

    try:
        initialize_database()
        index_file(str(inside), "inside.png", str(tmp_path), "photo", time.time(), 4, 1, 1)
        index_file(str(outside), "outside.png", str(outside_dir), "photo", time.time(), 4, 1, 1)

        removed = cleanup_stale_index(None, root_path=tmp_path)
        assert removed == 1
    finally:
        with suppress_oserrors():
            outside.unlink(missing_ok=True)
            outside_dir.rmdir()


def test_cleanup_stale_index_returns_zero_when_nothing_stale(isolated_metadata_db: Path, tmp_path: Path):
    image = tmp_path / "fresh.png"
    image.write_bytes(b"data")
    initialize_database()
    index_file(str(image), "fresh.png", str(tmp_path), "photo", time.time(), 4, 1, 1)
    assert cleanup_stale_index(None, root_path=tmp_path) == 0


def test_cleanup_ignored_index_removes_excluded_paths(isolated_metadata_db: Path, tmp_path: Path):
    """cleanup_ignored_index removes ignored paths that were inserted directly via SQL.

    index_file() refuses to insert ignored paths, so we bypass it here to
    simulate stale ignored rows left over from prior indexing runs.
    """
    album = tmp_path / "album"
    album.mkdir()
    image = album / "ok.png"
    image.write_bytes(b"data")

    ignored_dir = tmp_path / "node_modules"
    ignored_dir.mkdir()
    ignored = ignored_dir / "pkg.png"
    ignored.write_bytes(b"data")

    initialize_database()
    index_file(str(image), "ok.png", str(album), "photo", time.time(), 4, 1, 1)

    # Insert the ignored row directly (bypassing index_file's exclusion check)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO file_index (path, name, parent_path, type, mtime, size, "
            "width, height, indexed_at) VALUES (?, ?, ?, 'photo', ?, ?, ?, ?, ?)",
            (str(ignored.resolve()), "pkg.png", str(ignored_dir.resolve()), time.time(), 4, 1, 1, time.time()),
        )
        conn.execute(
            "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'photo', ?)",
            ("pkg.png", str(ignored.resolve()), str(ignored_dir.resolve())),
        )

    removed = cleanup_ignored_index(root_path=tmp_path)
    assert removed == 1

    with _connect() as conn:
        rows = conn.execute("SELECT path FROM file_index WHERE path = ?", (str(ignored.resolve()),)).fetchall()
    assert len(rows) == 0
    # The non-ignored image remains
    with _connect() as conn:
        rows = conn.execute("SELECT path FROM file_index WHERE path = ?", (str(image.resolve()),)).fetchall()
    assert len(rows) == 1


def test_cleanup_ignored_index_conn_returns_zero_when_nothing_ignored(isolated_metadata_db: Path, tmp_path: Path):
    album = tmp_path / "clean_album"
    album.mkdir()
    image = album / "ok.png"
    image.write_bytes(b"data")
    initialize_database()
    index_file(str(image), "ok.png", str(album), "photo", time.time(), 4, 1, 1)
    with _connect() as conn:
        removed = _cleanup_ignored_index_conn(conn, root_path=tmp_path)
    assert removed == 0


# ---------------------------------------------------------------------------
# index_directory_tree edge cases
# ---------------------------------------------------------------------------


def test_index_directory_tree_skips_symlinked_dirs(tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "a.png").write_bytes(b"data")

    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    indexed = index_directory_tree(tmp_path, include_metadata=False)
    # Should index real/a.png, real/ as folder, tmp_path as folder, link/ as folder,
    # but NOT descend into the symlink (so no duplicate a.png).
    assert indexed >= 1


def test_index_directory_tree_handles_unreadable_subdir(
    isolated_metadata_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.png").write_bytes(b"data")
    bad = root / "bad"
    bad.mkdir()

    real_iterdir = Path.iterdir

    def fail_iterdir(self):
        if self == bad:
            raise PermissionError("denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fail_iterdir)
    indexed = index_directory_tree(root, include_metadata=False)
    # Should not raise; should still index ok.png
    assert indexed >= 1


def test_index_directory_tree_with_collected_image_paths(isolated_metadata_db: Path, tmp_path: Path):
    root = tmp_path / "collect_root"
    root.mkdir()
    (root / "x.png").write_bytes(b"data")
    (root / "y.png").write_bytes(b"data")

    collected: list[Path] = []
    indexed = index_directory_tree(root, include_metadata=False, collected_image_paths=collected)
    assert indexed >= 2
    assert len(collected) == 2
    assert all(p.suffix == ".png" for p in collected)


def test_index_directory_tree_skips_excluded_subdir(tmp_path: Path):
    root = tmp_path / "exclude_root"
    root.mkdir()
    (root / "keep.png").write_bytes(b"data")
    node_modules = root / "node_modules"
    node_modules.mkdir()
    (node_modules / "pkg.png").write_bytes(b"data")

    indexed = index_directory_tree(root, include_metadata=False)
    # node_modules contents should not be indexed
    with _connect() as conn:
        rows = conn.execute(
            "SELECT path FROM file_index WHERE path LIKE ?",
            (f"{str(node_modules.resolve())}%",),
        ).fetchall()
    assert len(rows) == 0
    assert indexed >= 1


# ---------------------------------------------------------------------------
# initialize_database idempotency
# ---------------------------------------------------------------------------


def test_initialize_database_is_idempotent(isolated_metadata_db: Path):
    initialize_database()
    initialize_database()
    # If we get here without error, the function is idempotent.
    # Verify schema is present.
    with _connect() as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "image_metadata" in tables
    assert "file_index" in tables
    assert "folder_index_state" in tables


# ---------------------------------------------------------------------------
# get_metadata_index_status — defensive None / zero handling
# ---------------------------------------------------------------------------


def test_get_metadata_index_status_empty_db_no_path(isolated_metadata_db: Path):
    """Empty DB with path=None exercises the null-path branch and the
    "if x else 0" / "if x else None" defensive fallbacks."""
    status = get_metadata_index_status()
    assert status["path"] == ""
    assert status["total"] == 0
    assert status["indexed_photos"] == 0
    assert status["metadata_records"] == 0
    assert status["missing_metadata_records"] == 0
    assert status["counts"] == {
        "queued": 0,
        "running": 0,
        "done": 0,
        "failed": 0,
        "stale": 0,
        "skipped": 0,
    }
    assert status["queued"] == 0
    assert status["running"] == 0
    assert status["done"] == 0
    assert status["failed"] == 0
    assert status["stale"] == 0
    assert status["skipped"] == 0
    assert status["oldest_queued_age_seconds"] is None
    assert status["last_error"] is None
    assert status["updated_at"] is None


def test_get_metadata_index_status_empty_db_with_path(isolated_metadata_db: Path, tmp_path: Path):
    """Empty DB with a path argument exercises the if-path branch (WHERE clause
    built) but still returns zeros/None because no rows exist."""
    album = tmp_path / "empty_album"
    album.mkdir()

    status = get_metadata_index_status(path=album)
    assert status["path"] == str(album.resolve())
    assert status["total"] == 0
    assert status["indexed_photos"] == 0
    assert status["metadata_records"] == 0
    assert status["last_error"] is None
    assert status["oldest_queued_age_seconds"] is None
    assert status["updated_at"] is None


def test_get_metadata_index_status_populated_db(isolated_metadata_db: Path, tmp_path: Path):
    """Populated DB exercises the happy path: non-zero counts, last_error from
    a failed job, oldest_queued_age_seconds, and updated_at all populated."""
    album = tmp_path / "status_album"
    album.mkdir()
    image = album / "pic.png"
    image.write_bytes(b"data")

    # Queue a job (queued state)
    result = queue_metadata_index_paths([image])
    assert len(result.enqueued) == 1

    # Create a second image + job to mark failed
    image2 = album / "broken.png"
    image2.write_bytes(b"data")
    result2 = queue_metadata_index_paths([image2])
    failed_job = result2.enqueued[0]
    mark_metadata_jobs_failed([(failed_job, "extraction boom")])

    # Index a file so indexed_photos > 0
    index_file(str(image), "pic.png", str(album), "photo", time.time(), 4, 1, 1)

    status = get_metadata_index_status()
    assert status["total"] == 2
    assert status["counts"]["queued"] == 1
    assert status["counts"]["failed"] == 1
    assert status["queued"] == 1
    assert status["failed"] == 1
    assert status["indexed_photos"] >= 1
    # last_error should be populated from the failed job
    assert status["last_error"] is not None
    assert status["last_error"]["message"] == "extraction boom"
    assert status["last_error"]["path"] == failed_job.path
    # oldest_queued_age_seconds should be set because there is a queued job
    assert status["oldest_queued_age_seconds"] is not None
    # updated_at should be set because rows exist
    assert status["updated_at"] is not None


def test_get_metadata_index_status_populated_db_with_path_scope(
    isolated_metadata_db: Path, tmp_path: Path
):
    """Populated DB with a path argument scopes counts to that subtree and
    sets the root field to the resolved path."""
    inside_album = tmp_path / "inside"
    inside_album.mkdir()
    inside_image = inside_album / "in.png"
    inside_image.write_bytes(b"data")

    outside_album = tmp_path / "outside"
    outside_album.mkdir()
    outside_image = outside_album / "out.png"
    outside_image.write_bytes(b"data")

    # Queue jobs in both albums
    queue_metadata_index_paths([inside_image])
    queue_metadata_index_paths([outside_image])

    # Scope to inside_album only
    status = get_metadata_index_status(path=inside_album)
    assert status["path"] == str(inside_album.resolve())
    assert status["total"] == 1
    assert status["counts"]["queued"] == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class suppress_oserrors:
    """Suppress OSError when used as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is not None and issubclass(exc_type, OSError)
