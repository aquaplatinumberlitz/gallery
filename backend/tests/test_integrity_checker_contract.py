"""Contract tests for IntegrityChecker individual checks and schema edge cases.

Purpose:
Validate per-check IntegrityChecker contracts, run summary mapping, persisted
file-health envelopes, and schema-check failure reporting.

Guarantees:
Each check returns stable counts, repairs only the intended rows, preserves
unrelated rows, maps eight run_all_checks keys into five issue and four repair
keys, and records manual/daemon runs consistently.

Run when:
Changing integrity checker checks, file-health summary mapping, schema_check,
or the maintenance run persistence contract.

Each check is tested for three contract guarantees:
1. Returns 0 on empty DB
2. Correctly identifies and repairs the issue (non-zero count)
3. Does not affect unrelated rows

Also covers run_all_checks, run_and_persist, and schema_check edge cases.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from backend.integrity_checker import integrity_checker
from backend.metadata_store import _DB_LOCK, _connect, create_library, initialize_database
from backend.metadata_store.maintenance_store import get_latest_run
from backend.metadata_store.schema_check import check_catalog_schema


@pytest.fixture(autouse=True)
def _init_db(isolated_metadata_db: Path) -> None:
    initialize_database()


@pytest.fixture(autouse=True)
def _reset_checker() -> None:
    global _LIBRARY_ID
    _LIBRARY_ID = None
    integrity_checker.is_running = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FILE_HEALTH_ISSUES = {
    "missing_source_files",
    "generated_image_missing",
    "generated_image_abandoned",
    "metadata_mismatch",
    "orphaned_work_item",
    "generated_image_job_mismatch",
    "generated_image_expected_row_missing",
    "generated_image_queued_without_job",
    "generated_image_policy_deferred",
}
FILE_HEALTH_REPAIRS = {"repaired", "requeued", "failed", "skipped", "recovered", "unchanged"}


_LIBRARY_ID: int | None = None


def _ensure_library(conn: sqlite3.Connection) -> int:
    global _LIBRARY_ID
    if _LIBRARY_ID is None:
        lib = create_library([Path("/tmp/integrity_checker_test_lib")], name="TestLib")
        _LIBRARY_ID = int(lib["id"])
    return _LIBRARY_ID


def _asset_row(
    conn: sqlite3.Connection,
    path: str,
    mtime_ns: int = 0,
    size: int = 1024,
    metadata_state: str = "pending",
) -> None:
    now = time.time()
    library_id = _ensure_library(conn)
    conn.execute(
        """INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size,
           metadata_state, offline, deleted_at, indexed_at)
           VALUES (?, ?, ?, ?, 'image', ?, ?, ?, 0, NULL, ?)""",
        (library_id, path, str(Path(path).parent), Path(path).name, mtime_ns, size, metadata_state, now),
    )


def _image_metadata_row(
    conn: sqlite3.Connection,
    path: str,
    mtime_ns: int = 0,
    size: int = 1024,
) -> None:
    now = time.time()
    conn.execute(
        """INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, metadata_json, updated_at, indexed_at)
           VALUES (?, ?, ?, ?, ?, 64, 64, '{}', ?, ?)""",
        (path, Path(path).name, mtime_ns / 1e9, mtime_ns, size, now, now),
    )


def _metadata_job_row(
    conn: sqlite3.Connection,
    path: str,
    state: str = "queued",
    mtime_ns: int = 0,
    size: int = 1024,
) -> None:
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
            mtime_ns / 1e9,
            mtime_ns,
            size,
            state,
            now,
            now,
        ),
    )


def _derivative_row(
    conn: sqlite3.Connection,
    asset_id: int,
    cache_path: str | None = None,
    status: str = "queued",
    source_mtime_ns: int = 0,
) -> int:
    now = time.time()
    conn.execute(
        """INSERT INTO asset_derivatives (asset_id, kind, variant, source_mtime_ns, source_size, status, cache_path, max_long_edge, format, quality, updated_at)
           VALUES (?, 'thumbnail', 'thumb_512', ?, 1024, ?, ?, 512, 'webp', 85, ?)""",
        (asset_id, source_mtime_ns, status, cache_path, now),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _derivative_job_row(conn: sqlite3.Connection, derivative_id: int, state: str = "queued") -> None:
    now = time.time()
    conn.execute(
        "INSERT INTO derivative_jobs (derivative_id, state, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (derivative_id, state, now, now),
    )


# ===================================================================
# Check 1: _check_asset_done_no_metadata
# ===================================================================


class TestCheckAssetDoneNoMetadata:
    """Contract: assets with metadata_state='done' must have a matching image_metadata row."""

    def test_empty_db_returns_zero(self) -> None:
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_asset_done_no_metadata(conn)
        assert count == 0

    def test_detects_and_demotes_violation(self, tmp_path: Path) -> None:
        path = str(tmp_path / "test.png")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, metadata_state="done")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_asset_done_no_metadata(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (path,)).fetchone()
            assert row["metadata_state"] == "pending"

    def test_unaffected_row_left_alone(self, tmp_path: Path) -> None:
        good = str(tmp_path / "good.png")
        bad = str(tmp_path / "bad.png")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, good, metadata_state="done")
            _image_metadata_row(conn, good)
            _asset_row(conn, bad, metadata_state="done")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_asset_done_no_metadata(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (good,)).fetchone()["metadata_state"]
                == "done"
            )
            assert (
                conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (bad,)).fetchone()["metadata_state"]
                == "pending"
            )


# ===================================================================
# Check 2: _check_job_done_asset_not_done
# ===================================================================


class TestCheckJobDoneAssetNotDone:
    """Contract: done metadata_index_jobs with matching metadata should stamp asset done."""

    def test_empty_db_returns_zero(self) -> None:
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_done_asset_not_done(conn)
        assert count == 0

    def test_detects_and_stamps_done(self, tmp_path: Path) -> None:
        path = str(tmp_path / "test.png")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, path, metadata_state="pending")
            _image_metadata_row(conn, path)
            _metadata_job_row(conn, path, state="done")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_done_asset_not_done(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (path,)).fetchone()
            assert row["metadata_state"] == "done"

    def test_unaffected_row_left_alone(self, tmp_path: Path) -> None:
        good = str(tmp_path / "good.png")
        bad = str(tmp_path / "bad.png")
        good_mtime = int(time.time() * 1e9)
        bad_mtime = int(time.time() * 1e9) + 1
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, good, mtime_ns=good_mtime, metadata_state="pending")
            _image_metadata_row(conn, good, mtime_ns=good_mtime)
            _metadata_job_row(conn, good, state="done", mtime_ns=good_mtime)
            _asset_row(conn, bad, mtime_ns=bad_mtime, metadata_state="pending")
            _metadata_job_row(conn, bad, state="queued", mtime_ns=bad_mtime)
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_done_asset_not_done(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (good,)).fetchone()["metadata_state"]
                == "done"
            )
            assert (
                conn.execute("SELECT metadata_state FROM assets WHERE path = ?", (bad,)).fetchone()["metadata_state"]
                == "pending"
            )


# ===================================================================
# Check 3: _check_job_active_no_asset
# ===================================================================


class TestCheckJobActiveNoAsset:
    """Contract: queued/running metadata_index_jobs must have a matching assets row."""

    def test_empty_db_returns_zero(self) -> None:
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_active_no_asset(conn)
        assert count == 0

    def test_detects_and_fails_job(self, tmp_path: Path) -> None:
        path = str(tmp_path / "orphan.png")
        with _DB_LOCK, _connect() as conn:
            _metadata_job_row(conn, path, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_active_no_asset(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (path,)).fetchone()
            assert row["state"] == "failed"

    def test_unaffected_row_left_alone(self, tmp_path: Path) -> None:
        good = str(tmp_path / "good.png")
        bad = str(tmp_path / "bad.png")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, good)
            _metadata_job_row(conn, good, state="queued")
            _metadata_job_row(conn, bad, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_active_no_asset(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (good,)).fetchone()["state"]
                == "queued"
            )
            assert (
                conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (bad,)).fetchone()["state"]
                == "failed"
            )


# ===================================================================
# Check 4: _check_derivative_ready_no_file
# ===================================================================


class TestCheckDerivativeReadyNoFile:
    """Contract: ready derivatives must have a valid cache_path file on disk."""

    def test_empty_db_returns_zero(self) -> None:
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_derivative_ready_no_file(conn)
        assert count == 0

    def test_missing_source_is_skipped_when_cache_is_missing(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "missing.webp")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, str(tmp_path / "asset.png"))
            asset_id = conn.execute("SELECT id FROM assets").fetchone()[0]
            _derivative_row(conn, asset_id, cache_path=missing, status="ready")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_derivative_ready_no_file(conn)
        assert count == 0
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT status, cache_path, byte_size FROM asset_derivatives").fetchone()
            assert row["status"] == "skipped"
            assert row["cache_path"] is None

    def test_unaffected_row_left_alone(self, tmp_path: Path) -> None:
        existing = tmp_path / "exists.webp"
        existing.write_bytes(b"fake")
        missing = str(tmp_path / "missing.webp")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, str(tmp_path / "asset.png"))
            asset_id = conn.execute("SELECT id FROM assets").fetchone()[0]
            good_id = _derivative_row(conn, asset_id, cache_path=str(existing), status="ready", source_mtime_ns=1)
            bad_id = _derivative_row(conn, asset_id, cache_path=missing, status="ready", source_mtime_ns=2)
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_derivative_ready_no_file(conn)
        assert count == 0
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (good_id,)).fetchone()["status"]
                == "ready"
            )
            assert (
                conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (bad_id,)).fetchone()["status"]
                == "skipped"
            )


# ===================================================================
# Check 5: _check_derivative_job_done_not_ready
# ===================================================================


class TestCheckDerivativeJobDoneNotReady:
    """Contract: done derivative_jobs must have derivative status == 'ready'."""

    def test_empty_db_returns_zero(self) -> None:
        with _DB_LOCK, _connect() as conn:
            result = integrity_checker._check_derivative_job_done_not_ready(conn)
        assert result == {"repaired": 0, "failed": 0}

    def test_detects_and_reconciles_when_file_exists(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "exists.webp"
        cache_file.write_bytes(b"fake")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, str(tmp_path / "asset.png"))
            asset_id = conn.execute("SELECT id FROM assets").fetchone()[0]
            ad_id = _derivative_row(conn, asset_id, cache_path=str(cache_file), status="queued")
            _derivative_job_row(conn, ad_id, state="done")
        with _DB_LOCK, _connect() as conn:
            result = integrity_checker._check_derivative_job_done_not_ready(conn)
        assert result == {"repaired": 1, "failed": 0}
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (ad_id,)).fetchone()
            assert row["status"] == "ready"

    def test_unaffected_row_left_alone(self, tmp_path: Path) -> None:
        cache_file = tmp_path / "exists.webp"
        cache_file.write_bytes(b"fake")
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, str(tmp_path / "asset.png"))
            asset_id = conn.execute("SELECT id FROM assets").fetchone()[0]
            ad_id = _derivative_row(conn, asset_id, cache_path=str(cache_file), status="ready", source_mtime_ns=1)
            _derivative_job_row(conn, ad_id, state="done")
            ad_id2 = _derivative_row(conn, asset_id, cache_path=str(cache_file), status="queued", source_mtime_ns=2)
            _derivative_job_row(conn, ad_id2, state="done")
        with _DB_LOCK, _connect() as conn:
            result = integrity_checker._check_derivative_job_done_not_ready(conn)
        assert result == {"repaired": 1, "failed": 0}
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (ad_id,)).fetchone()["status"]
                == "ready"
            )
            assert (
                conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (ad_id2,)).fetchone()["status"]
                == "ready"
            )


# ===================================================================
# Check 6: _check_job_active_no_file
# ===================================================================


class TestCheckJobActiveNoFile:
    """Contract: queued/running metadata_index_jobs must have the source file on disk."""

    def test_empty_db_returns_zero(self) -> None:
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_active_no_file(conn)
        assert count == 0

    def test_detects_and_fails_when_file_missing(self, tmp_path: Path) -> None:
        path = str(tmp_path / "nonexistent.png")
        with _DB_LOCK, _connect() as conn:
            _metadata_job_row(conn, path, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_active_no_file(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            row = conn.execute("SELECT state, error FROM metadata_index_jobs WHERE path = ?", (path,)).fetchone()
            assert row["state"] == "failed"
            assert "file missing" in row["error"]

    def test_unaffected_row_left_alone(self, tmp_path: Path) -> None:
        existing = tmp_path / "exists.png"
        existing.write_bytes(b"fake")
        missing = str(tmp_path / "missing.png")
        with _DB_LOCK, _connect() as conn:
            _metadata_job_row(conn, str(existing), state="queued")
            _metadata_job_row(conn, missing, state="queued")
        with _DB_LOCK, _connect() as conn:
            count = integrity_checker._check_job_active_no_file(conn)
        assert count == 1
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (str(existing),)).fetchone()[
                    "state"
                ]
                == "queued"
            )
            assert (
                conn.execute("SELECT state FROM metadata_index_jobs WHERE path = ?", (missing,)).fetchone()["state"]
                == "failed"
            )


# ===================================================================
# run_all_checks contract
# ===================================================================


class TestAbandonedDerivativeRecovery:
    def test_completed_claim_is_not_overwritten_after_recovery_selection(
        self,
        isolated_metadata_db: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        source = tmp_path / "source.png"
        source.write_bytes(b"x" * 1024)
        stat = source.stat()
        with _DB_LOCK, _connect() as conn:
            _asset_row(conn, str(source), mtime_ns=stat.st_mtime_ns, size=stat.st_size)
            asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (str(source),)).fetchone()[0]
            derivative_id = _derivative_row(
                conn,
                asset_id,
                status="running",
                source_mtime_ns=stat.st_mtime_ns,
            )
            _derivative_job_row(conn, derivative_id, state="running")
            job_id = conn.execute(
                "SELECT id FROM derivative_jobs WHERE derivative_id = ?",
                (derivative_id,),
            ).fetchone()[0]
            conn.execute(
                """
                UPDATE derivative_jobs
                SET attempts = 1, claimed_by = 'worker', claim_token = 'old-token',
                    lease_expires_at = julianday('now') - 1
                WHERE id = ?
                """,
                (job_id,),
            )

        def complete_claim(_row: sqlite3.Row) -> None:
            with sqlite3.connect(isolated_metadata_db) as conn:
                conn.execute(
                    """
                    UPDATE derivative_jobs
                    SET state = 'done', claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (job_id,),
                )
                conn.execute(
                    "UPDATE asset_derivatives SET status = 'ready' WHERE id = ?",
                    (derivative_id,),
                )
            return None

        monkeypatch.setattr(integrity_checker, "_derivative_inapplicable_result", complete_claim)

        with _DB_LOCK, _connect() as conn:
            result = integrity_checker._check_abandoned_derivative_jobs(conn)

        assert result == {"requeued": 0, "skipped": 0, "failed": 0}
        with _DB_LOCK, _connect() as conn:
            assert (
                conn.execute(
                    "SELECT state FROM derivative_jobs WHERE id = ?",
                    (job_id,),
                ).fetchone()["state"]
                == "done"
            )
            assert (
                conn.execute(
                    "SELECT status FROM asset_derivatives WHERE id = ?",
                    (derivative_id,),
                ).fetchone()["status"]
                == "ready"
            )


class TestRunAllChecks:
    def test_returns_all_twenty_keys_with_int_values(self) -> None:
        results = integrity_checker.run_all_checks()
        expected_keys = {
            "asset_done_but_no_metadata",
            "job_done_asset_not_done",
            "job_active_no_asset",
            "derivative_ready_no_file",
            "derivative_ready_requeued",
            "derivative_ready_skipped",
            "derivative_done_not_ready",
            "derivative_done_repaired",
            "derivative_done_failed",
            "job_active_no_file",
            "derivative_abandoned_jobs",
            "derivative_abandoned_requeued",
            "derivative_abandoned_skipped",
            "derivative_abandoned_failed",
            "derivative_expected_row_missing",
            "derivative_expected_row_created",
            "derivative_queued_without_job",
            "derivative_queued_without_job_repaired",
            "derivative_policy_deferred",
            "derivative_policy_deferred_requeued",
        }
        assert set(results.keys()) == expected_keys
        for val in results.values():
            assert isinstance(val, int)
            assert val >= 0


# ===================================================================
# run_and_persist contract
# ===================================================================


class TestRunAndPersist:
    def test_returns_full_summary_and_persists_run(self) -> None:
        summary = integrity_checker.run_and_persist(trigger="manual")
        assert set(summary.keys()) == {
            "id",
            "trigger",
            "started_at",
            "finished_at",
            "status",
            "error",
            "issues",
            "repairs",
        }
        assert summary["trigger"] == "manual"
        assert summary["status"] == "ok"
        assert summary["error"] is None
        assert set(summary["issues"].keys()) == FILE_HEALTH_ISSUES
        assert set(summary["repairs"].keys()) == FILE_HEALTH_REPAIRS
        assert isinstance(summary["started_at"], float)
        assert isinstance(summary["finished_at"], float)
        assert summary["id"] is not None

        with _DB_LOCK, _connect() as conn:
            persisted = get_latest_run(conn)
        assert persisted is not None
        assert persisted["id"] == summary["id"]
        assert persisted["trigger"] == "manual"

    def test_can_be_retrieved_via_get_latest_run(self) -> None:
        summary = integrity_checker.run_and_persist(trigger="daemon")
        with _DB_LOCK, _connect() as conn:
            persisted = get_latest_run(conn)
        assert persisted is not None
        assert persisted["id"] == summary["id"]
        assert persisted["trigger"] == "daemon"


# ===================================================================
# Schema-check edge cases
# ===================================================================


class TestSchemaCheckEdgeCases:
    """Additional edge cases beyond the four existing test_schema_check.py tests."""

    def test_multiple_missing_items_reported_together(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY,
                library_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                parent_path TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                mtime_ns REAL,
                size INTEGER,
                metadata_state TEXT,
                deleted_at REAL,
                offline INTEGER NOT NULL DEFAULT 0,
                indexed_at REAL
            )
        """)
        issues = check_catalog_schema(conn)
        missing_tables = [i for i in issues if i.startswith("Missing table")]
        assert len(missing_tables) >= 7
        assert "Missing table: image_metadata" in issues
        assert "Missing table: metadata_index_jobs" in issues
        assert "Missing index: idx_image_metadata_mtime_size" in issues

    def test_empty_database_reports_all_tables_missing(self) -> None:
        conn = sqlite3.connect(":memory:")
        issues = check_catalog_schema(conn)
        missing_tables = [i for i in issues if i.startswith("Missing table")]
        assert len(missing_tables) >= 9

    def test_extra_columns_do_not_cause_false_positives(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY,
                library_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                parent_path TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                mtime_ns REAL,
                size INTEGER,
                metadata_state TEXT,
                deleted_at REAL,
                offline INTEGER NOT NULL DEFAULT 0,
                indexed_at REAL,
                extra_column_1 TEXT,
                extra_column_2 INTEGER
            );
            CREATE TABLE image_metadata (
                path TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                mtime REAL,
                mtime_ns INTEGER,
                size INTEGER,
                width INTEGER,
                height INTEGER,
                extra_col TEXT
            );
            CREATE TABLE metadata_index_jobs (
                path TEXT NOT NULL,
                name TEXT NOT NULL,
                parent_path TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                root_path TEXT NOT NULL,
                mtime REAL,
                mtime_ns INTEGER,
                size INTEGER NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                queued_at REAL,
                started_at REAL,
                finished_at REAL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE asset_derivatives (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                variant TEXT NOT NULL,
                source_mtime_ns REAL NOT NULL,
                source_size INTEGER NOT NULL,
                format TEXT NOT NULL DEFAULT 'webp',
                quality INTEGER NOT NULL DEFAULT 85,
                max_long_edge INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                cache_path TEXT,
                byte_size INTEGER,
                last_accessed_at REAL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                updated_at REAL NOT NULL DEFAULT (julianday('now'))
            );
            CREATE TABLE derivative_jobs (
                id INTEGER PRIMARY KEY,
                derivative_id INTEGER NOT NULL,
                priority INTEGER NOT NULL DEFAULT 3,
                state TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at REAL NOT NULL DEFAULT (julianday('now')),
                updated_at REAL NOT NULL DEFAULT (julianday('now')),
                started_at REAL,
                completed_at REAL
            );
            CREATE TABLE libraries (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE library_import_paths (
                id INTEGER PRIMARY KEY,
                library_id INTEGER NOT NULL,
                path TEXT NOT NULL
            );
            CREATE TABLE catalog_rebuild_entries (
                job_id INTEGER NOT NULL,
                library_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                parent_path TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                mtime_ns INTEGER,
                size INTEGER,
                width INTEGER,
                height INTEGER,
                mime_type TEXT,
                duration_ms INTEGER,
                codec TEXT,
                PRIMARY KEY(job_id, path)
            );
            CREATE TABLE integrity_check_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger TEXT NOT NULL,
                started_at REAL NOT NULL,
                finished_at REAL,
                status TEXT NOT NULL,
                error TEXT,
                issues_json TEXT NOT NULL,
                repairs_json TEXT NOT NULL
            );
        """)
        issues = check_catalog_schema(conn)
        col_issues = [i for i in issues if "extra" in i.lower() or "extra_column" in i]
        assert len(col_issues) == 0, "Extra columns should not cause false positives"
