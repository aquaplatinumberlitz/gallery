"""Phase 5 lease, shutdown, and worker resilience coverage.

Purpose:
Verify the Phase 5 worker-lifecycle hardening: a fenced lease heartbeat keeps a
long render from being duplicated by expired-claim recovery while the heartbeat
is healthy, the heartbeat stops before terminal persistence (done/failed/skipped/
retry/unexpected), obsolete tokens cannot renew a claim, and stop/start restores
the configured worker count without abandoning in-flight jobs or permanently
refusing restart because a stale thread object remains.

Guarantees:
* A render longer than the configured lease is not duplicated while its heartbeat
  renews the lease.
* The heartbeat renews only a still-running row owned by the same claim token.
* ``stop()`` records whether shutdown completed cleanly; ``start()`` restores
  missing worker slots after an incomplete stop.

Run when:
Changing derivative_scheduler.py lease/heartbeat, worker lifecycle, or
start()/stop() thread bookkeeping.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

import backend.derivative_scheduler as scheduler_module
import backend.thumbnails as thumbnails_module
from backend.config import DERIVATIVE_VARIANTS
from backend.derivative_scheduler import DerivativeScheduler, _LeaseHeartbeat
from backend.metadata_store import get_asset_folder_listing, index_file, register_library
from tests.conftest import create_test_png


def _catalog_image(root: Path) -> tuple[Path, int, int]:
    library_id = int(register_library(root)["id"])
    image = root / "source.png"
    create_test_png(image, size=(80, 60))
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "photo", stat.st_mtime, stat.st_size, 80, 60)
    listing = get_asset_folder_listing(root)
    assert listing is not None
    return image, listing["media"][0].asset_id, library_id


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def short_lease(monkeypatch: pytest.MonkeyPatch):
    """Use production-shaped short lease/heartbeat intervals for deterministic tests."""
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_JOB_LEASE_SECONDS", 1)
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_LEASE_HEARTBEAT_SECONDS", 0.3)
    yield


def test_lease_heartbeat_prevents_duplicate_render_after_lease_expiry(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    short_lease,
    monkeypatch: pytest.MonkeyPatch,
):
    """A healthy heartbeat keeps a long render from being recovered as a duplicate."""
    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=1)

    finished = threading.Event()

    def slow_render(*args, **kwargs):
        time.sleep(2.0)  # Longer than the 1s lease, but the heartbeat renews it.
        finished.set()
        return b"rendered-derivative-bytes"

    monkeypatch.setattr(thumbnails_module, "generate_derivative", slow_render)

    derivative_id = scheduler.schedule_derivative(
        asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"])
    )
    job = scheduler._claim_job()
    assert job is not None

    render_thread = threading.Thread(target=scheduler._run_job, args=(job,), name="render-under-test")
    render_thread.start()

    # Let the render run well past the original lease while the heartbeat renews.
    time.sleep(1.5)
    assert scheduler._recover_running_jobs(expired_only=True) == 0
    with _connect(isolated_metadata_db) as conn:
        running = conn.execute("SELECT state FROM derivative_jobs WHERE id = ?", (job["job_id"],)).fetchone()[0]
        assert running == "running"

    finished.wait(timeout=5)
    render_thread.join(timeout=5)

    with _connect(isolated_metadata_db) as conn:
        job_row = conn.execute(
            "SELECT state FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
            (derivative_id,),
        ).fetchone()
        derivative = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()
    assert job_row["state"] == "done"
    assert derivative["status"] == "ready"


def test_heartbeat_renews_lease_during_long_render_and_stops_after_done(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    short_lease,
    monkeypatch: pytest.MonkeyPatch,
):
    """The heartbeat renews while rendering and stops once the job completes."""
    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=1)

    renew_calls: list[float] = []
    original_renew = scheduler._renew_lease

    def counting_renew(job_id, claim_token):
        renew_calls.append(time.monotonic())
        return original_renew(job_id, claim_token)

    monkeypatch.setattr(scheduler, "_renew_lease", counting_renew)

    def slow_render(*args, **kwargs):
        time.sleep(2.0)
        return b"bytes"

    monkeypatch.setattr(thumbnails_module, "generate_derivative", slow_render)

    derivative_id = scheduler.schedule_derivative(
        asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"])
    )
    job = scheduler._claim_job()
    render_thread = threading.Thread(target=scheduler._run_job, args=(job,))
    render_thread.start()

    time.sleep(1.0)
    during_render = len(renew_calls)
    assert during_render >= 1  # Heartbeat renewed at least once during the render.

    render_thread.join(timeout=5)
    renew_after_completion = len(renew_calls)
    time.sleep(1.0)  # Longer than one heartbeat interval past completion.
    assert len(renew_calls) == renew_after_completion  # Heartbeat stopped; no further renewals.

    with _connect(isolated_metadata_db) as conn:
        assert (
            conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()[0] == "ready"
        )


def test_heartbeat_stops_on_failed_render(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    short_lease,
    monkeypatch: pytest.MonkeyPatch,
):
    """A heartbeat failure path still stops the heartbeat and lets handling persist."""
    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=1)

    renew_calls: list[int] = []
    original_renew = scheduler._renew_lease

    def counting_renew(job_id, claim_token):
        renew_calls.append(job_id)
        return original_renew(job_id, claim_token)

    monkeypatch.setattr(scheduler, "_renew_lease", counting_renew)

    def failing_render(*args, **kwargs):
        time.sleep(1.0)
        raise OSError("transient render failure")

    monkeypatch.setattr(thumbnails_module, "generate_derivative", failing_render)

    derivative_id = scheduler.schedule_derivative(
        asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"])
    )
    job = scheduler._claim_job()
    render_thread = threading.Thread(target=scheduler._run_job, args=(job,))
    render_thread.start()
    time.sleep(0.6)
    during_render = len(renew_calls)
    assert during_render >= 1

    render_thread.join(timeout=5)
    renew_after_failure = len(renew_calls)
    time.sleep(1.0)
    assert len(renew_calls) == renew_after_failure  # Heartbeat stopped after failure handling.

    with _connect(isolated_metadata_db) as conn:
        # Transient OSError retries: the derivative returns to queued, not stuck running.
        state = conn.execute(
            "SELECT state FROM derivative_jobs WHERE derivative_id = ? ORDER BY id DESC LIMIT 1",
            (derivative_id,),
        ).fetchone()[0]
        assert state in {"queued", "failed"}


def test_heartbeat_with_obsolete_token_updates_zero_rows(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """A renewal carrying a stale claim token cannot extend or overwrite the claim."""
    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    job = scheduler._claim_job()
    assert job is not None

    with _connect(isolated_metadata_db) as conn:
        conn.execute(
            "UPDATE derivative_jobs SET claim_token = 'other-token' WHERE id = ?",
            (job["job_id"],),
        )

    assert scheduler._renew_lease(job["job_id"], job["claim_token"]) is False
    with _connect(isolated_metadata_db) as conn:
        row = conn.execute(
            "SELECT claim_token, state FROM derivative_jobs WHERE id = ?",
            (job["job_id"],),
        ).fetchone()
    assert row["claim_token"] == "other-token"
    assert row["state"] == "running"


def test_heartbeat_thread_is_daemon_and_bounded(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    """The heartbeat thread is owned by job/claim and does not block process exit."""
    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler()
    scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))
    job = scheduler._claim_job()
    heartbeat = _LeaseHeartbeat(scheduler, job["job_id"], job["claim_token"], interval_seconds=0.2)
    assert heartbeat._thread.daemon is True
    heartbeat.start()
    assert heartbeat._thread.is_alive()
    heartbeat.stop()
    heartbeat._thread.join(timeout=1)
    assert not heartbeat._thread.is_alive()


def test_start_after_incomplete_stop_restores_workers_and_preserves_jobs(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A restart after an incomplete stop restores the worker count and keeps jobs."""
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_RECONCILE_ENABLED", False)
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 0.3)

    _image, asset_id, _library_id = _catalog_image(isolated_gallery_root)
    scheduler = DerivativeScheduler(worker_count=2)

    blocked = threading.Event()

    def blocking_render(*args, **kwargs):
        blocked.wait()
        return b"bytes"

    monkeypatch.setattr(thumbnails_module, "generate_derivative", blocking_render)

    scheduler.start()
    assert scheduler.alive_worker_count() == 2

    scheduler.schedule_derivative(asset_id, "thumbnail", str(DERIVATIVE_VARIANTS["thumbnail"][0]["name"]))

    # Wait until one worker is mid-render and holding the claim.
    for _ in range(100):
        with _connect(isolated_metadata_db) as conn:
            if conn.execute("SELECT count(*) FROM derivative_jobs WHERE state = 'running'").fetchone()[0] >= 1:
                break
        time.sleep(0.05)

    scheduler.stop()
    # One worker is still rendering (blocked); shutdown is therefore not clean.
    assert scheduler.alive_worker_count() == 1
    assert scheduler.last_shutdown_clean() is False

    scheduler.start()
    # start() must restore the missing slot rather than refusing because a stale
    # thread object remained in _threads.
    assert scheduler.alive_worker_count() == 2

    derivative_id = None
    with _connect(isolated_metadata_db) as conn:
        derivative_id = int(
            conn.execute("SELECT id FROM asset_derivatives WHERE asset_id = ?", (asset_id,)).fetchone()[0]
        )
    blocked.set()

    for _ in range(100):
        with _connect(isolated_metadata_db) as conn:
            if (
                conn.execute(
                    "SELECT count(*) FROM derivative_jobs WHERE derivative_id = ? AND state = 'done'",
                    (derivative_id,),
                ).fetchone()[0]
                >= 1
            ):
                break
        time.sleep(0.05)

    with _connect(isolated_metadata_db) as conn:
        job_count = conn.execute(
            "SELECT count(*) FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,)
        ).fetchone()[0]
        status = conn.execute("SELECT status FROM asset_derivatives WHERE id = ?", (derivative_id,)).fetchone()[0]
    assert job_count == 1  # No duplicate job created by the restart.
    assert status == "ready"
    scheduler.stop()


def test_stop_records_clean_shutdown_when_workers_finish(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """An idle scheduler stop completes cleanly within the bounded timeout."""
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_RECONCILE_ENABLED", False)
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_SHUTDOWN_TIMEOUT_SECONDS", 5)
    scheduler = DerivativeScheduler(worker_count=2)
    scheduler.start()
    assert scheduler.alive_worker_count() == 2
    scheduler.stop()
    assert scheduler.alive_worker_count() == 0
    assert scheduler.last_shutdown_clean() is True


def test_start_prunes_stale_dead_threads_before_restoring_slots(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """A stale dead thread object in _threads must not block restart or restore."""
    monkeypatch.setattr(scheduler_module, "DERIVATIVE_RECONCILE_ENABLED", False)
    scheduler = DerivativeScheduler(worker_count=2)

    class _DeadThread(threading.Thread):
        def is_alive(self):  # type: ignore[override]
            return False

        def start(self):  # noqa: D401
            return None

        def join(self, timeout=None):  # noqa: D401, ANN001
            return None

    with scheduler._lifecycle_lock:
        scheduler._threads = [_DeadThread(name="derivative-worker-1")]
    scheduler.start()
    assert scheduler.alive_worker_count() == 2
    scheduler.stop()
