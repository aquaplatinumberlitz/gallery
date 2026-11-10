"""Image pipeline plan B1 follow-up: background sibling batches yield to interactive work.

Purpose:
Pin the fix for the reviewer's album-harness regression. A worker that claims a background (priority 2-3)
job also claims its queued sibling variants and renders them as a cascade; with all workers inside such
batches, a priority 0-1 request waited tens of seconds even though the claim query orders by priority.

Guarantees:
Between variants of a batch led by a background job the worker checks (one plain read) for runnable priority
0-1 work. When there is some, it stops after the variant it is rendering, hands the unrendered sibling claims
back to `queued` in one fenced writer op that clears the claim token and lease and does not consume an attempt,
and returns so the next claim is the interactive job. The same happens when a request raises the priority of a
variant that the batch has claimed but not rendered. A released claim can never be completed by the preempted
worker (the token is gone), an interactive job waits about one variant's render time even when every worker
starts inside a background batch, and an interactive leader or a batch nobody is waiting for runs to the end.

Run when:
Changing `_run_batch`, `_batch_should_yield`, `_release_claims`, sibling claiming, or worker headroom for
interactive derivative jobs.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import backend.derivative_scheduler.lifecycle as scheduler_lifecycle_module
import backend.thumbnails as thumbnails
from backend.derivative_scheduler import DerivativeScheduler
from backend.metadata_store import index_file
from backend.metadata_store._db import open_connection
from tests.conftest import create_test_png
from tests.worker_contention_support import seed_library

BIG_QUOTA = 1024 * 1024 * 1024
VARIANTS = {
    "thumb_128": ("thumbnail", 128, 78),
    "thumb_256": ("thumbnail", 256, 78),
    "thumb_512": ("thumbnail", 512, 78),
    "preview_1440": ("preview", 1440, 86),
}


@pytest.fixture
def albums(isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_thumbnail_cache: Path, monkeypatch):
    """Six indexed 1200x800 PNGs: ``(db_path, [asset_id], scheduler)``."""
    import backend.visual_fingerprints as visual_fingerprints

    monkeypatch.setattr(visual_fingerprints, "notify_derivative_ready", lambda _asset_id: None)
    root = isolated_gallery_root / "preempt"
    root.mkdir(parents=True, exist_ok=True)
    seed_library(root)
    scheduler = DerivativeScheduler(worker_count=1, quota_bytes=BIG_QUOTA)
    ids: list[int] = []
    for index in range(6):
        image = root / f"photo_{index}.png"
        create_test_png(image, size=(1200, 800))
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 1200, 800)
        asset_id = scheduler.find_asset_id(image)
        assert asset_id is not None
        ids.append(asset_id)
    return isolated_metadata_db, ids, scheduler


def _queue_background(scheduler: DerivativeScheduler, asset_id: int) -> None:
    summary = scheduler.reconcile_desired_derivatives(asset_ids=[asset_id], reason="phase_1")
    assert summary.created_jobs == 4


def _request(scheduler: DerivativeScheduler, asset_id: int, variant: str = "thumb_512") -> int:
    kind, edge, quality = VARIANTS[variant]
    return scheduler.schedule_derivative(asset_id, kind, variant, 0, max_long_edge=edge, quality=quality, format="webp")


def _rows(db_path: Path, asset_id: int | None = None) -> dict[str, dict[str, Any]]:
    with open_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT d.asset_id, d.variant, d.status, d.attempts AS derivative_attempts, j.id AS job_id,
                   j.state AS job_state, j.attempts AS job_attempts, j.priority AS priority,
                   j.claim_token AS claim_token, j.lease_expires_at AS lease_expires_at, j.claimed_by AS claimed_by
            FROM asset_derivatives d JOIN derivative_jobs j ON j.derivative_id = d.id
            WHERE (? IS NULL OR d.asset_id = ?)
            """,
            (asset_id, asset_id),
        ).fetchall()
    return {(f"{row['asset_id']}:{row['variant']}" if asset_id is None else row["variant"]): dict(row) for row in rows}


def _during_first_encode(monkeypatch: pytest.MonkeyPatch, action) -> list[str]:  # noqa: ANN001
    """Run ``action`` once, while the first variant of a batch is being encoded (a request arriving mid-batch)."""
    encoded: list[str] = []
    real_encode = thumbnails._encode_image
    fired = threading.Event()

    def encode(img, normalized_format, quality):  # noqa: ANN001
        encoded.append(f"{quality}")
        if not fired.is_set():
            fired.set()
            action()
        return real_encode(img, normalized_format, quality)

    monkeypatch.setattr(thumbnails, "_encode_image", encode)
    return encoded


def test_a_background_batch_stops_after_the_current_variant_when_interactive_work_appears(
    albums, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, ids, scheduler = albums
    batch_asset, requested_asset = ids[0], ids[1]
    _queue_background(scheduler, batch_asset)
    _queue_background(scheduler, requested_asset)
    before = _rows(db_path, batch_asset)
    encoded = _during_first_encode(monkeypatch, lambda: _request(scheduler, requested_asset))

    job = scheduler._claim_job("worker-1")
    assert job is not None and job["asset_id"] == batch_asset
    scheduler._run_job(job)

    rows = _rows(db_path, batch_asset)
    done = [name for name, row in rows.items() if row["job_state"] == "done"]
    queued = [name for name, row in rows.items() if row["job_state"] == "queued"]
    assert len(encoded) == 1, "the batch must stop after the variant it was rendering"
    assert len(done) == 1 and len(queued) == 3, rows
    for name in queued:
        row = rows[name]
        assert row["status"] == "queued"
        assert row["job_attempts"] == before[name]["job_attempts"], "a release must not consume an attempt"
        assert row["derivative_attempts"] == before[name]["derivative_attempts"]
        assert row["claim_token"] is None and row["lease_expires_at"] is None and row["claimed_by"] is None

    follow_up = scheduler._claim_job("worker-1")
    assert follow_up is not None
    assert (follow_up["asset_id"], follow_up["variant"]) == (requested_asset, "thumb_512"), (
        "the next claim must be the interactive job"
    )


def test_a_released_sibling_claim_cannot_be_completed_by_the_preempted_worker(
    albums, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, ids, scheduler = albums
    batch_asset, requested_asset = ids[0], ids[1]
    _queue_background(scheduler, batch_asset)
    _queue_background(scheduler, requested_asset)
    siblings: list[Any] = []
    real_claim_siblings = scheduler._claim_siblings

    def recording(job):  # noqa: ANN001
        claimed = real_claim_siblings(job)
        siblings.extend(claimed)
        return claimed

    monkeypatch.setattr(scheduler, "_claim_siblings", recording)
    _during_first_encode(monkeypatch, lambda: _request(scheduler, requested_asset))
    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)
    assert len(siblings) == 3

    stale = siblings[0]
    assert scheduler._complete_claim(stale, "/nowhere.webp", 1) is False
    row = _rows(db_path, batch_asset)[stale["variant"]]
    assert (row["job_state"], row["status"]) == ("queued", "queued"), "the stale worker must write nothing"

    scheduler._claim_job("worker-2")  # the interactive job
    reclaimed = scheduler._claim_job("worker-2")  # then one of the released siblings, under a fresh token
    assert reclaimed is not None and reclaimed["claim_token"] not in {s["claim_token"] for s in siblings}
    assert scheduler._complete_claim(stale, "/nowhere.webp", 1) is False
    still_running = _rows(db_path, batch_asset)[reclaimed["variant"]]
    assert still_running["job_state"] == "running", "the new owner's claim is untouched by the old token"


def test_a_request_for_a_variant_a_batch_already_claimed_preempts_the_batch(
    albums, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, ids, scheduler = albums
    asset_id = ids[0]
    _queue_background(scheduler, asset_id)
    # thumb_256 and preview_1440 are claimed (running) by the batch but not rendered yet when the request comes
    _during_first_encode(monkeypatch, lambda: _request(scheduler, asset_id, "preview_1440"))

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    rows = _rows(db_path, asset_id)
    assert sum(row["job_state"] == "done" for row in rows.values()) == 1
    assert rows["preview_1440"]["job_state"] == "queued" and rows["preview_1440"]["priority"] == 0
    next_job = scheduler._claim_job("worker-1")
    assert next_job is not None and next_job["variant"] == "preview_1440", "the requested variant is rendered next"


def test_a_batch_nobody_is_waiting_for_runs_to_the_end(albums) -> None:
    db_path, ids, scheduler = albums
    _queue_background(scheduler, ids[0])

    job = scheduler._claim_job("worker-1")
    assert job is not None
    scheduler._run_job(job)

    assert {row["job_state"] for row in _rows(db_path, ids[0]).values()} == {"done"}


def test_an_interactive_leader_is_never_preempted_by_other_interactive_work(albums) -> None:
    db_path, ids, scheduler = albums
    _queue_background(scheduler, ids[0])
    _request(scheduler, ids[0], "thumb_512")
    _request(scheduler, ids[0], "thumb_256")
    _request(scheduler, ids[1], "thumb_512")

    job = scheduler._claim_job("worker-1")
    assert job is not None and job["asset_id"] == ids[0] and job["variant"] == "thumb_512"
    scheduler._run_job(job)

    rows = _rows(db_path, ids[0])
    assert (rows["thumb_512"]["job_state"], rows["thumb_256"]["job_state"]) == ("done", "done")


def test_an_interactive_job_waits_about_one_variant_when_every_worker_is_inside_a_background_batch(
    albums, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deterministic fake render time: 0.5 s per variant, three workers, each busy with a four-variant batch."""
    db_path, ids, _scheduler = albums
    monkeypatch.setattr(scheduler_lifecycle_module, "DERIVATIVE_RECONCILE_ENABLED", False)
    scheduler = DerivativeScheduler(worker_count=3, quota_bytes=BIG_QUOTA)
    variant_seconds = 0.5
    real_encode = thumbnails._encode_image

    def slow_encode(img, normalized_format, quality):  # noqa: ANN001
        time.sleep(variant_seconds)
        return real_encode(img, normalized_format, quality)

    monkeypatch.setattr(thumbnails, "_encode_image", slow_encode)
    for asset_id in ids[:5]:
        _queue_background(scheduler, asset_id)
    # Start the workers 0.15 s apart so each takes a whole asset (workers that wake at the same instant can split
    # one asset's variants between them, which hides the starvation this test is about).
    real_claim = scheduler._claim_job
    started: set[str] = set()

    def staggered_claim(worker_id=None, **kwargs):  # noqa: ANN001, ANN003
        name = threading.current_thread().name
        if name not in started:
            started.add(name)
            time.sleep(0.15 * (int(name.rsplit("-", 1)[-1]) - 1))
        return real_claim(worker_id, **kwargs)

    monkeypatch.setattr(scheduler, "_claim_job", staggered_claim)
    scheduler.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with open_connection(db_path) as conn:
                running_assets = conn.execute(
                    "SELECT count(DISTINCT d.asset_id) FROM derivative_jobs j JOIN asset_derivatives d "
                    "ON d.id = j.derivative_id WHERE j.state = 'running'"
                ).fetchone()[0]
            if running_assets >= 3:
                break
            time.sleep(0.02)
        assert running_assets >= 3, "every worker must be inside a background batch before the request arrives"

        asked = time.monotonic()
        derivative_id = _request(scheduler, ids[5])
        ready_at = None
        while time.monotonic() - asked < 10:
            outcome = scheduler.get_derivative_outcome(derivative_id)
            if outcome and outcome["derivative_state"] == "ready":
                ready_at = time.monotonic() - asked
                break
            time.sleep(0.01)
    finally:
        scheduler.stop()

    assert ready_at is not None, "the interactive derivative was never produced"
    # one variant still being rendered when the request arrives + its own render + scheduling slack;
    # without preemption it waits for a whole batch (4 variants = 2 s) before its own render.
    assert ready_at < 2 * variant_seconds + 0.4, f"interactive job took {ready_at:.2f}s"


def test_a_request_waiting_for_its_derivative_backs_off_its_catalog_polling(
    isolated_app, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dozens of waiting requests polling every 50 ms starved the render workers of the GIL.

    The wait is now signal-driven (``derivative_scheduler/waiters.py``) with a slow fallback poll; the deadline
    and constants are shortened here instead of faking the clock, because the wait runs on the event loop.
    """
    from backend.derivative_scheduler import scheduler as shared_scheduler

    polls: list[float] = []

    def outcome(_derivative_id):  # noqa: ANN001
        polls.append(time.monotonic())
        return {"derivative_state": "queued", "cache_path": None, "result_code": None}

    monkeypatch.setattr(shared_scheduler, "get_derivative_outcome", outcome)
    monkeypatch.setattr(shared_scheduler, "is_running", lambda: True)
    monkeypatch.setattr(shared_scheduler, "schedule_derivative", lambda *args, **kwargs: 1)
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 2.0)
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_FALLBACK_SECONDS", 0.5)

    response = isolated_app.get("/api/thumbnail", params={"path": str(temp_gallery / "album_a" / "001.png")})

    assert response.status_code == 503, "the wait still gives up after its deadline"
    assert 2 <= len(polls) <= 8, f"{len(polls)} reads in a 2 s wait (a fixed 50 ms interval is 40)"
    gaps = [later - earlier for earlier, later in zip(polls, polls[1:], strict=False)]
    assert min(gaps[:-1] or gaps) >= 0.4, "reads are spaced by the fallback interval, not hot-polled"
