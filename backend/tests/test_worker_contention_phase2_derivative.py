"""Phase 2.3 regression: derivative job and catalog writes go through the single database writer.

Purpose:
Pin the derivative half of the Phase 2 write-contention work. Before it, the derivative claim, lease
renewal, completion, failure, recovery, scheduling, eviction and reconcile paths each opened their own
``BEGIN IMMEDIATE`` transaction (a reconcile batch held the SQLite write lock for 250 assets x 3
variants), so every one of them queued on SQLite's write lock behind every other writer. Now they are
database writer ops: claims, lease renewals, completions, failures and interactive scheduling use the
priority lane, background scheduling, recovery, eviction and reconcile batches the normal lane, and the
warm-path ``last_accessed_at`` touch on the HTTP request path is fire-and-forget.

Guarantees:
Claim, lease renewal (the heartbeat), completion and failure writes are priority-lane writer ops;
interactive scheduling (job priority 0-1) is a priority op and background scheduling, supervisor
recovery, queued-job reconciliation and reconcile batches are normal-lane ops; a reconcile pass is split
into small ops (no op coalesces more than the op budget of assets) while ``CapacityLedger`` semantics stay
those of one transaction; superseded files are unlinked only after the retiring op resolved
successfully, and a failed commit keeps rows and files; eviction is two ops with the unlink between them;
a stale claim's completion and failure apply zero rows; the warm ready-file lookup never waits for the
writer (the ``last_accessed_at`` touch is a queued normal-lane op that ``release_serving`` flushes); no
derivative writer call is made holding ``_DB_LOCK`` and a whole derivative lifecycle drains through the
writer; the maintenance producer gate still holds back derivative writes; reconcile results are identical
through the writer and through the direct flag-off transactions; with the flag off every path uses the
previous direct transactions and the writer never starts.

Run when:
Changing derivative claim/complete/fail/renew/recover/schedule/reconcile/eviction paths, the lookup
touch, the reconcile op size, the maintenance producer gate, or the writer feature flag.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from PIL import UnidentifiedImageError

import backend.config as config
from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler
from backend.derivative_scheduler.execution import _LeaseHeartbeat
from backend.metadata_store import index_file
from backend.visual_fingerprints import notify_derivative_ready as real_notify_derivative_ready
from tests.conftest import create_test_png
from tests.test_db_writer import Blocker
from tests.worker_contention_support import (
    WRITER_THREAD_NAME,
    RecordingWriter,
    capture_write_threads,
    install_submit_spy,
    run_while_db_lock_held,
    seed_library,
    wait_until,
)

BIG_QUOTA = 1024 * 1024 * 1024
THUMB_VARIANT = str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"])

needs_writer = pytest.mark.skipif(
    not getattr(config, "DB_WRITER_ENABLED", True),
    reason="exercises the writer path; GALLERY_DB_WRITER_ENABLED is off for this run",
)


def _writer_module():
    import backend.metadata_store.db_writer as db_writer_module

    return db_writer_module


def _make_library(root: Path, count: int) -> tuple[int, list[tuple[int, Path]]]:
    """Create a library over ``root`` with ``count`` real indexed PNGs; return ``(library_id, [(asset_id, path)])``."""
    root.mkdir(parents=True, exist_ok=True)
    library_id = seed_library(root)
    probe = DerivativeScheduler(worker_count=1, quota_bytes=BIG_QUOTA)
    images: list[tuple[int, Path]] = []
    for index in range(count):
        image = root / f"img_{index:03d}.png"
        create_test_png(image, size=(48, 32))
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 48, 32)
        asset_id = probe.find_asset_id(image)
        assert asset_id is not None
        images.append((asset_id, image))
    return library_id, images


@pytest.fixture
def library(
    isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_thumbnail_cache: Path, monkeypatch
) -> tuple[Path, int, list[tuple[int, Path]]]:
    """One library with three real indexed images: ``(db_path, library_id, [(asset_id, path)])``."""
    import backend.visual_fingerprints as visual_fingerprints

    monkeypatch.setattr(visual_fingerprints, "notify_derivative_ready", lambda _asset_id: None)
    library_id, images = _make_library(isolated_gallery_root / "photos", 3)
    return isolated_metadata_db, library_id, images


@pytest.fixture
def scheduler() -> DerivativeScheduler:
    return DerivativeScheduler(worker_count=1, quota_bytes=BIG_QUOTA)


@pytest.fixture
def submit_log(monkeypatch: pytest.MonkeyPatch):
    return install_submit_spy(monkeypatch)


@pytest.fixture(params=["writer", "direct"])
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test once through the writer and once through the direct (flag-off) transactions."""
    monkeypatch.setattr(_writer_module(), "DB_WRITER_ENABLED", request.param == "writer")
    return request.param


def _derivative_row(db_path: Path, derivative_id: int) -> dict[str, Any]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()
    assert row is not None
    return dict(row)


def _job_rows(db_path: Path, derivative_id: int) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM derivative_jobs WHERE derivative_id = ? ORDER BY id", (derivative_id,)
            )
        ]


def _make_ready(db_path: Path, derivative_id: int, cache_file: Path, *, byte_size: int = 5) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"x" * byte_size)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = ?, last_accessed_at = NULL "
            "WHERE id = ?",
            (str(cache_file), byte_size, derivative_id),
        )
        conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (derivative_id,))


# ---------------------------------------------------------------------------
# Lanes
# ---------------------------------------------------------------------------


@needs_writer
def test_claims_renewals_completions_and_failures_use_the_priority_lane(
    library, scheduler: DerivativeScheduler, submit_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _library_id, images = library
    (first_id, _), (second_id, _), (third_id, _) = images
    ids = [scheduler.schedule_derivative(asset_id, "thumbnail", THUMB_VARIANT, 3) for asset_id, _ in images]
    assert len(set(ids)) == 3
    lanes: dict[str, list[str]] = {}

    def lanes_of(label: str, action) -> Any:
        start = len(submit_log)
        result = action()
        lanes[label] = [entry.lane for entry in submit_log[start:]]
        return result

    job_one = lanes_of("claim", lambda: scheduler._claim_job("worker-a"))
    job_two = scheduler._claim_job("worker-b")
    job_three = scheduler._claim_job("worker-c")
    assert job_one is not None and job_two is not None and job_three is not None
    lanes_of("renew", lambda: scheduler._renew_lease(job_one["job_id"], job_one["claim_token"]))
    lanes_of("complete", lambda: scheduler._run_job(job_one))

    import backend.thumbnails as thumbnails

    def failing_generate(*_args, **_kwargs):
        raise UnidentifiedImageError("not an image")

    monkeypatch.setattr(thumbnails, "generate_derivative", failing_generate)
    lanes_of("fail", lambda: scheduler._run_job(job_two))

    assert _derivative_row(db_path, job_one["id"])["status"] == "ready"
    assert _derivative_row(db_path, job_two["id"])["status"] == "failed"
    for label in ("claim", "renew", "fail"):
        assert lanes[label], f"{label} never reached the writer"
        assert set(lanes[label]) == {"priority"}, f"{label} used lanes {lanes[label]}"
    assert len(lanes["claim"]) == 1, "one writer op per claim"
    assert lanes["complete"] and lanes["complete"][0] == "priority", "the completion write is a priority op"
    assert set(lanes["complete"]) <= {"priority", "normal"}

    # A heartbeat renewal is the same priority op (WK-02 root cause: renewals must never queue behind readers).
    heartbeat_log: list[str] = []
    start = len(submit_log)
    beat = _LeaseHeartbeat(scheduler, job_three["job_id"], job_three["claim_token"], 0.05)
    beat.start()
    try:
        assert wait_until(lambda: len(submit_log) > start, timeout=10)
    finally:
        beat.stop()
    heartbeat_log.extend(entry.lane for entry in submit_log[start:])
    assert heartbeat_log and set(heartbeat_log) == {"priority"}


@needs_writer
def test_interactive_scheduling_is_a_priority_op_and_background_scheduling_a_normal_op(
    library, scheduler: DerivativeScheduler, submit_log
) -> None:
    _db_path, _library_id, images = library
    start = len(submit_log)
    scheduler.schedule_derivative(images[0][0], "thumbnail", THUMB_VARIANT, 0)
    interactive = [entry.lane for entry in submit_log[start:]]
    start = len(submit_log)
    scheduler.schedule_derivative(images[1][0], "thumbnail", THUMB_VARIANT, 3)
    background = [entry.lane for entry in submit_log[start:]]

    assert interactive and set(interactive) == {"priority"}, interactive
    assert background and set(background) == {"normal"}, background


@needs_writer
def test_reconcile_recovery_and_queued_job_reconciliation_use_the_normal_lane(
    library, scheduler: DerivativeScheduler, submit_log
) -> None:
    db_path, library_id, images = library
    start = len(submit_log)
    summary = scheduler.reconcile_desired_derivatives(
        library_id=library_id, reason="manual_generate", respect_warm_policy=False
    )
    reconcile_lanes = [entry.lane for entry in submit_log[start:]]
    assert summary.created_jobs == len(images) * sum(len(v) for v in DERIVATIVE_VARIANTS.values())
    assert reconcile_lanes and set(reconcile_lanes) == {"normal"}, reconcile_lanes

    claimed = scheduler._claim_job("worker-a")
    assert claimed is not None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE derivative_jobs SET lease_expires_at = julianday('now') - 1 WHERE id = ?", (claimed["job_id"],)
        )
        # A queued job whose asset is gone must be terminalized by the queued-job reconciliation.
        conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (images[2][0],))
    start = len(submit_log)
    assert scheduler._recover_running_jobs(expired_only=True) == 1
    recovery_lanes = [entry.lane for entry in submit_log[start:]]
    start = len(submit_log)
    scheduler._reconcile_queued_jobs()
    queued_lanes = [entry.lane for entry in submit_log[start:]]

    assert recovery_lanes and set(recovery_lanes) == {"normal"}, recovery_lanes
    assert queued_lanes and set(queued_lanes) == {"normal"}, queued_lanes
    assert _job_rows(db_path, claimed["id"])[-1]["state"] == "queued"


# ---------------------------------------------------------------------------
# Reconcile batches stay small
# ---------------------------------------------------------------------------


@needs_writer
def test_a_reconcile_pass_is_split_into_small_writer_ops(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.derivative_scheduler.reconcile as reconcile_module

    library_id, images = _make_library(isolated_gallery_root / "many", 130)
    monkeypatch.setattr(reconcile_module, "DERIVATIVE_RECONCILE_BATCH_SIZE", 250)
    monkeypatch.setattr(reconcile_module, "DERIVATIVE_RECONCILE_YIELD_SECONDS", 0)
    recording = RecordingWriter(monkeypatch)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=BIG_QUOTA)
    variants_per_asset = sum(len(v) for v in DERIVATIVE_VARIANTS.values())
    try:
        summary = scheduler.reconcile_desired_derivatives(
            library_id=library_id, reason="manual_generate", respect_warm_policy=False
        )
    finally:
        recording.stop()

    assert summary.created_jobs == len(images) * variants_per_asset
    job_inserts = [count for count in recording.writes_per_op("INSERT INTO derivative_jobs") if count]
    assert len(job_inserts) >= 3, f"a 130-asset pass must be split into several ops; saw {job_inserts}"
    assert sum(job_inserts) == len(images) * variants_per_asset
    assert max(job_inserts) <= 50 * variants_per_asset, f"one op coalesced too many identities: {job_inserts}"


# ---------------------------------------------------------------------------
# Fencing: a stale claim writes nothing
# ---------------------------------------------------------------------------


def test_a_stale_claims_completion_and_failure_apply_zero_rows(
    library, scheduler: DerivativeScheduler, submit_log, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    db_path, _library_id, images = library
    asset_id = images[0][0]
    scheduler.schedule_derivative(asset_id, "thumbnail", THUMB_VARIANT, 3)
    old = scheduler._claim_job("worker-old")
    assert old is not None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE derivative_jobs SET lease_expires_at = julianday('now') - 1 WHERE id = ?", (old["job_id"],)
        )
    assert scheduler._recover_running_jobs(expired_only=True) == 1
    new = scheduler._claim_job("worker-new")
    assert new is not None and new["claim_token"] != old["claim_token"] and new["job_id"] == old["job_id"]

    scheduler._run_job(old)  # renders fine, but its completion is fenced

    row = _job_rows(db_path, old["id"])[-1]
    assert row["state"] == "running" and row["claim_token"] == new["claim_token"]
    assert _derivative_row(db_path, old["id"])["status"] == "running"

    import backend.thumbnails as thumbnails

    def failing_generate(*_args, **_kwargs):
        raise UnidentifiedImageError("stale failure")

    monkeypatch.setattr(thumbnails, "generate_derivative", failing_generate)
    scheduler._run_job(old)  # its failure write is fenced too

    row = _job_rows(db_path, old["id"])[-1]
    assert row["state"] == "running" and row["claim_token"] == new["claim_token"] and row["error"] is None
    assert _derivative_row(db_path, old["id"])["status"] == "running"
    if mode == "writer":
        assert [entry for entry in submit_log if entry.lane == "priority"], "the fenced writes never used the writer"


# ---------------------------------------------------------------------------
# Lease heartbeat vs _DB_LOCK holders (WK-02 root cause)
# ---------------------------------------------------------------------------


def test_the_lease_heartbeat_renews_through_the_writer_while_another_thread_holds_the_db_lock(
    library, scheduler: DerivativeScheduler, submit_log, mode: str
) -> None:
    db_path, _library_id, images = library
    scheduler.schedule_derivative(images[0][0], "thumbnail", THUMB_VARIANT, 3)
    job = scheduler._claim_job("worker")
    assert job is not None
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE derivative_jobs SET lease_expires_at = julianday('now') + 1.0 / 86400 WHERE id = ?",
            (job["job_id"],),
        )

    def renewed() -> bool:
        with sqlite3.connect(db_path) as conn:
            return bool(
                conn.execute(
                    "SELECT lease_expires_at > julianday('now') + 100.0 / 86400 FROM derivative_jobs WHERE id = ?",
                    (job["job_id"],),
                ).fetchone()[0]
            )

    heartbeat = _LeaseHeartbeat(scheduler, job["job_id"], job["claim_token"], 0.05)

    def hold_lock_until_renewed() -> bool:
        heartbeat.start()
        try:
            return wait_until(renewed, timeout=20)
        finally:
            heartbeat.stop()

    finished, result, error = run_while_db_lock_held(hold_lock_until_renewed, timeout=25)

    assert finished and error is None
    assert result is True, "the heartbeat could not renew while another thread held _DB_LOCK"
    if mode == "writer":
        renewals = [entry for entry in submit_log if entry.thread.startswith("derivative-lease")]
        assert renewals and {entry.lane for entry in renewals} == {"priority"}
        assert not [entry for entry in renewals if entry.holds_db_lock]


# ---------------------------------------------------------------------------
# End to end through the writer, no _DB_LOCK
# ---------------------------------------------------------------------------


@needs_writer
def test_the_derivative_workers_drain_every_job_through_the_writer_without_holding_the_db_lock(
    library, submit_log
) -> None:
    db_path, library_id, images = library
    scheduler = DerivativeScheduler(worker_count=2, quota_bytes=BIG_QUOTA)
    expected = len(images) * sum(len(v) for v in DERIVATIVE_VARIANTS.values())
    summary = scheduler.reconcile_desired_derivatives(
        library_id=library_id, reason="manual_generate", respect_warm_policy=False
    )
    assert summary.created_jobs == expected
    scheduler.start()
    try:

        def all_ready() -> bool:
            with sqlite3.connect(db_path) as conn:
                return (
                    conn.execute("SELECT count(*) FROM asset_derivatives WHERE status = 'ready'").fetchone()[0]
                    == expected
                )

        assert wait_until(all_ready, timeout=60), "the workers did not finish every derivative"
    finally:
        scheduler.stop()

    assert submit_log, "the derivative workers never used the writer"
    assert not [entry for entry in submit_log if entry.holds_db_lock], "a writer call was made holding _DB_LOCK"
    with sqlite3.connect(db_path) as conn:
        done = conn.execute("SELECT count(*) FROM derivative_jobs WHERE state = 'done'").fetchone()[0]
        files = [row[0] for row in conn.execute("SELECT cache_path FROM asset_derivatives")]
    assert done == expected and all(Path(path).is_file() for path in files)


def test_a_whole_derivative_lifecycle_completes_while_another_thread_holds_the_db_lock(
    library, scheduler: DerivativeScheduler, mode: str
) -> None:
    """Claim, render (including its dimension upsert), completion and quota enforcement need no `_DB_LOCK`."""
    db_path, _library_id, images = library
    derivative_id = scheduler.schedule_derivative(images[0][0], "thumbnail", THUMB_VARIANT, 3)

    def lifecycle() -> None:
        job = scheduler._claim_job("worker")
        assert job is not None
        scheduler._run_job(job)

    finished, _result, error = run_while_db_lock_held(lifecycle, timeout=1.0 if mode == "direct" else 20.0)

    assert error is None
    if mode == "writer":
        assert finished, "the writer path must not queue behind _DB_LOCK"
    else:
        assert not finished, "control: the direct dimension upsert does queue behind _DB_LOCK"
    # run_while_db_lock_held releases the holder afterwards, so the direct path completes too.
    assert _derivative_row(db_path, derivative_id)["status"] == "ready"


@needs_writer
def test_a_derivative_lifecycle_writes_only_on_the_writer_thread(
    library, scheduler: DerivativeScheduler, submit_log, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scheduling, reconcile, claim, render, completion, recovery, retirement and eviction: no write elsewhere."""
    db_path, library_id, images = library
    with capture_write_threads(monkeypatch) as writes:
        scheduler.schedule_derivative(images[0][0], "thumbnail", THUMB_VARIANT, 0)
        scheduler.reconcile_desired_derivatives(
            library_id=library_id, reason="manual_generate", respect_warm_policy=False
        )
        job = scheduler._claim_job("worker")
        assert job is not None
        scheduler._run_job(job)  # render (dimension upsert), completion, quota enforcement
        scheduler._claim_job("worker-2")
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE derivative_jobs SET lease_expires_at = julianday('now') - 1 WHERE state = 'running'")
            conn.execute("UPDATE assets SET offline = 1 WHERE id = ?", (images[2][0],))
        scheduler._recover_running_jobs(expired_only=True)
        scheduler._reconcile_queued_jobs()
        scheduler.retire_superseded_derivatives()
        scheduler.repair_derivative_consistency([job["id"]])
        scheduler.quota_bytes = 1
        scheduler._reserve_capacity(1)

    test_setup = ("UPDATE derivative_jobs SET lease_expires_at = julianday('now') - 1", "UPDATE assets SET offline = 1")
    off_writer = [
        (thread, text.split("(")[0][:50])
        for thread, text in writes
        if thread != WRITER_THREAD_NAME and not text.startswith(test_setup)
    ]
    assert not off_writer, f"derivative writes outside the database writer: {off_writer[:12]}"
    assert any("derivative_jobs" in text for thread, text in writes if thread == WRITER_THREAD_NAME)
    assert any("image_metadata" in text for thread, text in writes if thread == WRITER_THREAD_NAME)


@needs_writer
def test_the_derivative_ready_hook_invalidates_through_the_writer_and_schedules_after_the_op(
    library, submit_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``notify_derivative_ready`` (called by a derivative worker per completed derivative) was a direct write."""
    import backend.visual_fingerprints as visual_fingerprints

    _db_path, library_id, images = library
    monkeypatch.setattr(visual_fingerprints, "GALLERY_RELATED_VISUAL_ENABLED", True)
    scheduled: list[tuple[int, str]] = []
    monkeypatch.setattr(
        visual_fingerprints,
        "schedule_visual_fingerprint_backfill",
        lambda lib: scheduled.append((lib, threading.current_thread().name)),
    )
    start = len(submit_log)

    real_notify_derivative_ready(images[0][0])

    entries = submit_log[start:]
    assert entries and {entry.lane for entry in entries} == {"normal"}
    assert not [entry for entry in entries if entry.holds_db_lock]
    assert len(scheduled) == 1 and scheduled[0][0] == library_id
    assert scheduled[0][1] != WRITER_THREAD_NAME, "the backfill scheduling takes _DB_LOCK: never inside the op"


# ---------------------------------------------------------------------------
# Superseded retirement and eviction: unlink only after the op resolved
# ---------------------------------------------------------------------------


def _seed_superseded_ready(db_path: Path, asset_id: int, cache_file: Path) -> int:
    """Insert a ready derivative of an old source identity of ``asset_id`` with a file on disk."""
    with sqlite3.connect(db_path) as conn:
        mtime_ns, size = conn.execute("SELECT mtime_ns, size FROM assets WHERE id = ?", (asset_id,)).fetchone()
        derivative_id = int(
            conn.execute(
                """
                INSERT INTO asset_derivatives (
                  asset_id, kind, variant, source_mtime_ns, source_size, format, quality, max_long_edge,
                  status, cache_path, byte_size
                ) VALUES (?, 'thumbnail', ?, ?, ?, 'webp', 82, 128, 'ready', ?, 5)
                """,
                (asset_id, THUMB_VARIANT, mtime_ns - 7, size, str(cache_file)),
            ).lastrowid
        )
        conn.execute(
            "INSERT INTO derivative_jobs (derivative_id, priority, state) VALUES (?, 3, 'done')", (derivative_id,)
        )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(b"stale")
    return derivative_id


@needs_writer
def test_retired_files_are_unlinked_only_after_the_op_resolved_successfully(
    library, scheduler: DerivativeScheduler, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _library_id, images = library
    cache_file = tmp_path / "cache" / "old_identity.webp"
    derivative_id = _seed_superseded_ready(db_path, images[0][0], cache_file)
    recording = RecordingWriter(monkeypatch)
    observed: list[tuple[int, bool]] = []
    real_discard = scheduler._discard_retired_files

    def watching_discard(paths):
        paths = list(paths)
        observed.append((recording.commits, cache_file.exists()))
        return real_discard(paths)

    monkeypatch.setattr(scheduler, "_discard_retired_files", watching_discard)
    try:
        recording.commit_failures.append(sqlite3.OperationalError("disk I/O error"))
        with pytest.raises(sqlite3.OperationalError):
            scheduler.retire_superseded_derivatives()
        assert cache_file.exists(), "a retirement that did not commit must keep its file"
        assert _derivative_row(db_path, derivative_id)["status"] == "ready"
        assert observed == [], "the unlink step must not run when the op failed"

        commits_before = recording.commits
        assert scheduler.retire_superseded_derivatives() == 1
    finally:
        recording.stop()

    assert _derivative_row(db_path, derivative_id)["status"] == "skipped"
    assert not cache_file.exists()
    assert observed and observed[0][0] > commits_before and observed[0][1] is True, (
        "the file must still exist, and the retiring batch be committed, when the unlink step starts"
    )


@needs_writer
def test_eviction_is_two_writer_ops_with_the_unlink_between_them(
    library, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, _library_id, images = library
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=800)
    ids = [scheduler.schedule_derivative(asset_id, "thumbnail", THUMB_VARIANT, 3) for asset_id, _ in images[:2]]
    files = [tmp_path / "ev" / f"{index}.webp" for index in range(2)]
    for derivative_id, cache_file in zip(ids, files, strict=True):
        _make_ready(db_path, derivative_id, cache_file, byte_size=400)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE asset_derivatives SET last_accessed_at = 2460000.0 WHERE id = ?", (ids[0],))
        conn.execute("UPDATE asset_derivatives SET last_accessed_at = 2460001.0 WHERE id = ?", (ids[1],))
    recording = RecordingWriter(monkeypatch)
    try:
        assert scheduler._reserve_capacity(400) is True
    finally:
        recording.stop()

    assert len(recording.ops) == 2, f"expected select+evict then finalize ops, saw {len(recording.ops)}"
    assert not files[0].exists() and files[1].exists()
    first = _derivative_row(db_path, ids[0])
    assert first["status"] == "evicted" and first["cache_path"] is None
    assert _derivative_row(db_path, ids[1])["status"] == "ready"


# ---------------------------------------------------------------------------
# HTTP request path: the warm lookup never waits for the writer
# ---------------------------------------------------------------------------


@needs_writer
def test_the_warm_ready_lookup_does_not_wait_for_a_busy_writer_and_the_touch_is_flushed_on_release(
    library, scheduler: DerivativeScheduler, submit_log, tmp_path: Path
) -> None:
    db_path, _library_id, images = library
    asset_id, image = images[0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", THUMB_VARIANT, 3)
    cache_file = tmp_path / "warm" / "ready.webp"
    _make_ready(db_path, derivative_id, cache_file)
    stat = image.stat()
    writer = _writer_module().database_writer
    blocker = Blocker()
    parked = writer.submit(blocker, lane="normal")  # the writer is now inside a long batch
    outcome: dict[str, Any] = {}
    done = threading.Event()
    start = len(submit_log)

    def request() -> None:
        outcome["ready"] = scheduler.acquire_ready_derivative(
            asset_id, "thumbnail", THUMB_VARIANT, source_mtime_ns=stat.st_mtime_ns, source_size=stat.st_size
        )
        done.set()

    try:
        assert blocker.entered.wait(10)
        thread = threading.Thread(target=request, daemon=True)
        thread.start()
        returned_while_blocked = done.wait(2.0)
        touched_while_blocked = _derivative_row(db_path, derivative_id)["last_accessed_at"]
    finally:
        blocker.release.set()
    parked.result(timeout=10)
    thread.join(10)

    assert returned_while_blocked, "a warm lookup must not wait for the writer (HTTP latency)"
    assert outcome["ready"] is not None and outcome["ready"]["cache_path"] == str(cache_file)
    assert touched_while_blocked is None, "the touch is queued behind the busy writer, not applied inline"
    touches = submit_log[start:]
    assert touches and {entry.lane for entry in touches} == {"normal"}
    scheduler.release_serving(str(cache_file))  # flushes the pending touch before the lease is dropped
    assert _derivative_row(db_path, derivative_id)["last_accessed_at"] is not None


@needs_writer
def test_a_warm_lookup_skips_the_touch_while_maintenance_is_active(
    library, scheduler: DerivativeScheduler, submit_log, tmp_path: Path
) -> None:
    from backend.catalog_maintenance_gate import maintenance_gate

    db_path, _library_id, images = library
    asset_id, image = images[0]
    derivative_id = scheduler.schedule_derivative(asset_id, "thumbnail", THUMB_VARIANT, 3)
    cache_file = tmp_path / "warm" / "maintenance.webp"
    _make_ready(db_path, derivative_id, cache_file)
    stat = image.stat()
    start = len(submit_log)
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def request() -> None:
        outcome["ready"] = scheduler.get_ready_derivative(
            asset_id, "thumbnail", THUMB_VARIANT, source_mtime_ns=stat.st_mtime_ns, source_size=stat.st_size
        )
        done.set()

    with maintenance_gate():
        thread = threading.Thread(target=request, daemon=True)
        thread.start()
        assert done.wait(5), "the request path must never wait for maintenance"
    thread.join(10)

    assert outcome["ready"] is not None
    assert submit_log[start:] == [], "no writer op may be queued while maintenance holds the gate"
    assert _derivative_row(db_path, derivative_id)["last_accessed_at"] is None


# ---------------------------------------------------------------------------
# Maintenance producer gate
# ---------------------------------------------------------------------------


@needs_writer
def test_active_maintenance_holds_back_derivative_writer_ops_until_it_is_released(
    library, scheduler: DerivativeScheduler
) -> None:
    from backend.catalog_maintenance_gate import maintenance_gate

    db_writer = _writer_module()
    db_writer.database_writer.reset()
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def producer() -> None:
        outcome["claim"] = scheduler._claim_job("worker")
        done.set()

    with maintenance_gate():
        thread = threading.Thread(target=producer, daemon=True)
        thread.start()
        assert not done.wait(0.3), "a derivative claim must wait while maintenance holds the gate"
        assert db_writer.database_writer.stats()["ops"] == 0, "no writer op may bypass the gate"
    assert done.wait(10), "releasing maintenance resumes the paused producer"
    thread.join(10)
    assert outcome["claim"] is None  # nothing was queued
    assert db_writer.database_writer.stats()["ops"] >= 1


@needs_writer
def test_an_in_flight_derivative_writer_op_keeps_maintenance_from_starting(
    library, scheduler: DerivativeScheduler, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.catalog_maintenance_gate import MaintenanceGateBusy, maintenance_gate

    _db_path, _library_id, images = library
    scheduler.schedule_derivative(images[0][0], "thumbnail", THUMB_VARIANT, 3)
    job = scheduler._claim_job("worker")
    assert job is not None
    parked = Blocker()
    real_estimate = DerivativeScheduler._estimate_new_derivative_bytes
    outcome: dict[str, Any] = {}

    def parking_estimate(self, conn):
        parked.entered.set()
        assert parked.release.wait(30)
        return real_estimate(self, conn)

    # The renewal op itself cannot be parked; park a priority-lane scheduling op instead.
    monkeypatch.setattr(DerivativeScheduler, "_estimate_new_derivative_bytes", parking_estimate)

    def producer() -> None:
        outcome["id"] = scheduler.schedule_derivative(images[1][0], "thumbnail", THUMB_VARIANT, 0)

    thread = threading.Thread(target=producer, daemon=True)
    thread.start()
    try:
        assert parked.entered.wait(10)
        with pytest.raises(MaintenanceGateBusy), maintenance_gate():
            pass
    finally:
        parked.release.set()
        thread.join(10)
    assert "id" in outcome
    with maintenance_gate():  # quiesced again once the producer finished
        pass


# ---------------------------------------------------------------------------
# Equivalence and the flag
# ---------------------------------------------------------------------------


def _fingerprint(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    from tests.test_worker_contention_wk03 import _database_fingerprint

    return _database_fingerprint(db_path)


def test_reconcile_results_are_identical_through_the_writer_and_directly(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    isolated_thumbnail_cache: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import asdict

    from tests.test_worker_contention_wk03 import (
        _candidates,
        _copy_database,
        _seed_existing_state,
        _use_database,
    )

    library_id, images = _make_library(isolated_gallery_root / "eq", 36)
    assets = []
    with sqlite3.connect(isolated_metadata_db) as conn:
        for asset_id, image in images:
            stat = image.stat()
            assets.append((asset_id, str(image), stat.st_mtime_ns, stat.st_size))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    _seed_existing_state(isolated_metadata_db, assets, tmp_path / "cache")
    assert _candidates(assets)
    results = {}
    for label, enabled in (("writer", True), ("direct", False)):
        run_db = _copy_database(isolated_metadata_db, tmp_path / f"{label}.db")
        _use_database(monkeypatch, run_db)
        monkeypatch.setattr(_writer_module(), "DB_WRITER_ENABLED", enabled)
        _writer_module().database_writer.reset()
        sched = DerivativeScheduler(worker_count=1, quota_bytes=60 * 64 * 1024)
        summary = sched.reconcile_desired_derivatives(
            library_id=library_id, reason="integrity", respect_warm_policy=False, retry_failed=True
        )
        results[label] = (asdict(summary), _fingerprint(run_db))

    assert results["writer"] == results["direct"]
    assert results["writer"][0]["created_jobs"] > 0


def test_with_the_flag_off_the_direct_transactions_are_used_and_the_writer_never_starts(
    library, scheduler: DerivativeScheduler, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_writer = _writer_module()
    monkeypatch.setattr(db_writer, "DB_WRITER_ENABLED", False)
    db_writer.database_writer.reset()
    db_path, library_id, images = library

    derivative_id = scheduler.schedule_derivative(images[0][0], "thumbnail", THUMB_VARIANT, 0)
    summary = scheduler.reconcile_desired_derivatives(
        library_id=library_id, reason="manual_generate", respect_warm_policy=False
    )
    job = scheduler._claim_job("worker")
    assert job is not None
    scheduler._run_job(job)
    started = time.monotonic()
    assert scheduler.retire_superseded_derivatives() == 0
    assert time.monotonic() - started < 10

    assert summary.created_jobs > 0
    assert _derivative_row(db_path, job["id"])["status"] == "ready"
    assert derivative_id
    assert db_writer.database_writer.state == "idle"
    assert db_writer.database_writer.stats()["ops"] == 0
