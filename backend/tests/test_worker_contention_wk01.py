"""WK-01 regression: status reads must not stall background workers.

Purpose:
Pin the worker-lifecycle audit finding WK-01. The runtime status query ran a
correlated ``max(id)`` subquery over ``derivative_jobs`` with no
``(derivative_id, id)`` index while holding the process-wide ``_DB_LOCK``, so UI
status polling froze the metadata, derivative, and catalog workers.

Guarantees:
The ``idx_derivative_jobs_derivative_id`` index exists on fresh and existing
databases and is used by the global-runtime and per-library derivative status
queries; the 36,000-row runtime query finishes inside the 500 ms status budget;
no status function or endpoint waits on ``_DB_LOCK``; each status build reads
one consistent WAL snapshot; and the counters equal the values the pre-change
implementation produced for the same seeded database (frozen golden file).

Run when:
Changing status aggregate SQL, status read-connection handling, the
``derivative_jobs`` indexes, or anything that touches ``_DB_LOCK`` on a status path.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.worker_contention_support import (
    VARIANTS,
    capture_sql,
    query_plan,
    run_while_db_lock_held,
    seed_assets,
    seed_derivative_corpus,
    seed_library,
)

GOLDEN_PATH = Path(__file__).resolve().parent / "fixtures" / "worker_contention" / "status_golden_wk01.json"
INDEX_NAME = "idx_derivative_jobs_derivative_id"
STATUS_BUDGET_SECONDS = 0.5
LATEST_STATE_TO_DERIVATIVE_STATUS = {
    "done": "ready",
    "queued": "queued",
    "running": "running",
    "failed": "failed",
    "skipped": "skipped",
}


def _runtime_count_statement(statements: list[str]) -> str:
    matches = [s for s in statements if "FROM derivative_jobs j" in s and "GROUP BY j.state" in s and "latest" in s]
    assert matches, "build_global_runtime did not run the derivative job count query"
    return matches[0]


def _library_status_job_statement(statements: list[str]) -> str:
    matches = [s for s in statements if "max(CASE WHEN j.state = 'running'" in s]
    assert matches, "library_status did not run the derivative job lifecycle query"
    return matches[0]


def _capture_runtime_statement(monkeypatch: pytest.MonkeyPatch) -> str:
    from backend.metadata_store.status_store import build_global_runtime

    with capture_sql(monkeypatch) as statements:
        build_global_runtime()
    return _runtime_count_statement(statements)


def _run_counts(db_path: Path, statement: str, *, deadline: float | None = None) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        if deadline is not None:
            limit = time.perf_counter() + deadline
            conn.set_progress_handler(lambda: 1 if time.perf_counter() > limit else 0, 10_000)
        try:
            return {str(state): int(count) for state, count in conn.execute(statement)}
        except sqlite3.OperationalError as exc:
            pytest.fail(f"derivative count query exceeded {deadline}s and was interrupted: {exc}")


@pytest.fixture
def seeded_library(isolated_metadata_db: Path, isolated_gallery_root: Path) -> tuple[Path, int, Path]:
    root = isolated_gallery_root / "photos"
    root.mkdir()
    return isolated_metadata_db, seed_library(root), root


# ---------------------------------------------------------------------------
# 0.2 index for the runtime status query
# ---------------------------------------------------------------------------


def test_fresh_database_has_derivative_jobs_derivative_id_index(isolated_metadata_db: Path) -> None:
    with sqlite3.connect(isolated_metadata_db) as conn:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            (INDEX_NAME,),
        ).fetchone()
    assert row is not None, f"{INDEX_NAME} missing from a freshly initialized database"
    assert "derivative_jobs" in row[0] and "derivative_id" in row[0] and "id" in row[0].split("(", 1)[1]


def test_existing_database_gains_index_through_additive_ensure(
    isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store as ms

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms._db, "_DB_INITIALIZED_PATH", None)

    ms.initialize_database()

    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (INDEX_NAME,)).fetchone() is not None
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 12


def test_runtime_derivative_count_query_uses_derivative_id_index(
    isolated_metadata_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    statement = _capture_runtime_statement(monkeypatch)

    plan = query_plan(isolated_metadata_db, statement)

    assert INDEX_NAME in plan, f"runtime derivative count query does not use {INDEX_NAME}:\n{plan}"


def test_library_status_job_query_uses_derivative_id_index(
    seeded_library: tuple[Path, int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.derivative_scheduler import DerivativeScheduler

    db_path, library_id, _root = seeded_library
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=1024 * 1024)
    with capture_sql(monkeypatch) as statements:
        scheduler.library_status(library_id)

    plan = query_plan(db_path, _library_status_job_statement(statements))

    assert INDEX_NAME in plan, f"derivative library_status job query does not use {INDEX_NAME}:\n{plan}"


def test_runtime_derivative_count_query_finishes_within_budget_over_36000_job_rows(
    seeded_library: tuple[Path, int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, library_id, root = seeded_library
    statement = _capture_runtime_statement(monkeypatch)
    assets = seed_assets(db_path, library_id, root, 4_000)
    total_jobs, expected = seed_derivative_corpus(db_path, assets, jobs_per_derivative=3)
    assert total_jobs == 36_000

    started = time.perf_counter()
    counts = _run_counts(db_path, statement, deadline=10.0)
    elapsed = time.perf_counter() - started

    assert counts == expected
    assert elapsed < STATUS_BUDGET_SECONDS, f"runtime derivative count took {elapsed:.3f}s (budget 0.5s)"


def test_runtime_derivative_counts_identical_with_and_without_index(
    seeded_library: tuple[Path, int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, library_id, root = seeded_library
    statement = _capture_runtime_statement(monkeypatch)
    assets = seed_assets(db_path, library_id, root, 120)
    _total, expected = seed_derivative_corpus(db_path, assets, jobs_per_derivative=4)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
        # One superseded identity and one inactive asset must stay out of the counts.
        conn.execute("UPDATE assets SET mtime_ns = mtime_ns + 1 WHERE id = ?", (assets[0][0],))
        conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (assets[1][0],))
        excluded = conn.execute(
            """
            SELECT (SELECT state FROM derivative_jobs WHERE derivative_id = d.id ORDER BY id DESC LIMIT 1) AS state
            FROM asset_derivatives d WHERE d.asset_id IN (?, ?)
            """,
            (assets[0][0], assets[1][0]),
        ).fetchall()
    for (state,) in excluded:
        expected[str(state)] -= 1
    expected = {state: count for state, count in expected.items() if count}

    without_index = _run_counts(db_path, statement)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"CREATE INDEX {INDEX_NAME} ON derivative_jobs(derivative_id, id)")
    with_index = _run_counts(db_path, statement)

    assert len(with_index) >= 4
    assert without_index == expected
    assert with_index == expected


# ---------------------------------------------------------------------------
# 0.3 status reads without _DB_LOCK
# ---------------------------------------------------------------------------


def _status_callables(library_id: int) -> dict[str, Any]:
    from backend.derivative_scheduler import DerivativeScheduler
    from backend.indexer import get_indexer_runtime_status, get_metadata_lifecycle_status
    from backend.metadata_store.status_store import (
        build_catalog_status,
        build_global_runtime,
        build_library_status_batch,
    )

    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=1024 * 1024)
    return {
        "build_global_runtime": build_global_runtime,
        "build_catalog_status": lambda: build_catalog_status(library_id),
        "build_library_status_batch": build_library_status_batch,
        "derivative_library_status": lambda: scheduler.library_status(library_id),
        "get_indexer_runtime_status": get_indexer_runtime_status,
        "get_metadata_lifecycle_status": get_metadata_lifecycle_status,
    }


STATUS_FUNCTION_NAMES = (
    "build_global_runtime",
    "build_catalog_status",
    "build_library_status_batch",
    "derivative_library_status",
    "get_indexer_runtime_status",
    "get_metadata_lifecycle_status",
)


@pytest.mark.parametrize("name", STATUS_FUNCTION_NAMES)
def test_status_function_returns_while_another_thread_holds_db_lock(
    seeded_library: tuple[Path, int, Path], name: str
) -> None:
    _db_path, library_id, _root = seeded_library
    function = _status_callables(library_id)[name]

    finished, result, error = run_while_db_lock_held(function, timeout=2.0)

    assert finished, f"{name} blocked on _DB_LOCK for more than 2 s"
    assert error is None, f"{name} raised {error!r}"
    assert result


@pytest.mark.parametrize(
    "path_template",
    [
        "/api/libraries/{library_id}/status",
        "/api/libraries/status",
        "/api/derivatives/status?library_id={library_id}",
        "/api/maintenance/runtime",
    ],
)
def test_status_endpoint_returns_while_another_thread_holds_db_lock(
    isolated_app: TestClient, isolated_gallery_root: Path, path_template: str
) -> None:
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_library(root)
    path = path_template.format(library_id=library_id)

    finished, response, error = run_while_db_lock_held(lambda: isolated_app.get(path), timeout=2.0)

    assert finished, f"GET {path} blocked on _DB_LOCK for more than 2 s"
    assert error is None, f"GET {path} raised {error!r}"
    assert response.status_code == 200


def test_global_runtime_reads_one_snapshot_even_when_a_writer_commits_mid_build(
    seeded_library: tuple[Path, int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit that lands between two status queries must not be visible to the same build."""
    from backend.metadata_store.status_store import build_global_runtime

    db_path, library_id, root = seeded_library
    assets = seed_assets(db_path, library_id, root, 6)
    seed_derivative_corpus(db_path, assets, jobs_per_derivative=2, latest_states=("done",))
    before = build_global_runtime()
    assert before["derivative_queue_depth"] == 0

    with sqlite3.connect(db_path) as conn:
        target = int(conn.execute("SELECT min(id) FROM asset_derivatives").fetchone()[0])
    fired = threading.Event()

    def writer_commits_once(statement: str) -> None:
        # The first query (running catalog jobs) has already established the read snapshot
        # when the second library_jobs query starts; commit a new queued derivative job now.
        if "FROM library_jobs" in statement and "state = 'queued'" in statement and not fired.is_set():
            fired.set()
            writer = sqlite3.connect(db_path, timeout=5)
            try:
                writer.execute(
                    "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, 'queued')",
                    (target,),
                )
                writer.commit()
            finally:
                writer.close()

    real_connect = sqlite3.connect

    def traced_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        if not fired.is_set():
            conn.set_trace_callback(writer_commits_once)
        return conn

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", traced_connect)
        during = build_global_runtime()

    assert fired.is_set(), "writer hook never fired; the build did not query library_jobs"
    assert during["derivative_queue_depth"] == 0, "status build observed a commit made after its first read"
    assert build_global_runtime()["derivative_queue_depth"] == 1


def test_catalog_status_build_opens_a_single_read_connection(
    seeded_library: tuple[Path, int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.metadata_store.status_store import build_catalog_status

    _db_path, library_id, _root = seeded_library
    opened: list[str] = []
    real_connect = sqlite3.connect

    def counting_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        opened.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", counting_connect)
        build_catalog_status(library_id)

    assert len(opened) == 1, f"status build opened {len(opened)} connections: {opened}"


# ---------------------------------------------------------------------------
# 0.3 counters equal the pre-change values (frozen golden)
# ---------------------------------------------------------------------------

# Time-dependent values and process/config facts (worker counts, watcher, reconcile loop)
# are not derived from database counters, so they are excluded from the golden comparison.
VOLATILE_KEYS = frozenset(
    {
        "generated_at",
        "checked_at",
        "last_scan_at",
        "oldest_queued_metadata_job_age",
        "metadata_worker_alive",
        "derivative_oldest_running_age_seconds",
        "oldest_running_age_seconds",
        "created_at",
        "updated_at",
        "catalog_worker_count",
        "catalog_alive_workers",
        "catalog_supervisor_alive",
        "catalog_supervisor_failures",
        "catalog_supervisor_last_check_at",
        "catalog_supervisor_last_recovered_jobs",
        "metadata_worker_count",
        "derivative_configured_worker_count",
        "derivative_worker_count",
        "worker_count",
        "alive_worker_count",
        "configured_worker_count",
        "worker_healthy",
        "watcher_enabled",
        "watcher_healthy",
        "watcher_issue",
        "scheduled_reconciliation_enabled",
        "derivative_reconcile_enabled",
        "derivative_reconcile_running",
        "derivative_last_reconcile_started_at",
        "derivative_last_reconcile_completed_at",
        "derivative_last_reconcile_status",
        "derivative_last_reconcile_created_jobs",
    }
)


def _scrub(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {
            _scrub(key, root): _scrub(item, root) for key, item in sorted(value.items()) if key not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_scrub(item, root) for item in value]
    if isinstance(value, str):
        return value.replace(str(root), "<root>")
    return value


def seed_status_golden_state(db_path: Path, root: Path) -> int:
    """Seed the deterministic database whose status output is frozen in the golden file."""
    from backend.metadata_store import create_job, update_job_state

    library_id = seed_library(root, name="Golden")
    assets = seed_assets(db_path, library_id, root, 8)
    with sqlite3.connect(db_path) as conn:
        for index, (_asset_id, path, mtime_ns, size) in enumerate(assets):
            name = Path(path).name
            if index < 3:
                conn.execute("UPDATE assets SET metadata_state = 'done' WHERE path = ?", (path,))
                conn.execute(
                    """
                    INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, updated_at, indexed_at)
                    VALUES (?, ?, ?, ?, ?, 1700000200.0, 1700000300.0)
                    """,
                    (path, name, mtime_ns / 1e9, mtime_ns, size),
                )
            job_state = ("done", "done", "done", "queued", "queued", "running", "failed", "stale")[index]
            conn.execute(
                """
                INSERT INTO metadata_index_jobs (
                  path, name, parent_path, folder_path, root_path, mtime, mtime_ns, size, state,
                  attempts, error, queued_at, started_at, finished_at, updated_at, library_id, priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 3)
                """,
                (
                    path,
                    name,
                    str(root),
                    str(root),
                    str(root),
                    mtime_ns / 1e9,
                    mtime_ns,
                    size,
                    job_state,
                    1 if job_state in {"running", "failed", "done"} else 0,
                    "boom" if job_state == "failed" else None,
                    1_700_000_000.0 + index,
                    1_700_000_100.0 + index if job_state in {"running", "done", "failed"} else None,
                    1_700_000_150.0 + index if job_state in {"done", "failed", "stale"} else None,
                    1_700_000_400.0 + index,
                    library_id,
                ),
            )
    seed_derivative_corpus(
        db_path,
        assets,
        jobs_per_derivative=2,
        derivative_status=LATEST_STATE_TO_DERIVATIVE_STATUS,
    )
    done_job = create_job("scan", library_id=library_id)
    update_job_state(int(done_job["id"]), "running", progress_total=8)
    update_job_state(int(done_job["id"]), "succeeded", progress_current=8, progress_total=8)
    return library_id


def build_status_snapshot(library_id: int, root: Path) -> dict[str, Any]:
    from backend.derivative_scheduler import DerivativeScheduler
    from backend.indexer import get_indexer_runtime_status, get_metadata_lifecycle_status
    from backend.metadata_store.status_store import (
        build_catalog_status,
        build_global_runtime,
        build_library_status_batch,
    )

    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=10 * 1024 * 1024)
    snapshot = {
        "catalog_status": build_catalog_status(library_id),
        "library_status_batch": build_library_status_batch(),
        "global_runtime": build_global_runtime(),
        "metadata_lifecycle": get_metadata_lifecycle_status(),
        "indexer_runtime": get_indexer_runtime_status(),
        "derivative_library_status": scheduler.library_status(library_id),
    }
    return _scrub(snapshot, root)


def test_status_counters_equal_values_from_the_pre_change_implementation(
    isolated_metadata_db: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.config as config_module

    monkeypatch.setattr(config_module, "METADATA_INDEXER_ENABLED", True)
    root = isolated_gallery_root / "photos"
    root.mkdir()
    library_id = seed_status_golden_state(isolated_metadata_db, root)

    snapshot = build_status_snapshot(library_id, root)

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert snapshot == golden
    # Guard against a vacuous golden: the seeded state must exercise every counter family.
    metadata = snapshot["catalog_status"]["status"]["metadata"]
    assert metadata["total_assets"] == 8 and metadata["ready_assets"] == 3 and metadata["failed_assets"] == 1
    assert snapshot["global_runtime"]["derivative_queue_depth"] > 0
    assert snapshot["global_runtime"]["derivative_failed_jobs"] > 0
    assert snapshot["metadata_lifecycle"]["queued_metadata_jobs"] == 2
    assert len(VARIANTS) == 3
