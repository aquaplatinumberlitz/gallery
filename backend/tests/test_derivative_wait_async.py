"""
Purpose:
Verifies that a request waiting for its on-demand derivative waits on the event loop, not in a thread-pool thread
(PR-01 / BL-9), and that the wait keeps its error mapping, deadline and cleanup.

Guarantees:
* 50 waiting thumbnail requests leave a sync endpoint answering promptly (they hold no thread-pool thread)
* a worker's completion signal wakes the waiter at once; the slow fallback poll covers a missed signal
* the registry is empty after completion, timeout and client disconnect
* failed, deferred, skipped and invalid outcomes keep their HTTP status; ``source_changed`` reschedules once
* without scheduler workers the wait still advances the queue through ``run_once``

Run when:
* changing ``thumbnails._await_derivative`` / ``_serve_derivative`` or the derivative scheduler's terminal writes
* touching ``backend/derivative_scheduler/waiters.py``
"""

from __future__ import annotations

import asyncio
import itertools
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend import thumbnails
from backend.derivative_scheduler import scheduler as shared_scheduler
from backend.derivative_scheduler.waiters import DerivativeWaiters, derivative_waiters

PENDING = {"derivative_state": "queued", "cache_path": None, "result_code": None}


def _fake_scheduler(**overrides):
    """A scheduler stand-in with the four calls ``_await_derivative`` makes."""
    state = SimpleNamespace(outcomes=[], polls=[], scheduled=[], run_once_calls=0, running=True)

    def get_derivative_outcome(derivative_id):
        state.polls.append(derivative_id)
        current = state.outcomes[0] if len(state.outcomes) == 1 else state.outcomes.pop(0)
        return current(derivative_id) if callable(current) else current

    def schedule_derivative(*args, **kwargs):
        state.scheduled.append((args, kwargs))
        return 100 + len(state.scheduled)

    def run_once():
        state.run_once_calls += 1
        return False

    fake = SimpleNamespace(
        state=state,
        is_running=lambda: state.running,
        run_once=run_once,
        get_derivative_outcome=get_derivative_outcome,
        schedule_derivative=schedule_derivative,
        acquire_ready_derivative=lambda *a, **k: {"id": 1, "cache_path": "x"},
    )
    for name, value in overrides.items():
        setattr(fake, name, value)
    return fake


def _await(fake, derivative_id=1):
    return thumbnails._await_derivative(
        fake, derivative_id, 7, "thumbnail", "v", max_long_edge=512, quality=78, format="webp"
    )


# --------------------------------------------------------------------------------------------------------------
# The regression: waiting requests must not occupy the shared thread pool
# --------------------------------------------------------------------------------------------------------------


def test_fifty_waiting_derivative_requests_do_not_starve_a_sync_endpoint(
    isolated_app, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Derivatives never complete. Before the fix 50 waiters parked all 40 pool threads for the whole wait."""
    from backend.app import app

    ids = itertools.count(1)
    seen: set[int] = set()
    seen_lock = threading.Lock()

    def outcome(derivative_id):
        with seen_lock:
            seen.add(derivative_id)
        return dict(PENDING)

    monkeypatch.setattr(shared_scheduler, "is_running", lambda: True)
    monkeypatch.setattr(shared_scheduler, "run_once", lambda: False)
    monkeypatch.setattr(shared_scheduler, "schedule_derivative", lambda *a, **k: next(ids))
    monkeypatch.setattr(shared_scheduler, "get_derivative_outcome", outcome)
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 4.0, raising=False)
    path = str(temp_gallery / "album_a" / "001.png")

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
            waiters = [asyncio.create_task(client.get("/api/thumbnail", params={"path": path})) for _ in range(50)]
            deadline = time.monotonic() + 20
            while len(seen) < 50 and time.monotonic() < deadline:
                await asyncio.sleep(0.02)
            assert len(seen) == 50, "every request must reach its wait"
            latencies = []
            for _ in range(3):
                started = time.monotonic()
                probe = await client.get("/api/search", params={"q": "x", "scope": "all"})
                latencies.append(time.monotonic() - started)
                assert probe.status_code == 200
            assert not any(task.done() for task in waiters), "the probe must run while the requests still wait"
            responses = await asyncio.gather(*waiters)
        return latencies, responses

    latencies, responses = asyncio.run(scenario())

    # Parked threads made this wait for the whole 4-10 s deadline; an idle pool answers in milliseconds.
    assert max(latencies) < 2.0, f"sync endpoint took {latencies} while 50 derivative requests waited"
    assert {response.status_code for response in responses} == {503}
    assert derivative_waiters.waiting_count() == 0, "timed-out waiters must leave the registry"


def test_waiting_for_a_derivative_borrows_no_thread_pool_token(
    isolated_app, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Between catalog reads a waiter holds no token of the shared limiter (sampled while everyone waits)."""
    import anyio.to_thread

    from backend.app import app

    seen = threading.Event()
    monkeypatch.setattr(shared_scheduler, "is_running", lambda: True)
    monkeypatch.setattr(shared_scheduler, "schedule_derivative", lambda *a, **k: 1)

    def outcome(_derivative_id):
        seen.set()
        return dict(PENDING)

    monkeypatch.setattr(shared_scheduler, "get_derivative_outcome", outcome)
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 1.5, raising=False)
    path = str(temp_gallery / "album_a" / "001.png")

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
            task = asyncio.create_task(client.get("/api/thumbnail", params={"path": path}))
            while not seen.is_set():
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.3)
            borrowed = anyio.to_thread.current_default_thread_limiter().borrowed_tokens
            response = await task
        return borrowed, response

    borrowed, response = asyncio.run(scenario())
    assert borrowed == 0
    assert response.status_code == 503


# --------------------------------------------------------------------------------------------------------------
# Signal, fallback and cleanup
# --------------------------------------------------------------------------------------------------------------


def test_a_completion_signal_wakes_the_waiter_before_the_fallback_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_FALLBACK_SECONDS", 30.0)
    fake = _fake_scheduler()
    ready = {"derivative_state": "ready", "cache_path": __file__, "result_code": None}
    fake.state.outcomes = [lambda _id: ready if signalled.is_set() else dict(PENDING)]
    signalled = threading.Event()

    def complete_from_a_worker_thread():
        time.sleep(0.2)
        signalled.set()
        derivative_waiters.notify(1)

    async def scenario():
        threading.Thread(target=complete_from_a_worker_thread).start()
        started = time.monotonic()
        result = await _await(fake)
        return result, time.monotonic() - started

    result, elapsed = asyncio.run(scenario())
    assert result == {"id": 1, "cache_path": "x"}
    assert elapsed < 5, "the 30 s fallback poll must not be what woke the waiter"
    assert len(fake.state.polls) == 2, "one read before the wait and one after the signal"
    assert derivative_waiters.waiting_count() == 0


def test_the_fallback_poll_covers_a_missed_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_FALLBACK_SECONDS", 0.1)
    fake = _fake_scheduler()
    ready = {"derivative_state": "ready", "cache_path": __file__, "result_code": None}
    fake.state.outcomes = [dict(PENDING), dict(PENDING), ready]  # never notified

    assert asyncio.run(_await(fake)) == {"id": 1, "cache_path": "x"}
    assert len(fake.state.polls) == 3


def test_many_waiters_read_the_catalog_slowly_while_workers_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """No busy polling: with live workers a waiter reads once per fallback interval, not 20 times a second."""
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 1.0)
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_FALLBACK_SECONDS", 0.4)
    fake = _fake_scheduler()
    fake.state.outcomes = [dict(PENDING)]

    async def scenario():
        return await asyncio.gather(*[_await(fake, derivative_id=n) for n in range(1, 21)])

    assert asyncio.run(scenario()) == [None] * 20
    per_waiter = len(fake.state.polls) / 20
    assert per_waiter <= 4, f"{per_waiter} reads per waiter in 1 s (a 30 ms poll would be about 20)"


def test_registry_is_cleaned_after_completion_timeout_and_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_FALLBACK_SECONDS", 0.05)
    ready = {"derivative_state": "ready", "cache_path": __file__, "result_code": None}

    done = _fake_scheduler()
    done.state.outcomes = [ready]
    assert asyncio.run(_await(done)) is not None
    assert derivative_waiters.waiting_count() == 0

    timed_out = _fake_scheduler()
    timed_out.state.outcomes = [dict(PENDING)]
    assert asyncio.run(_await(timed_out)) is None
    assert derivative_waiters.waiting_count() == 0

    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 30.0)
    disconnected = _fake_scheduler()
    disconnected.state.outcomes = [dict(PENDING)]

    async def cancel_mid_wait():
        task = asyncio.create_task(_await(disconnected))
        while derivative_waiters.waiting_count() == 0 or not disconnected.state.polls:
            await asyncio.sleep(0.01)
        assert derivative_waiters.waiting_count() == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_mid_wait())
    assert derivative_waiters.waiting_count() == 0


def test_a_client_disconnect_removes_the_waiter(
    isolated_app, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.app import app

    monkeypatch.setattr(shared_scheduler, "is_running", lambda: True)
    monkeypatch.setattr(shared_scheduler, "schedule_derivative", lambda *a, **k: 5)
    monkeypatch.setattr(shared_scheduler, "get_derivative_outcome", lambda _id: dict(PENDING))
    path = str(temp_gallery / "album_a" / "001.png")

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
            task = asyncio.create_task(client.get("/api/thumbnail", params={"path": path}))
            deadline = time.monotonic() + 10
            while derivative_waiters.waiting_count() == 0 and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert derivative_waiters.waiting_count() == 1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert derivative_waiters.waiting_count() == 0


def test_registry_notify_is_thread_safe_and_tolerates_a_closed_loop() -> None:
    registry = DerivativeWaiters()

    async def register_only():
        return registry.register(9)

    loop = asyncio.new_event_loop()
    event = loop.run_until_complete(register_only())
    loop.close()
    registry.notify(9)  # a closed loop must not raise
    registry.notify(404)  # unknown id is a no-op
    registry.unregister(9, event)
    registry.unregister(9, event)  # idempotent
    assert registry.waiting_count() == 0


def test_the_scheduler_notifies_waiters_when_a_claim_reaches_a_terminal_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_complete_claim`` and ``_handle_failure`` are the worker-side producers of the wake-up signal."""
    from backend.derivative_scheduler import execution

    notified: list[int] = []
    monkeypatch.setattr(execution.derivative_waiters, "notify", notified.append)
    monkeypatch.setattr(execution, "run_write", lambda fn, **kwargs: True)
    job = {"id": 42, "job_id": 7, "claim_token": "t", "job_attempts": 1}

    scheduler = shared_scheduler
    assert scheduler._complete_claim(job, "/cache/x.webp", 10) is True
    scheduler._handle_failure(job, execution._DerivativeSkip("source_missing", "gone"))
    assert notified == [42, 42]

    monkeypatch.setattr(execution, "run_write", lambda fn, **kwargs: False)  # a stale claim wrote nothing
    assert scheduler._complete_claim(job, "/cache/x.webp", 10) is False
    scheduler._handle_failure(job, execution._DerivativeSkip("source_missing", "gone"))
    assert notified == [42, 42]


# --------------------------------------------------------------------------------------------------------------
# Preserved behaviour
# --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "result_code", "expected"),
    [
        ("failed", "invalid_source", (400, None)),
        ("failed", "attempts_exhausted", (500, "Generated image worker failed")),
        ("failed", "internal_error", (500, "Generated image worker failed")),
        ("failed", None, (500, "Generated image generation failed")),
        ("deferred_capacity", None, (507, None)),
        ("evicted", None, (507, None)),
        ("skipped", "source_missing", (404, None)),
        ("skipped", "asset_inactive", (404, None)),
        ("skipped", "other", (500, "Generated image request reached a terminal state")),
    ],
)
def test_terminal_outcomes_keep_their_http_status(
    isolated_app,
    temp_gallery: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    result_code: str | None,
    expected: tuple[int, str | None],
) -> None:
    monkeypatch.setattr(shared_scheduler, "is_running", lambda: True)
    monkeypatch.setattr(shared_scheduler, "schedule_derivative", lambda *a, **k: 1)
    monkeypatch.setattr(
        shared_scheduler,
        "get_derivative_outcome",
        lambda _id: {"derivative_state": state, "cache_path": None, "result_code": result_code},
    )
    response = isolated_app.get("/api/thumbnail", params={"path": str(temp_gallery / "album_a" / "001.png")})
    assert response.status_code == expected[0]
    if expected[1] is not None:
        assert expected[1] in response.text


def test_source_changed_reschedules_once_and_follows_the_new_derivative() -> None:
    fake = _fake_scheduler()
    changed = {"derivative_state": "skipped", "cache_path": None, "result_code": "source_changed"}
    ready = {"derivative_state": "ready", "cache_path": __file__, "result_code": None}
    fake.state.outcomes = [lambda derivative_id: changed if derivative_id == 1 else ready]

    result = asyncio.run(_await(fake))

    assert result == {"id": 1, "cache_path": "x"}
    assert len(fake.state.scheduled) == 1
    assert fake.state.scheduled[0][1] == {"max_long_edge": 512, "quality": 78, "format": "webp"}
    assert fake.state.polls == [1, 101]
    assert derivative_waiters.waiting_count() == 0


def test_source_changed_twice_is_a_terminal_skip_with_one_reschedule() -> None:
    fake = _fake_scheduler()
    fake.state.outcomes = [{"derivative_state": "skipped", "cache_path": None, "result_code": "source_changed"}]

    kind, outcome = asyncio.run(_await(fake))

    assert kind == "skipped"
    assert outcome["result_code"] == "source_changed"
    assert len(fake.state.scheduled) == 1
    assert derivative_waiters.waiting_count() == 0


def test_a_vanished_derivative_row_gives_up_without_waiting() -> None:
    fake = _fake_scheduler()
    fake.state.outcomes = [None]
    assert asyncio.run(_await(fake)) is None


def test_a_timeout_gives_503_after_the_deadline(
    isolated_app, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(thumbnails, "DERIVATIVE_WAIT_SECONDS", 0.5)
    monkeypatch.setattr(shared_scheduler, "is_running", lambda: True)
    monkeypatch.setattr(shared_scheduler, "schedule_derivative", lambda *a, **k: 1)
    monkeypatch.setattr(shared_scheduler, "get_derivative_outcome", lambda _id: dict(PENDING))
    started = time.monotonic()
    response = isolated_app.get("/api/thumbnail", params={"path": str(temp_gallery / "album_a" / "001.png")})
    assert response.status_code == 503
    assert 0.4 <= time.monotonic() - started < 5


def test_without_workers_the_wait_advances_the_queue_through_run_once() -> None:
    fake = _fake_scheduler()
    fake.state.running = False
    ready = {"derivative_state": "ready", "cache_path": __file__, "result_code": None}
    fake.state.outcomes = [dict(PENDING), ready]

    assert asyncio.run(_await(fake)) == {"id": 1, "cache_path": "x"}
    assert fake.state.run_once_calls == 2, "run_once is called before each catalog read, as one bounded pool call"
