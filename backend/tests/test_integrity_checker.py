"""
Purpose:
Regression and contract tests for the IntegrityChecker cross-table consistency
checks. Verifies that integrity violations are detected and repaired correctly
for all six check types.

Guarantees:
* Asset with done metadata_state but missing/stale image_metadata is demoted and requeued.
* Done metadata job with current image_metadata but pending asset stamps asset done.
* Queued/running metadata job with no asset row is failed.
* Ready derivative with missing cache_path or file is requeued and derivative_jobs row created.
* Done derivative job with non-ready catalog status is reconciled (ready or failed).
* Queued/running metadata job with missing file is failed.
* Start/stop lifecycle is idempotent and thread-safe.

Run when:
* Changing integrity_checker.py check logic or derivative job scheduling.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

import pytest

from backend.integrity_checker import IntegrityChecker, integrity_checker
from backend.metadata_store import (
    _DB_LOCK,
    _connect,
    create_library,
    initialize_database,
)
from tests.conftest import create_test_image


@pytest.fixture(autouse=True)
def _init_db(isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch):
    initialize_database()


@pytest.fixture
def _checker() -> IntegrityChecker:
    return IntegrityChecker(interval=3600)


def _asset_row(
    conn: sqlite3.Connection, path: str, library_id: int, mtime_ns: int, size: int, metadata_state: str = "pending"
):
    now = time.time()
    conn.execute(
        """INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
           metadata_state, offline, deleted_at, indexed_at)
           VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 0, NULL, ?)""",
        (library_id, path, str(Path(path).parent), Path(path).name, mtime_ns, size, metadata_state, now),
    )


def _image_metadata_row(conn: sqlite3.Connection, path: str, mtime_ns: int, size: int):
    now = time.time()
    conn.execute(
        """INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at)
           VALUES (?, ?, ?, ?, ?, 64, 64, '{}', ?, ?)""",
        (path, Path(path).name, mtime_ns / 1e9, mtime_ns, size, now, now),
    )


def _metadata_job_row(
    conn: sqlite3.Connection, path: str, state: str = "queued", mtime_ns: int | None = None, size: int = 0
):
    now = time.time()
    conn.execute(
        """INSERT INTO metadata_index_jobs (path, name, parent_path, folder_path, root_path,
           mtime, mtime_ns, size, state, attempts, error, queued_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
           ON CONFLICT(path) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at""",
        (
            path,
            Path(path).name,
            str(Path(path).parent),
            str(Path(path).parent),
            "",
            (mtime_ns or 0) / 1e9,
            mtime_ns,
            size,
            state,
            now,
            now,
        ),
    )


# ---------------------------------------------------------------------------
# Test 1: Asset done with no/stale image_metadata
# ---------------------------------------------------------------------------


class TestAssetDoneNoMetadata:
    def test_asset_done_demoted_when_image_metadata_missing(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size, metadata_state="done")
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_asset_done_no_metadata(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (path,)).fetchone()
            assert row["metadata_state"] == "pending"
            job = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (path,)).fetchone()
            assert job is not None and job["state"] == "queued"

    def test_asset_done_not_demoted_when_image_metadata_current(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size, metadata_state="done")
            _image_metadata_row(conn, path, mtime_ns, size)
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_asset_done_no_metadata(conn)
        assert count == 0

    def test_asset_done_demoted_when_image_metadata_stale(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        old_mtime_ns = int(time.time() * 1e9) - 1_000_000_000
        new_mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, new_mtime_ns, size, metadata_state="done")
            _image_metadata_row(conn, path, old_mtime_ns, size)
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_asset_done_no_metadata(conn)
        assert count == 1


# ---------------------------------------------------------------------------
# Test 2: Job done + metadata current + asset pending
# ---------------------------------------------------------------------------


class TestJobDoneAssetNotDone:
    def test_asset_stamped_done_when_job_done_and_metadata_current(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size, metadata_state="pending")
            _image_metadata_row(conn, path, mtime_ns, size)
            _metadata_job_row(conn, path, state="done", mtime_ns=mtime_ns, size=size)
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_job_done_asset_not_done(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (path,)).fetchone()
            assert row["metadata_state"] == "done"

    def test_asset_unchanged_when_metadata_missing(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size, metadata_state="pending")
            _metadata_job_row(conn, path, state="done", mtime_ns=mtime_ns, size=size)
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_job_done_asset_not_done(conn)
        assert count == 0


# ---------------------------------------------------------------------------
# Test 3: Queued job with no asset row
# ---------------------------------------------------------------------------


class TestJobActiveNoAsset:
    def test_queued_job_failed_when_asset_missing(self, _checker, tmp_path: Path):
        path = str(tmp_path / "orphan.png")
        with _DB_LOCK, _connect() as conn:
            _metadata_job_row(conn, path, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_job_active_no_asset(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (path,)).fetchone()
            assert row["state"] == "failed"

    def test_queued_job_unchanged_when_asset_exists(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            _metadata_job_row(conn, path, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_job_active_no_asset(conn)
        assert count == 0


# ---------------------------------------------------------------------------
# Test 4: Derivative ready but cache_path missing
# ---------------------------------------------------------------------------


class TestDerivativeReadyNoFile:
    def test_derivative_requeued_when_cache_file_missing(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        missing_path = str(root / "missing.webp")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (path,)).fetchone()[0]
            conn.execute(
                """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality)
                   VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', ?, 512, 'webp', 85)""",
                (asset_id, mtime_ns, size, missing_path),
            )
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_derivative_ready_no_file(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT status, last_error, cache_path, byte_size FROM asset_derivatives WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            assert row["status"] == "queued"
            assert "file missing" in row["last_error"]
            assert row["cache_path"] is None, "stale cache_path should be cleared"
            assert row["byte_size"] is None, "stale byte_size should be cleared"
            # Verify a derivative_jobs row was created
            ad_id = conn.execute(
                "SELECT id FROM asset_derivatives WHERE asset_id = ? AND kind = 'thumbnail'", (asset_id,)
            ).fetchone()[0]
            dj = conn.execute("SELECT state FROM derivative_jobs WHERE derivative_id = ?", (ad_id,)).fetchone()
            assert dj is not None, "derivative_jobs row should exist"
            assert dj["state"] == "queued"

    def test_derivative_requeue_does_not_duplicate_active_job(self, _checker, isolated_gallery_root: Path):
        """When a derivative_jobs row is already queued/running, no duplicate is created."""
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        missing_path = str(root / "missing.webp")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (path,)).fetchone()[0]
            conn.execute(
                """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality)
                   VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', ?, 512, 'webp', 85)""",
                (asset_id, mtime_ns, size, missing_path),
            )
            ad_id = conn.execute(
                "SELECT id FROM asset_derivatives WHERE asset_id = ? AND kind = 'thumbnail'", (asset_id,)
            ).fetchone()[0]
            # Pre-seed a queued derivative_jobs row
            conn.execute(
                "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, 'queued')",
                (ad_id,),
            )
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_derivative_ready_no_file(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            # Only one queued/running derivative_jobs row should exist
            rows = conn.execute(
                "SELECT id, state FROM derivative_jobs WHERE derivative_id = ? AND state IN ('queued', 'running')",
                (ad_id,),
            ).fetchall()
            assert len(rows) == 1, "Should not duplicate an active derivative_jobs row"

    def test_derivative_requeued_when_cache_path_null(self, _checker, isolated_gallery_root: Path):
        """Derivative with status='ready' and cache_path=NULL should be requeued."""
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (path,)).fetchone()[0]
            # cache_path = NULL means no derivative was ever generated
            conn.execute(
                """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality)
                   VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', NULL, 512, 'webp', 85)""",
                (asset_id, mtime_ns, size),
            )
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_derivative_ready_no_file(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute(
                "SELECT status, last_error FROM asset_derivatives WHERE asset_id = ? AND kind = 'thumbnail'",
                (asset_id,),
            ).fetchone()
            assert row["status"] == "queued"
            assert "file missing" in row["last_error"]

    def test_derivative_unchanged_when_cache_file_exists(self, _checker, isolated_gallery_root: Path, tmp_path: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        cache_file = tmp_path / "exists.webp"
        cache_file.write_bytes(b"fake derivative")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (path,)).fetchone()[0]
            conn.execute(
                """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality)
                   VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'ready', ?, 512, 'webp', 85)""",
                (asset_id, mtime_ns, size, str(cache_file)),
            )
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_derivative_ready_no_file(conn)
        assert count == 0


# ---------------------------------------------------------------------------
# Test 5: Derivative job done but status not ready
# ---------------------------------------------------------------------------


class TestDerivativeJobDoneNotReady:
    def test_derivative_reconciled_when_job_done_and_not_ready(
        self, _checker, isolated_gallery_root: Path, tmp_path: Path
    ):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        cache_file = tmp_path / "exists.webp"
        cache_file.write_bytes(b"fake derivative")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (path,)).fetchone()[0]
            conn.execute(
                """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality)
                   VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'queued', ?, 512, 'webp', 85)""",
                (asset_id, mtime_ns, size, str(cache_file)),
            )
            ad_id = conn.execute(
                "SELECT id FROM asset_derivatives WHERE asset_id = ? AND kind = 'thumbnail'", (asset_id,)
            ).fetchone()[0]
            now = time.time()
            conn.execute(
                "INSERT INTO derivative_jobs (derivative_id, state, created_at, updated_at) VALUES (?, 'done', ?, ?)",
                (ad_id, now, now),
            )
        with _DB_LOCK, _connect() as conn:
            result = _checker._check_derivative_job_done_not_ready(conn)
        assert result == {"repaired": 1, "failed": 0}
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (ad_id,)).fetchone()
            assert row["status"] == "ready"

    def test_done_derivative_job_failed_when_cache_file_missing(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        lib = create_library([root], name="Lib")
        lib_id = int(lib["id"])
        path = str(root / "img.png")
        size = 1024
        mtime_ns = int(time.time() * 1e9)
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, lib_id, mtime_ns, size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (path,)).fetchone()[0]
            conn.execute(
                """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality)
                   VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'queued', '/tmp/missing.webp', 512, 'webp', 85)""",
                (asset_id, mtime_ns, size),
            )
            ad_id = conn.execute(
                "SELECT id FROM asset_derivatives WHERE asset_id = ? AND kind = 'thumbnail'", (asset_id,)
            ).fetchone()[0]
            now = time.time()
            conn.execute(
                "INSERT INTO derivative_jobs (derivative_id, state, created_at, updated_at) VALUES (?, 'done', ?, ?)",
                (ad_id, now, now),
            )
        with _DB_LOCK, _connect() as conn:
            result = _checker._check_derivative_job_done_not_ready(conn)
        assert result == {"repaired": 0, "failed": 1}
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state, error FROM derivative_jobs WHERE derivative_id = ?", (ad_id,)).fetchone()
            assert row["state"] == "failed"
            assert "cache file missing" in row["error"]


# ---------------------------------------------------------------------------
# Test 6: Metadata job queued but file missing
# ---------------------------------------------------------------------------


class TestJobActiveNoFile:
    def test_queued_job_failed_when_file_missing(self, _checker, tmp_path: Path):
        path = str(tmp_path / "nonexistent.png")
        with _DB_LOCK, _connect() as conn:
            _metadata_job_row(conn, path, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_job_active_no_file(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state, error FROM metadata_index_jobs WHERE path = ?", (path,)).fetchone()
            assert row["state"] == "failed"
            assert "file missing" in row["error"]

    def test_queued_job_unchanged_when_file_exists(self, _checker, isolated_gallery_root: Path):
        root = isolated_gallery_root
        path = root / "exists.png"
        create_test_image(path)
        with _DB_LOCK, _connect() as conn:
            _metadata_job_row(conn, str(path), state="queued")
        with _DB_LOCK, _connect() as conn:
            count = _checker._check_job_active_no_file(conn)
        assert count == 0


# ---------------------------------------------------------------------------
# Test 7: Start/stop lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_stop(self):
        c = IntegrityChecker(interval=60)
        c.start()
        assert c._thread is not None and c._thread.is_alive()
        c.stop()
        assert c._thread is not None and not c._thread.is_alive()

    def test_start_twice_is_idempotent(self):
        c = IntegrityChecker(interval=60)
        c.start()
        thread_id = id(c._thread)
        c.start()
        assert id(c._thread) == thread_id
        c.stop()

    def test_stop_without_start(self):
        c = IntegrityChecker(interval=60)
        c.stop()

    def test_start_stop_singleton(self):
        integrity_checker.start()
        assert integrity_checker._thread is not None and integrity_checker._thread.is_alive()
        integrity_checker.stop()
        assert integrity_checker._thread is not None and not integrity_checker._thread.is_alive()


# ---------------------------------------------------------------------------
# Test 8: All checks with empty DB
# ---------------------------------------------------------------------------


class TestEmptyDB:
    def test_all_checks_return_zero(self, _checker):
        with _DB_LOCK, _connect():
            results = _checker.run_all_checks()
        for key, val in results.items():
            assert val == 0, f"{key} should be 0 but got {val}"


# ---------------------------------------------------------------------------
# Test 9: Persistence layer (Phase 3)
# ---------------------------------------------------------------------------


class TestRunAndPersist:
    def test_run_and_persist_creates_run_row(self, _checker):
        checker = _checker
        summary = checker.run_and_persist(trigger="manual")
        assert summary["trigger"] == "manual"
        assert summary["status"] == "ok"
        assert summary["error"] is None
        assert set(summary["issues"].keys()) == {
            "missing_source_files",
            "generated_image_missing",
            "metadata_mismatch",
            "orphaned_work_item",
            "generated_image_job_mismatch",
        }
        assert set(summary["repairs"].keys()) == {"repaired", "requeued", "failed", "unchanged"}
        assert summary["started_at"] is not None
        assert summary["finished_at"] is not None
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT * FROM integrity_check_runs").fetchone()
        assert row is not None
        assert row["trigger"] == "manual"
        assert row["status"] == "ok"
        assert row["error"] is None
        issues = json.loads(row["issues_json"])
        assert set(issues.keys()) == {
            "missing_source_files",
            "generated_image_missing",
            "metadata_mismatch",
            "orphaned_work_item",
            "generated_image_job_mismatch",
        }
        repairs = json.loads(row["repairs_json"])
        assert set(repairs.keys()) == {"repaired", "requeued", "failed", "unchanged"}

    def test_run_and_persist_error_records_error(self, _checker, monkeypatch):
        checker = _checker

        def _raise(*args, **kwargs):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(checker, "run_all_checks", _raise)
        summary = checker.run_and_persist(trigger="daemon")
        assert summary["status"] == "error"
        assert "simulated crash" in summary["error"]
        assert summary["trigger"] == "daemon"
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT * FROM integrity_check_runs").fetchone()
        assert row["status"] == "error"
        assert "simulated crash" in row["error"]

    def test_get_latest_run_returns_none_when_empty(self):
        from backend.metadata_store.maintenance_store import get_latest_run

        with _DB_LOCK, _connect() as conn:
            result = get_latest_run(conn)
        assert result is None

    def test_get_latest_run_returns_most_recent(self):
        from backend.metadata_store.maintenance_store import insert_run, get_latest_run

        now = time.time()
        with _DB_LOCK, _connect() as conn:
            id1 = insert_run(
                conn,
                {
                    "trigger": "manual",
                    "started_at": now - 10,
                    "finished_at": now - 5,
                    "status": "ok",
                    "error": None,
                    "issues": {
                        "missing_source_files": 0,
                        "generated_image_missing": 0,
                        "metadata_mismatch": 0,
                        "orphaned_work_item": 0,
                        "generated_image_job_mismatch": 0,
                    },
                    "repairs": {"repaired": 0, "requeued": 0, "failed": 0, "unchanged": 0},
                },
            )
            id2 = insert_run(
                conn,
                {
                    "trigger": "daemon",
                    "started_at": now - 3,
                    "finished_at": now,
                    "status": "ok",
                    "error": None,
                    "issues": {
                        "missing_source_files": 0,
                        "generated_image_missing": 0,
                        "metadata_mismatch": 0,
                        "orphaned_work_item": 0,
                        "generated_image_job_mismatch": 0,
                    },
                    "repairs": {"repaired": 0, "requeued": 0, "failed": 0, "unchanged": 0},
                },
            )
            latest = get_latest_run(conn)
        assert latest is not None
        assert latest["id"] == id2
        assert latest["trigger"] == "daemon"

    def test_is_running_flag_during_run(self, _checker):
        checker = _checker
        assert checker.is_running is False
        captured = []
        original = checker.run_all_checks

        def tracking_run(*args, **kwargs):
            captured.append(checker.is_running)
            return original(*args, **kwargs)

        checker.run_all_checks = tracking_run
        checker.run_and_persist(trigger="manual")
        assert captured == [True]
        assert checker.is_running is False
