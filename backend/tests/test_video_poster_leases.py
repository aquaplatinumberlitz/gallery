"""Video poster serving-lease concurrency regressions.

Purpose:
Exercise atomic poster serving protection and duplicate generation locking.

Guarantees:
Posters cannot be evicted during handoff/streaming, duplicate requests consume
one ffmpeg slot, and 304/send-failure/error/normal paths release every lease.

Run when:
Changing video poster generation, quota eviction, concurrency, or responses.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import video
from backend.metadata_store import index_file, register_library


@pytest.fixture(autouse=True)
def _reset_poster_state() -> None:
    with video._POSTER_STATE_LOCK:
        video._POSTER_GENERATING_PATHS.clear()
        video._POSTER_SERVED_PATHS.clear()
        video._POSTER_SERVING_COUNTS.clear()


def _cached_poster(source: Path, cache_dir: Path) -> Path:
    source.write_bytes(b"video")
    stat = source.stat()
    key = f"{source}_{stat.st_mtime_ns}_{stat.st_size}"
    import hashlib

    path = cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.webp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFFposter")
    return path


def _catalog_video(path: Path) -> None:
    register_library(path.parent)
    stat = path.stat()
    assert index_file(path, path.name, path.parent, "video", stat.st_mtime, stat.st_size, None, None, "video/mp4")


def test_serving_lease_prevents_eviction_during_response_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    cache_dir = tmp_path / "posters"
    poster = _cached_poster(source, cache_dir)
    monkeypatch.setattr(video, "POSTER_CACHE_DIR", cache_dir)
    monkeypatch.setattr(video, "VIDEO_POSTER_QUOTA_BYTES", 1024)

    lease = video._get_or_generate_poster(source, True)
    assert isinstance(lease, video._PosterServingLease)
    monkeypatch.setattr(video, "VIDEO_POSTER_QUOTA_BYTES", 0)
    assert video._enforce_poster_quota() is False
    assert poster.exists()

    lease.release()
    assert video._enforce_poster_quota()
    assert not poster.exists()


def test_duplicate_generation_waits_for_key_lock_before_ffmpeg_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    cache_dir = tmp_path / "posters"
    monkeypatch.setattr(video, "POSTER_CACHE_DIR", cache_dir)
    monkeypatch.setattr(video.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video, "VIDEO_POSTER_QUOTA_BYTES", 1024)

    class CountingSemaphore:
        def __init__(self) -> None:
            self.acquire_calls = 0

        def acquire(self, timeout: float) -> bool:
            self.acquire_calls += 1
            return True

        def release(self) -> None:
            return None

    slots = CountingSemaphore()
    monkeypatch.setattr(video, "_POSTER_SLOTS", slots)
    first_entered = threading.Event()
    allow_finish = threading.Event()
    run_calls = 0

    class Result:
        returncode = 0

    def fake_run(args, **_kwargs):
        nonlocal run_calls
        run_calls += 1
        first_entered.set()
        assert allow_finish.wait(2)
        Path(args[-1]).write_bytes(b"RIFFposter")
        return Result()

    monkeypatch.setattr(video.subprocess, "run", fake_run)
    results: list[Path | video._PosterServingLease] = []

    first = threading.Thread(target=lambda: results.append(video._get_or_generate_poster(source)))
    second = threading.Thread(target=lambda: results.append(video._get_or_generate_poster(source)))
    first.start()
    assert first_entered.wait(1)
    second.start()
    allow_finish.set()
    first.join(2)
    second.join(2)

    assert run_calls == 1
    assert slots.acquire_calls == 1
    assert len(results) == 2
    assert results[0] == results[1]


def test_304_and_normal_response_release_serving_leases(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = isolated_gallery_root / "source.mp4"
    source.write_bytes(b"video")
    _catalog_video(source)
    poster = tmp_path / "poster.webp"
    poster.write_bytes(b"RIFFposter")

    def leased(_source: Path, acquire_serving: bool = False):
        assert acquire_serving
        video._acquire_poster_serving(str(poster))
        return video._PosterServingLease(poster)

    monkeypatch.setattr(video, "_get_or_generate_poster", leased)
    stat = poster.stat()
    etag = f'"{stat.st_mtime_ns}-{stat.st_size}"'
    not_modified = isolated_app.get(
        "/api/video/poster",
        params={"path": str(source)},
        headers={"If-None-Match": etag},
    )
    assert not_modified.status_code == 304
    assert video._POSTER_SERVING_COUNTS == {}

    normal = isolated_app.get("/api/video/poster", params={"path": str(source)})
    assert normal.status_code == 200
    assert normal.content == poster.read_bytes()
    assert video._POSTER_SERVING_COUNTS == {}


def test_poster_stat_error_releases_lease(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = isolated_gallery_root / "source.mp4"
    source.write_bytes(b"video")
    _catalog_video(source)
    missing = tmp_path / "missing.webp"

    def leased(_source: Path, acquire_serving: bool = False):
        assert acquire_serving
        video._acquire_poster_serving(str(missing))
        return video._PosterServingLease(missing)

    monkeypatch.setattr(video, "_get_or_generate_poster", leased)
    response = isolated_app.get("/api/video/poster", params={"path": str(source)})
    assert response.status_code == 500
    assert video._POSTER_SERVING_COUNTS == {}


def test_response_send_failure_releases_serving_lease(tmp_path: Path) -> None:
    poster = tmp_path / "poster.webp"
    poster.write_bytes(b"RIFFposter")
    video._acquire_poster_serving(str(poster))
    lease = video._PosterServingLease(poster)
    response = video._LeasedPosterResponse(
        lease,
        media_type="image/webp",
        stat_result=poster.stat(),
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/poster",
        "raw_path": b"/poster",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 80),
        "extensions": {},
    }

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            raise RuntimeError("client disconnected")

    with pytest.raises(RuntimeError, match="client disconnected"):
        asyncio.run(response(scope, receive, send))
    assert video._POSTER_SERVING_COUNTS == {}
