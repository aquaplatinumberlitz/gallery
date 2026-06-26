"""
Purpose:
Exercise backend/library_events.py SSE subscriber lifecycle, event publishing, and
streaming branches for backend line coverage above the release threshold.

Guarantees:
* event_payload builds the expected V1 SSE payload dict from a serialized job.
* format_sse serialises a payload as a standard SSE frame with correct event/id/data.
* publish appends to subscriber queues, handles full queues by dropping oldest,
  and skips closed loops.
* event_stream yields keepalive frames on timeout and removes subscribers on disconnect.

Run when:
* changing library_events.py subscriber lifecycle, queue full/closed-loop branches,
  or the event_stream async generator.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from backend import library_events


def test_event_payload_builds_expected_dict():
    job = {
        "id": 42,
        "library_id": 1,
        "state": "running",
        "progress_current": 5,
        "progress_total": 10,
        "message": "Scanning…",
        "error": None,
        "updated_at": 1234567890,
    }
    payload = library_events.event_payload("job.progress", job)
    assert payload["type"] == "job.progress"
    assert payload["job_id"] == 42
    assert payload["library_id"] == 1
    assert payload["state"] == "running"
    assert payload["progress_current"] == 5
    assert payload["progress_total"] == 10
    assert payload["message"] == "Scanning…"
    assert payload["error"] is None


def test_format_sse_serialises_payload():
    payload = {
        "type": "job.progress",
        "job_id": 42,
        "library_id": 1,
        "state": "running",
        "progress_current": 5,
        "progress_total": 10,
        "message": "Scanning…",
        "error": None,
        "updated_at": 1234567890,
    }
    frame = library_events.format_sse(payload)
    assert frame.startswith("event: job.progress")
    assert "id: 42" in frame
    assert "data:" in frame


def test_format_sse_falls_back_to_updated_at_when_job_id_missing():
    payload = {
        "type": "keepalive",
        "job_id": None,
        "updated_at": 999,
        "library_id": 1,
        "state": "running",
        "progress_current": 0,
        "progress_total": 0,
        "message": "",
        "error": None,
    }
    frame = library_events.format_sse(payload)
    assert "id: 999" in frame


def test_publish_appends_to_subscriber_queue():
    async def _run():
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        loop = asyncio.get_running_loop()
        subscriber_id = 1
        library_events._subscribers[subscriber_id] = (loop, queue)
        try:
            library_events.publish({"type": "test", "job_id": 1})
            # call_soon_threadsafe schedules but needs a yield to execute
            await asyncio.sleep(0)
            assert not queue.empty()
            item = queue.get_nowait()
            assert item["type"] == "test"
        finally:
            library_events._subscribers.pop(subscriber_id, None)

    asyncio.run(_run())


def test_publish_handles_full_queue():
    async def _run():
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        loop = asyncio.get_running_loop()
        subscriber_id = 2
        library_events._subscribers[subscriber_id] = (loop, queue)
        try:
            queue.put_nowait({"type": "first"})
            library_events.publish({"type": "second"})
            await asyncio.sleep(0)
            assert queue.qsize() == 1
            item = queue.get_nowait()
            assert item["type"] == "second"
        finally:
            library_events._subscribers.pop(subscriber_id, None)

    asyncio.run(_run())


def test_publish_skips_closed_loop():
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.new_event_loop()
    loop.close()
    subscriber_id = 3
    library_events._subscribers[subscriber_id] = (loop, queue)
    try:
        library_events.publish({"type": "test", "job_id": 3})
        assert queue.empty()
    finally:
        library_events._subscribers.pop(subscriber_id, None)


def test_event_stream_yields_keepalive_on_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(library_events, "KEEPALIVE_TIMEOUT_SECONDS", 0.01)

    async def _run():
        async def is_connected():
            return False

        request = MagicMock()
        request.is_disconnected = is_connected

        frames = []
        async for frame in library_events.event_stream(request):
            frames.append(frame)
            if len(frames) >= 2:
                break
        assert any("keep-alive" in f for f in frames)

    asyncio.run(_run())


def test_event_stream_removes_subscriber_on_disconnect():
    async def _run():
        async def is_disconnected():
            return True

        request = MagicMock()
        request.is_disconnected = is_disconnected
        sid_before = len(library_events._subscribers)
        async for _ in library_events.event_stream(request):
            break
        assert len(library_events._subscribers) == sid_before

    asyncio.run(_run())
