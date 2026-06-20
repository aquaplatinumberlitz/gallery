"""Best-effort in-process Server-Sent Events for library job progress."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request

_subscribers: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Queue[dict[str, Any]]]] = {}
_subscriber_lock = threading.Lock()
_next_subscriber_id = 0

# Seconds to wait for an event before yielding a keep-alive comment frame.
# Exposed as a module constant so tests can shorten it without patching
# asyncio.wait_for globally.
KEEPALIVE_TIMEOUT_SECONDS: float = 15.0


def event_payload(event_type: str, job: dict[str, Any]) -> dict[str, Any]:
    """Build the stable V1 SSE payload from a serialized job."""
    return {
        "type": event_type,
        "job_id": job["id"],
        "library_id": job["library_id"],
        "state": job["state"],
        "progress_current": job["progress_current"],
        "progress_total": job["progress_total"],
        "message": job["message"],
        "error": job["error"],
        "updated_at": job["updated_at"],
    }


def format_sse(payload: dict[str, Any]) -> str:
    """Serialize one event as a standard SSE frame."""
    event_id = payload.get("job_id") or payload["updated_at"]
    data = json.dumps(payload, separators=(",", ":"))
    return f"event: {payload['type']}\nid: {event_id}\ndata: {data}\n\n"


def publish(payload: dict[str, Any]) -> None:
    """Publish an event to current subscribers without blocking job threads."""
    with _subscriber_lock:
        subscribers = list(_subscribers.values())

    def enqueue(queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(payload)

    for loop, queue in subscribers:
        if not loop.is_closed():
            loop.call_soon_threadsafe(enqueue, queue)


async def event_stream(request: Request) -> AsyncIterator[str]:
    """Yield event frames and periodic comments until the client disconnects."""
    global _next_subscriber_id
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
    loop = asyncio.get_running_loop()
    with _subscriber_lock:
        _next_subscriber_id += 1
        subscriber_id = _next_subscriber_id
        _subscribers[subscriber_id] = (loop, queue)
    try:
        while not await request.is_disconnected():
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_TIMEOUT_SECONDS)
                yield format_sse(payload)
            except TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        with _subscriber_lock:
            _subscribers.pop(subscriber_id, None)
