"""Phase 2.4 regression: catalog scan and rebuild writes go through the single database writer.

Purpose:
Pin the catalog half of the Phase 2 write-contention work. Before it, every catalog write (claim, job
transition, lease renewal, bulk index batch, reconcile, metadata-job persistence, rebuild staging and
activation) ran in its own ``_DB_LOCK`` + ``BEGIN IMMEDIATE`` transaction, so the lease renewal of a
running scan queued behind any unrelated ``_DB_LOCK`` holder (WK-02 root cause: two scans lost their claim
in the audit) and long scan batches held SQLite's write lock for hundreds of milliseconds. Now every one
of them is a writer op: claim, job transitions, lease renewals and abandoned-claim closing use the
priority lane and scan batch writes use the normal lane (Phase 3 retired ``_DB_LOCK``).

Guarantees:
With the writer running, a whole scan and a whole rebuild run no write statement on any thread but the
writer thread; claim, job transitions, lease renewals
and abandoned-claim closing are priority-lane ops while scan batches, reconcile, metadata-job persistence,
rebuild staging and activation are normal-lane ops; bulk index writes are split into small ops; the
catalog lease heartbeat keeps a claim alive while unrelated bulk writers saturate the write path for longer
than the lease; claim fencing is unchanged (a stale claim writes zero rows and its ops raise ``CatalogJobClaimLost``
inside the op); rebuild activation stays one atomic op; conflicts raised inside an op surface unchanged;
the maintenance producer gate still holds back catalog writes and an in-flight op keeps maintenance from
starting; scan results are identical through the writer and through the no-active-writer path; with no
active writer every path uses direct transactions and the writer never starts.

Run when:
Changing catalog job claim/transition/renew/recover paths, scan batch persistence, rebuild staging or
activation, the catalog lease heartbeat, the maintenance producer gate, or the no-active-writer path.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from backend import scan_worker
from backend.metadata_store import (
    CatalogJobClaimLost,
    CatalogJobConflict,
    claim_next_catalog_job,
    create_job,
    create_library,
    renew_catalog_job_lease,
    update_job_state,
)
from backend.metadata_store._db import open_connection
from tests.conftest import create_test_png
from tests.test_db_writer import Blocker
from tests.worker_contention_support import (
    WRITER_THREAD_NAME,
    RecordingWriter,
    capture_write_threads,
    install_submit_spy,
    run_while_write_path_saturated,
)

needs_writer = pytest.mark.usefixtures("started_writer")
CATALOG_TABLES = (
    "library_jobs",
    "libraries",
    "assets",
    "file_index",
    "file_index_fts",
    "metadata_index_jobs",
    "catalog_rebuild_entries",
    "derivative_jobs",
    "asset_derivatives",
)
FIXED_MTIME_NS = 1_700_000_000_000_000_000


def _writer_module():
    import backend.metadata_store.db_writer as db_writer_module

    return db_writer_module


def _populate(root: Path, count: int = 8) -> list[Path]:
    images: list[Path] = []
    for album in ("album_a", "album_b"):
        (root / album).mkdir(parents=True, exist_ok=True)
        for index in range(count // 2):
            image = root / album / f"img_{index:03d}.png"
            create_test_png(image, size=(24, 16), color=(index * 30 % 255, 90, 160))
            os.utime(image, ns=(FIXED_MTIME_NS, FIXED_MTIME_NS + index * 1_000_000))
            images.append(image.resolve())
    return images


@pytest.fixture
def scan_env(
    isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_thumbnail_cache: Path
) -> tuple[Path, int, Path, list[Path]]:
    """One library over a small album tree: ``(db_path, library_id, root, images)``."""
    root = isolated_gallery_root / "photos"
    root.mkdir()
    images = _populate(root)
    library_id = int(create_library([root], name="Catalog")["id"])
    return isolated_metadata_db, library_id, root, images


@pytest.fixture
def submit_log(monkeypatch: pytest.MonkeyPatch):
    return install_submit_spy(monkeypatch)


@pytest.fixture(params=["writer", "direct"])
def mode(request: pytest.FixtureRequest) -> str:
    """Run a test once through the writer and once through the no-active-writer (direct) path."""
    writer = _writer_module().database_writer
    if request.param == "writer":
        writer.start()
    else:
        writer.reset()
    return request.param


def _job(db_path: Path, job_id: int) -> dict[str, Any]:
    with open_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM library_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row is not None
    return dict(row)


def _count(db_path: Path, table: str) -> int:
    with open_connection(db_path) as conn:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


# ---------------------------------------------------------------------------
# A whole scan / rebuild runs on the writer thread only
# ---------------------------------------------------------------------------


@needs_writer
@pytest.mark.parametrize("operation", ["scan", "rebuild"])
def test_a_whole_catalog_job_writes_only_on_the_writer_thread(
    scan_env, submit_log, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    db_path, library_id, _root, images = scan_env

    with capture_write_threads(monkeypatch) as writes:
        if operation == "scan":
            job, _created = scan_worker.queue_scan(library_id, trigger="manual")
        else:
            job, _created = scan_worker.queue_rebuild(library_id)
        assert scan_worker.run_once() is True

    assert _job(db_path, int(job["id"]))["state"] == "succeeded"
    assert _count(db_path, "assets") >= len(images)
    assert _count(db_path, "metadata_index_jobs") == len(images)
    off_writer = [(thread, text.split("(")[0][:60]) for thread, text in writes if thread != WRITER_THREAD_NAME]
    assert not off_writer, f"{operation} wrote outside the database writer: {off_writer[:12]}"
    on_writer = " ".join(text for thread, text in writes if thread == WRITER_THREAD_NAME)
    for table in ("library_jobs", "assets", "file_index", "metadata_index_jobs"):
        assert table in on_writer, f"no {table} write reached the writer during a {operation}"
    assert submit_log, "the catalog job never used the writer"


# ---------------------------------------------------------------------------
# Lanes
# ---------------------------------------------------------------------------


@needs_writer
def test_claim_transitions_renewals_and_abandoned_claims_are_priority_ops_and_scan_batches_normal_ops(
    scan_env, submit_log
) -> None:
    from backend.indexer import dispatch_metadata_index_paths
    from backend.metadata_store import (
        activate_rebuild_staging,
        delete_rebuild_staging,
        enumerate_to_rebuild_staging,
        fail_abandoned_catalog_job_claim,
        index_directory_tree,
        reconcile_library_assets,
        recover_stale_jobs,
    )
    from backend.metadata_store.job_store import update_parent_aggregate_job

    db_path, library_id, root, images = scan_env
    lanes: dict[str, list[str]] = {}

    def lanes_of(label: str, action) -> Any:
        start = len(submit_log)
        result = action()
        lanes[label] = [entry.lane for entry in submit_log[start:]]
        return result

    parent = create_job("scan_all", progress_total=1)
    job, _created = lanes_of(
        "enqueue",
        lambda: scan_worker.queue_scan(library_id, trigger="manual", parent_job_id=int(parent["id"])),
    )
    claimed = lanes_of("claim", lambda: claim_next_catalog_job(worker_id="w-1", lease_seconds=60))
    assert claimed is not None and int(claimed["id"]) == int(job["id"])
    token = str(claimed["claim_token"])
    job_id = int(claimed["id"])
    lanes_of(
        "transition",
        lambda: update_job_state(job_id, "running", claim_token=token, progress_total=1, library_state="indexing"),
    )
    assert lanes_of("renew", lambda: renew_catalog_job_lease(job_id, token, lease_seconds=60)) is True
    collected: set[str] = set()
    lanes_of(
        "index",
        lambda: index_directory_tree(
            root, collected_asset_paths=collected, claim_job_id=job_id, claim_token=token, claim_lease_seconds=60
        ),
    )
    lanes_of(
        "reconcile",
        lambda: reconcile_library_assets(
            library_id, collected, scope_path=root, claim_job_id=job_id, claim_token=token, claim_lease_seconds=60
        ),
    )
    lanes_of(
        "metadata_jobs",
        lambda: dispatch_metadata_index_paths(
            images,
            root,
            catalog_claim_job_id=job_id,
            catalog_claim_token=token,
            catalog_claim_lease_seconds=60,
        ),
    )
    lanes_of("parent", lambda: update_parent_aggregate_job(int(parent["id"])))
    lanes_of(
        "abandoned",
        lambda: fail_abandoned_catalog_job_claim(job_id, token, reason="test closes the claim"),
    )
    assert _job(db_path, job_id)["state"] == "failed"

    rebuild, _created = scan_worker.queue_rebuild(library_id)
    claimed_rebuild = claim_next_catalog_job(worker_id="w-1", lease_seconds=60)
    assert claimed_rebuild is not None
    rebuild_id, rebuild_token = int(claimed_rebuild["id"]), str(claimed_rebuild["claim_token"])
    assert rebuild_id == int(rebuild["id"])
    lanes_of(
        "staging",
        lambda: enumerate_to_rebuild_staging(rebuild_id, library_id, [root], rebuild_token, 60),
    )
    lanes_of("activation", lambda: activate_rebuild_staging(rebuild_id, library_id, None, rebuild_token, 60))
    lanes_of("delete_staging", lambda: delete_rebuild_staging(rebuild_id, claim_token=rebuild_token))
    with open_connection(db_path) as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = 1.0 WHERE id = ?", (rebuild_id,))
    recovered = lanes_of("recover", lambda: recover_stale_jobs(reason="test recovery", live_worker_ids=set()))
    assert [item["id"] for item in recovered if item["id"] == rebuild_id]

    for label in ("enqueue", "claim", "transition", "renew", "parent", "abandoned"):
        assert lanes[label], f"{label} never reached the writer"
        assert set(lanes[label]) == {"priority"}, f"{label} used lanes {lanes[label]}"
    for label in ("index", "reconcile", "metadata_jobs", "staging", "activation", "delete_staging", "recover"):
        assert lanes[label], f"{label} never reached the writer"
        assert set(lanes[label]) == {"normal"}, f"{label} used lanes {lanes[label]}"
    assert len(lanes["claim"]) == 1 and len(lanes["activation"]) == 1, "claim and activation are one op each"


@needs_writer
def test_bulk_index_writes_are_split_into_small_writer_ops(scan_env, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.metadata_store.file_index import _bulk_index_records

    db_path, library_id, root, _images = scan_env
    records = [
        (
            str(root / f"synthetic_{index:05d}.png"),
            f"synthetic_{index:05d}.png",
            str(root),
            "image",
            1.0,
            FIXED_MTIME_NS + index,
            1_000 + index,
            8,
            8,
            time.time(),
            "image/png",
            None,
            None,
        )
        for index in range(1_200)
    ]
    recording = RecordingWriter(monkeypatch)
    try:
        _bulk_index_records(records, library_id)
    finally:
        recording.stop()

    assert _count(db_path, "file_index") == 1_200
    per_op = [count for count in recording.writes_per_op("INSERT INTO file_index (") if count]
    assert len(per_op) >= 4, f"1,200 rows must be several ops; saw {per_op}"
    assert sum(per_op) == 1_200
    assert max(per_op) <= 50, f"one op wrote too many rows for the 250 ms write budget: {per_op}"


# ---------------------------------------------------------------------------
# Lease renewal vs unrelated bulk writers (WK-02 root cause)
# ---------------------------------------------------------------------------


@needs_writer
def test_a_running_scans_lease_is_renewed_while_unrelated_bulk_writers_saturate_the_write_path_longer_than_the_lease(
    scan_env, submit_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writer-path version of the WK-02 lease test (the direct path has no priority lane and no workers).

    Before this test ran in both modes while another thread held ``_DB_LOCK``; only a running writer has a
    priority lane that lets a renewal overtake bulk writers, which is the guarantee that replaced the lock.
    """
    db_path, library_id, _root, _images = scan_env
    monkeypatch.setattr(scan_worker, "CATALOG_LEASE_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr(scan_worker, "CATALOG_JOB_LEASE_SECONDS", 1.0)
    scan_worker.queue_scan(library_id, trigger="manual")
    claimed = claim_next_catalog_job(worker_id="w-lease", lease_seconds=1.0)
    assert claimed is not None
    job_id, token = int(claimed["id"]), str(claimed["claim_token"])
    update_job_state(job_id, "running", claim_token=token, lease_seconds=1.0, progress_total=1)
    original_expiry = float(_job(db_path, job_id)["lease_expires_at"])
    heartbeat = scan_worker._CatalogLeaseHeartbeat(job_id, token)

    def run_past_the_original_lease() -> tuple[bool, float]:
        heartbeat.start()
        try:
            deadline = original_expiry + 0.6  # the lease would have lapsed twice over without renewals
            while time.time() < deadline:
                time.sleep(0.02)
            row = _job(db_path, job_id)
            return row["state"] == "running" and float(row["lease_expires_at"]) > time.time(), float(
                row["lease_expires_at"]
            )
        finally:
            heartbeat.stop()

    finished, result, error = run_while_write_path_saturated(run_past_the_original_lease, timeout=15)

    assert finished and error is None
    alive, expiry = result
    assert alive, (
        f"the claim's lease lapsed while bulk writers saturated the write path (expiry {expiry}, started {original_expiry})"
    )
    assert update_job_state(job_id, "running", claim_token=token, lease_seconds=1.0, progress_current=1) is not None
    renewals = [entry for entry in submit_log if entry.lane == "priority"]
    assert renewals, "the lease renewals never used the priority lane"


# ---------------------------------------------------------------------------
# Fencing
# ---------------------------------------------------------------------------


def test_a_stale_catalog_claim_writes_zero_rows_and_its_ops_raise_inside_the_op(
    scan_env, submit_log, mode: str
) -> None:
    from backend.indexer import dispatch_metadata_index_paths
    from backend.metadata_store import (
        activate_rebuild_staging,
        enumerate_to_rebuild_staging,
        reconcile_library_assets,
        recover_stale_jobs,
    )
    from backend.metadata_store.file_index import _bulk_index_records

    db_path, library_id, root, images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    old = claim_next_catalog_job(worker_id="w-old", lease_seconds=60)
    assert old is not None
    old_id, old_token = int(old["id"]), str(old["claim_token"])
    with open_connection(db_path) as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = 1.0 WHERE id = ?", (old_id,))
    assert [job["id"] for job in recover_stale_jobs(reason="lost", live_worker_ids=set())] == [old_id]
    scan_worker.queue_scan(library_id, trigger="manual")
    new = claim_next_catalog_job(worker_id="w-new", lease_seconds=60)
    assert new is not None and str(new["claim_token"]) != old_token
    before = {table: _count(db_path, table) for table in CATALOG_TABLES}
    record = (
        str(root / "ghost.png"), "ghost.png", str(root), "image", 1.0, FIXED_MTIME_NS, 10, 4, 4, time.time(),
        "image/png", None, None,
    )  # fmt: skip

    with pytest.raises(CatalogJobClaimLost):
        _bulk_index_records([record], library_id, claim_job_id=old_id, claim_token=old_token)
    with pytest.raises(CatalogJobClaimLost):
        reconcile_library_assets(library_id, set(), scope_path=root, claim_job_id=old_id, claim_token=old_token)
    with pytest.raises(CatalogJobClaimLost):
        dispatch_metadata_index_paths(
            images, root, catalog_claim_job_id=old_id, catalog_claim_token=old_token, catalog_claim_lease_seconds=60
        )
    with pytest.raises(CatalogJobClaimLost):
        enumerate_to_rebuild_staging(old_id, library_id, [root], old_token, 60)
    with pytest.raises(CatalogJobClaimLost):
        activate_rebuild_staging(old_id, library_id, None, old_token, 60)
    assert update_job_state(old_id, "running", claim_token=old_token) is None
    assert renew_catalog_job_lease(old_id, old_token) is False

    assert {table: _count(db_path, table) for table in CATALOG_TABLES} == before
    assert _job(db_path, old_id)["state"] == "failed"
    assert _job(db_path, int(new["id"]))["claim_token"] == str(new["claim_token"])
    if mode == "writer":
        assert submit_log, "the fenced writes never reached the writer"


def test_rebuild_activation_is_atomic_when_a_step_fails(scan_env, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    import backend.metadata_store.job_store as job_store
    from backend.metadata_store import activate_rebuild_staging, enumerate_to_rebuild_staging

    db_path, library_id, root, images = scan_env
    scan_worker.queue_rebuild(library_id)
    claimed = claim_next_catalog_job(worker_id="w", lease_seconds=60)
    assert claimed is not None
    job_id, token = int(claimed["id"]), str(claimed["claim_token"])
    enumerate_to_rebuild_staging(job_id, library_id, [root], token, 60)
    staged = _count(db_path, "catalog_rebuild_entries")
    assert staged >= len(images)
    assets_before = _count(db_path, "assets")

    def failing_refresh(*_args, **_kwargs):
        raise RuntimeError("injected activation failure")

    with monkeypatch.context() as patch:
        patch.setattr(job_store, "refresh_catalog_job_claim_before_commit_conn", failing_refresh)
        with pytest.raises(RuntimeError, match="injected activation failure"):
            activate_rebuild_staging(job_id, library_id, None, token, 60)

    assert _count(db_path, "assets") == assets_before, "a failed activation changes nothing in the canonical generation"
    assert _count(db_path, "file_index") == 0
    assert _count(db_path, "catalog_rebuild_entries") == staged, "a failed activation keeps its staging rows"
    result = activate_rebuild_staging(job_id, library_id, None, token, 60)  # and the retry still works
    assert result["created"] >= len(images)
    assert _count(db_path, "catalog_rebuild_entries") == 0


def test_a_conflict_raised_inside_the_op_surfaces_unchanged_and_writes_nothing(scan_env, mode: str) -> None:
    db_path, library_id, _root, _images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    running = claim_next_catalog_job(worker_id="w", lease_seconds=60)
    assert running is not None
    jobs_before = _count(db_path, "library_jobs")

    with pytest.raises(CatalogJobConflict) as conflict:
        scan_worker.queue_rebuild(library_id)

    assert conflict.value.args and _count(db_path, "library_jobs") == jobs_before
    assert _job(db_path, int(running["id"]))["state"] == "running"


# ---------------------------------------------------------------------------
# Writer-path equivalents of the direct-transaction fencing/batching internals
# ---------------------------------------------------------------------------


@needs_writer
def test_a_heartbeat_landing_between_the_recovery_read_and_its_write_wins(
    scan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fenced recovery write re-validates the lease inside the op (candidates are read earlier)."""
    import backend.metadata_store.job_store as job_store
    from backend.metadata_store import get_job, recover_stale_jobs

    db_path, library_id, _root, _images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    job = claim_next_catalog_job(worker_id="live-worker", lease_seconds=60)
    assert job is not None
    with open_connection(db_path) as conn:
        conn.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() - 1, job["id"]))
    real_run_write = job_store.run_write

    def racing_run_write(op, **kwargs):
        with open_connection(db_path) as raw:  # the heartbeat renews after the candidates were read
            raw.execute("UPDATE library_jobs SET lease_expires_at = ? WHERE id = ?", (time.time() + 60, job["id"]))
        return real_run_write(op, **kwargs)

    monkeypatch.setattr(job_store, "run_write", racing_run_write)
    assert recover_stale_jobs(live_worker_ids={"live-worker"}) == []
    assert get_job(job["id"])["state"] == "running"


@needs_writer
def test_scan_batches_commit_separately_and_refresh_the_claim_inside_each_op(
    scan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store.file_index as file_index_module

    db_path, library_id, root, _images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    claimed = claim_next_catalog_job(worker_id="w", lease_seconds=5)
    assert claimed is not None
    records = [
        (
            str(root / f"batch_{index}.png"), f"batch_{index}.png", str(root), "image", 1.0, FIXED_MTIME_NS + index,
            10, 4, 4, time.time(), "image/png", None, None,
        )
        for index in range(3)
    ]  # fmt: skip
    monkeypatch.setattr(file_index_module, "_INDEX_WRITE_BATCH_SIZE", 1)
    recording = RecordingWriter(monkeypatch)
    try:
        before_expiry = float(_job(db_path, int(claimed["id"]))["lease_expires_at"])
        file_index_module._bulk_index_records(
            records, library_id, claim_job_id=int(claimed["id"]), claim_token=str(claimed["claim_token"]),
            claim_lease_seconds=60,
        )  # fmt: skip
    finally:
        recording.stop()

    assert len(recording.ops) == 3 and recording.commits >= 1
    for statements in recording.ops:  # every op asserts the claim first and refreshes it before it ends
        assert statements[0].startswith("SELECT id, library_id, claim_token")
        assert statements[-1].lstrip().startswith("UPDATE library_jobs")
    assert float(_job(db_path, int(claimed["id"]))["lease_expires_at"]) > before_expiry + 30


@needs_writer
def test_metadata_job_batches_are_one_op_each_and_refresh_the_claim(scan_env, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.metadata_store.metadata_queue as metadata_queue_module
    from backend.indexer import dispatch_metadata_index_paths

    db_path, library_id, root, images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    claimed = claim_next_catalog_job(worker_id="w", lease_seconds=5)
    assert claimed is not None
    from backend.metadata_store import index_directory_tree

    index_directory_tree(root)
    monkeypatch.setattr(metadata_queue_module, "GALLERY_CATALOG_WRITE_BATCH_SIZE", 3)
    recording = RecordingWriter(monkeypatch)
    try:
        result = dispatch_metadata_index_paths(
            images, root, catalog_claim_job_id=int(claimed["id"]), catalog_claim_token=str(claimed["claim_token"]),
            catalog_claim_lease_seconds=60,
        )  # fmt: skip
    finally:
        recording.stop()

    assert result["queued"] == len(images)
    assert len(recording.ops) == 3  # 8 images in batches of 3
    for statements in recording.ops:
        assert statements[0].startswith("SELECT id, library_id, claim_token")
        assert any(s.lstrip().startswith("UPDATE library_jobs") for s in statements[-2:])
    assert _count(db_path, "metadata_index_jobs") == len(images)


@needs_writer
def test_a_directory_scan_writes_through_one_shared_writer_connection(
    scan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.metadata_store import index_directory_tree

    _db_path, _library_id, root, images = scan_env
    _writer_module().database_writer.reset()
    _writer_module().database_writer.start()
    opened: list[str] = []
    real_connect = sqlite3.connect

    def counting_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        opened.append(threading.current_thread().name)
        return real_connect(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", counting_connect)
        assert index_directory_tree(root) == len(images) + 3  # images, the root and two album folders
    assert opened.count(WRITER_THREAD_NAME) == 1, f"the scan opened connections on {opened}"


# ---------------------------------------------------------------------------
# A saturated writer leaves gaps for other writers
# ---------------------------------------------------------------------------


class _ManualClock:
    """A clock the test advances by hand: elapsed "time" is whatever the ops and the test make it."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _run_saturated_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, yield_ms: int, ops: int, batch_ms: int, op_ms: int
) -> tuple[list[tuple[float, float]], list[int]]:
    """Saturate a private writer with ``ops`` back-to-back one-op batches on a manual clock.

    Each op "works" for ``op_ms`` by advancing the manual clock (no sleeping). When the writer pauses to yield
    the write lock, the test acquires the lock with a second connection (the "other writer"), then advances the
    clock past the pause. Returns each op's ``(start, end)`` clock times and the stretch boundaries (the number
    of ops done when the lock was released and another connection took it).
    """
    from backend.metadata_store.db_writer import DatabaseWriter

    clock = _ManualClock()
    monkeypatch.setattr(DatabaseWriter, "_clock_monotonic", staticmethod(clock))  # the yield/streak clock
    db_file = tmp_path / f"yield_{int(yield_ms)}.db"
    with open_connection(db_file) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    writer = DatabaseWriter(
        connect=lambda: open_connection(db_file, isolation_level=None),
        path_provider=lambda: db_file,
        batch_max=1,  # one op per batch, so the batch (and the streak) boundaries do not depend on timing
        batch_ms=batch_ms,
        yield_ms=yield_ms,
        clock=clock,
    )
    spans: list[tuple[float, float]] = []
    handovers: list[int] = []

    def op(conn: sqlite3.Connection) -> None:
        start = clock.now
        conn.execute("INSERT INTO t DEFAULT VALUES")
        clock.now += op_ms / 1000.0
        spans.append((start, clock.now))

    def another_writer_takes_the_lock() -> None:
        other = sqlite3.connect(db_file, timeout=0, isolation_level=None)  # timeout=0: fail at once if locked
        try:
            other.execute("BEGIN IMMEDIATE")  # raises "database is locked" if the writer still holds the lock
            other.execute("ROLLBACK")
        finally:
            other.close()

    writer.start()
    try:
        futures = [writer.submit(op) for _ in range(ops)]
        per_stretch = -(-batch_ms // op_ms)  # ops per stretch: the first op end at or past batch_ms
        done = 0
        while done < ops:
            # No yield: every op runs without any help from the test. With a yield the writer pauses after each
            # stretch, so the future that closes the stretch is the last one that can complete before we move on.
            done = ops if yield_ms <= 0 else min(done + per_stretch, ops)
            futures[done - 1].result(timeout=60)
            if yield_ms > 0 and done < ops:
                assert len(spans) == done, "the writer must not start the next batch while it yields"
                another_writer_takes_the_lock()
                handovers.append(done)
                clock.now += yield_ms / 1000.0 + 0.001  # the pause is over
    finally:
        writer.stop(timeout=10)
    return spans, handovers


def test_a_saturated_writer_yields_the_write_lock_after_each_stretch_of_back_to_back_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the yield a busy writer never pauses; with it, it releases the lock once per ``batch_ms`` stretch.

    Deterministic replacement for a wall-clock measurement of the longest span a probe was blocked: the writer's
    clock is manual and each op advances it by 4 ms of fake work, so a 30 ms stretch is exactly 8 ops. With a
    60 ms yield the writer must stop after op 8, 16, ... without starting the next op until the clock has moved
    past the pause, and another connection must be able to take the write lock in that gap. Without the yield
    all ops run back to back with no pause at all (the control).
    """
    ops, batch_ms, op_ms = 24, 30, 4
    control_spans, control_handovers = _run_saturated_writer(
        tmp_path, monkeypatch, yield_ms=0, ops=ops, batch_ms=batch_ms, op_ms=op_ms
    )
    assert len(control_spans) == ops and control_handovers == []
    assert all(later[0] == earlier[1] for earlier, later in zip(control_spans, control_spans[1:], strict=False)), (
        "control: a saturated writer without the yield starts every batch the instant the last one ended"
    )

    yield_ms = 60
    spans, handovers = _run_saturated_writer(
        tmp_path, monkeypatch, yield_ms=yield_ms, ops=ops, batch_ms=batch_ms, op_ms=op_ms
    )
    assert handovers == [8, 16], "the lock is released after each 30 ms (8-op) stretch of back-to-back batches"
    assert len(spans) == ops
    for boundary in handovers:
        before, after = spans[boundary - 1], spans[boundary]
        assert after[0] - before[1] >= yield_ms / 1000.0, "the writer paused for the whole yield before the next batch"
    inside_a_stretch = [
        (earlier, later)
        for index, (earlier, later) in enumerate(zip(spans, spans[1:], strict=False), start=1)
        if index not in handovers
    ]
    assert all(later[0] == earlier[1] for earlier, later in inside_a_stretch), "no pause inside a stretch"


# ---------------------------------------------------------------------------
# Maintenance producer gate
# ---------------------------------------------------------------------------


@needs_writer
def test_active_maintenance_holds_back_catalog_writer_ops_until_it_is_released(scan_env) -> None:
    from backend.catalog_maintenance_gate import maintenance_gate

    _db_path, library_id, _root, _images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    db_writer = _writer_module()
    db_writer.database_writer.reset()
    db_writer.database_writer.start()
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def producer() -> None:
        outcome["job"] = claim_next_catalog_job(worker_id="w", lease_seconds=60)
        done.set()

    with maintenance_gate():
        thread = threading.Thread(target=producer, daemon=True)
        thread.start()
        assert not done.wait(0.3), "a catalog claim must wait while maintenance holds the gate"
        assert db_writer.database_writer.stats()["ops"] == 0, "no writer op may bypass the gate"
    assert done.wait(10), "releasing maintenance resumes the paused producer"
    thread.join(10)
    assert outcome["job"] is not None


@needs_writer
def test_an_in_flight_catalog_writer_op_keeps_maintenance_from_starting(
    scan_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.metadata_store.job_store as job_store
    from backend.catalog_maintenance_gate import MaintenanceGateBusy, maintenance_gate
    from backend.metadata_store.file_index import _bulk_index_records

    _db_path, library_id, root, _images = scan_env
    scan_worker.queue_scan(library_id, trigger="manual")
    claimed = claim_next_catalog_job(worker_id="w", lease_seconds=60)
    assert claimed is not None
    parked = Blocker()
    real_refresh = job_store.refresh_catalog_job_claim_before_commit_conn

    def parking_refresh(*args, **kwargs):
        parked.entered.set()
        assert parked.release.wait(30)
        return real_refresh(*args, **kwargs)

    monkeypatch.setattr(job_store, "refresh_catalog_job_claim_before_commit_conn", parking_refresh)
    record = (
        str(root / "parked.png"), "parked.png", str(root), "image", 1.0, FIXED_MTIME_NS, 10, 4, 4, time.time(),
        "image/png", None, None,
    )  # fmt: skip
    thread = threading.Thread(
        target=lambda: _bulk_index_records(
            [record], library_id, claim_job_id=int(claimed["id"]), claim_token=str(claimed["claim_token"])
        ),
        daemon=True,
    )
    thread.start()
    try:
        assert parked.entered.wait(10)
        with pytest.raises(MaintenanceGateBusy), maintenance_gate():
            pass
    finally:
        parked.release.set()
        thread.join(10)
    with maintenance_gate():  # quiesced again once the producer's op finished
        pass


# ---------------------------------------------------------------------------
# Equivalence and the flag
# ---------------------------------------------------------------------------


def _catalog_fingerprint(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    queries = {
        "assets": "SELECT path, name, type, CASE WHEN type = 'folder' THEN NULL ELSE mtime_ns END, size, "
        "metadata_state, offline, deleted_at IS NULL FROM assets ORDER BY path",
        "file_index": "SELECT path, name, type, CASE WHEN type = 'folder' THEN NULL ELSE mtime_ns END, size "
        "FROM file_index ORDER BY path",
        "fts": "SELECT path, name, type FROM file_index_fts ORDER BY path",
        "metadata_jobs": "SELECT path, state, attempts, priority, mtime_ns, size FROM metadata_index_jobs ORDER BY path",
        "jobs": "SELECT type, state, trigger, scope_path, counters, message, error FROM library_jobs ORDER BY id",
        "library": "SELECT state, last_error FROM libraries ORDER BY id",
        "derivatives": "SELECT d.kind, d.variant, d.status FROM asset_derivatives d "
        "JOIN assets a ON a.id = d.asset_id ORDER BY a.path, d.kind, d.variant",
    }
    result: dict[str, list[tuple[Any, ...]]] = {}
    with open_connection(db_path) as conn:
        for name, sql in queries.items():
            result[name] = [tuple(row) for row in conn.execute(sql)]
    return result


def test_scan_and_rebuild_results_are_identical_through_the_writer_and_directly(
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import shutil

    import backend.config as cfg
    import backend.metadata_store as ms

    root = isolated_gallery_root / "photos"
    results: dict[str, list[dict[str, list[tuple[Any, ...]]]]] = {}
    for label, enabled in (("writer", True), ("direct", False)):
        shutil.rmtree(root, ignore_errors=True)  # identical file state for both runs
        root.mkdir()
        images = _populate(root, 12)
        sidecar = root / "album_a" / "img_000.txt"
        run_db = tmp_path / f"{label}.db"
        monkeypatch.setattr(cfg, "GALLERY_METADATA_DB", run_db)
        monkeypatch.setattr(ms, "GALLERY_METADATA_DB", run_db)
        monkeypatch.setattr(ms._db, "_DB_INITIALIZED", False)
        monkeypatch.setattr(ms._db, "_DB_INITIALIZED_PATH", None)
        _writer_module().database_writer.reset()
        if enabled:
            _writer_module().database_writer.start()
        ms.initialize_database()
        library_id = int(create_library([root], name="Equivalence")["id"])
        snapshots = []
        scan_worker.queue_scan(library_id, trigger="manual")
        assert scan_worker.run_once() is True
        snapshots.append(_catalog_fingerprint(run_db))
        for image in images[::2]:  # touch half the images and add a sidecar, then rescan
            os.utime(image, ns=(FIXED_MTIME_NS, FIXED_MTIME_NS + 5_000_000_000))
        sidecar.write_text("a sidecar", encoding="utf-8")
        scan_worker.queue_scan(library_id, trigger="manual")
        assert scan_worker.run_once() is True
        snapshots.append(_catalog_fingerprint(run_db))
        (root / "album_b" / "img_001.png").unlink()
        scan_worker.queue_rebuild(library_id)
        assert scan_worker.run_once() is True
        snapshots.append(_catalog_fingerprint(run_db))
        results[label] = snapshots

    for step, (written, direct) in enumerate(zip(results["writer"], results["direct"], strict=True)):
        for table in written:
            assert written[table] == direct[table], f"step {step}: {table} differs between writer and direct"
    assert results["writer"][2]["jobs"][-1][1] == "succeeded"


def test_with_no_active_writer_the_direct_transactions_are_used_and_the_writer_never_starts(
    scan_env, no_active_writer
) -> None:
    """Converted from ``test_with_the_flag_off_the_direct_transactions_are_used_and_the_writer_never_starts``.

    Same scan, same final state and the writer stays idle; the flag and the ``_DB_LOCK`` ownership assertion
    are gone with the code they covered.
    """
    db_writer = _writer_module()
    db_path, library_id, _root, images = scan_env

    job, _created = scan_worker.queue_scan(library_id, trigger="manual")
    assert scan_worker.run_once() is True

    assert _job(db_path, int(job["id"]))["state"] == "succeeded"
    assert _count(db_path, "metadata_index_jobs") == len(images)
    assert db_writer.database_writer.state == "idle"
    assert db_writer.database_writer.stats()["ops"] == 0
