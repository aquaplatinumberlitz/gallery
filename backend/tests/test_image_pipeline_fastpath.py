"""Image pipeline plan B4: warm thumbnail serving fast path and coalesced access touches.

Purpose:
Pin the serving fast path of `docs/archived/IMAGE_PIPELINE_PLAN.md` (B4). A warm `/api/thumbnail` request used to
spend most of its time on catalog reads (authorization, asset id, ready derivative; each a new SQLite connection)
and queued one `last_accessed_at` writer op per file. A bounded in-process LRU now remembers the resolution, is
validated by the source `stat()` on every hit, and the access touches are written as one coalesced writer op.

Guarantees:
A repeated request is answered without the catalog lookups and with identical bytes, headers and 304s; an entry
never serves a derivative of a superseded or rewritten source, a deleted cache file, or an asset the catalog has
deactivated once its time-to-live passed; the LRU is bounded and disableable; `last_accessed_at` touches inside a
window cost one writer op, the pending ones are flushed by the next window, by `flush_touches`, by `stop()` and
by an eviction pass (which therefore never evicts a file that was just served), and a touch the writer dropped
(maintenance) is retried.

Run when:
Changing `derivative_fastpath.py`, the fast path in `thumbnails._serve_derivative`, `try_acquire_serving`, or the
touch coalescing in `derivative_scheduler/lookup.py`.
"""

from __future__ import annotations

import os
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import backend.thumbnails as thumbnails
from backend.catalog_maintenance_gate import maintenance_gate
from backend.derivative_fastpath import DerivativeFastPath, fast_path_key
from backend.derivative_scheduler import DerivativeScheduler, scheduler
from backend.metadata_store import index_file
from backend.metadata_store._db import open_connection
from backend.metadata_store.db_writer import run_write
from tests.conftest import create_test_png
from tests.worker_contention_support import install_submit_spy, seed_library

BIG_QUOTA = 1024 * 1024 * 1024


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fast_path(monkeypatch: pytest.MonkeyPatch) -> DerivativeFastPath:
    """A fresh fast path with a controllable clock, installed where the handler looks it up."""
    clock = FakeClock()
    instance = DerivativeFastPath(64, 5.0, clock=clock)
    instance.clock = clock  # type: ignore[attr-defined]
    monkeypatch.setattr(thumbnails, "derivative_fast_path", instance, raising=False)
    return instance


@pytest.fixture
def lookups(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count the catalog lookups a request performs."""
    counts = {"authorize": 0, "find_asset_id": 0, "acquire_ready": 0}
    real_authorize = thumbnails.require_media_path_allowed
    real_find = scheduler.find_asset_id
    real_acquire = scheduler.acquire_ready_derivative

    def authorize(*args, **kwargs):  # noqa: ANN002, ANN003
        counts["authorize"] += 1
        return real_authorize(*args, **kwargs)

    def find(*args, **kwargs):  # noqa: ANN002, ANN003
        counts["find_asset_id"] += 1
        return real_find(*args, **kwargs)

    def acquire(*args, **kwargs):  # noqa: ANN002, ANN003
        counts["acquire_ready"] += 1
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(thumbnails, "require_media_path_allowed", authorize)
    monkeypatch.setattr(scheduler, "find_asset_id", find)
    monkeypatch.setattr(scheduler, "acquire_ready_derivative", acquire)
    return counts


def _thumb(client: TestClient, path: Path, **extra: Any):
    return client.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 256, **extra})


def test_a_repeated_request_skips_the_catalog_lookups_and_answers_identically(
    isolated_app: TestClient, temp_gallery: Path, fast_path: DerivativeFastPath, lookups: dict[str, int]
) -> None:
    path = temp_gallery / "album_a" / "001.png"

    first = _thumb(isolated_app, path)
    cold = dict(lookups)
    second = _thumb(isolated_app, path)
    third = _thumb(isolated_app, path, v=f"{path.stat().st_mtime_ns}-{path.stat().st_size}")

    assert first.status_code == second.status_code == third.status_code == 200
    assert cold["authorize"] >= 1 and cold["find_asset_id"] >= 1 and cold["acquire_ready"] >= 1
    assert lookups == cold, "a warm request must not touch the catalog"
    assert second.content == first.content
    assert second.headers["etag"] == first.headers["etag"]
    assert second.headers["content-type"] == "image/webp"
    assert second.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert third.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_conditional_requests_are_answered_from_the_fast_path(
    isolated_app: TestClient, temp_gallery: Path, fast_path: DerivativeFastPath, lookups: dict[str, int]
) -> None:
    path = temp_gallery / "album_a" / "001.png"
    etag = _thumb(isolated_app, path).headers["etag"]
    cold = dict(lookups)

    revalidated = isolated_app.get(
        "/api/thumbnail",
        params={"path": str(path), "max_long_edge": 256},
        headers={"If-None-Match": etag},
    )

    assert revalidated.status_code == 304
    assert revalidated.headers["etag"] == etag
    assert lookups == cold


def test_asset_id_requests_use_the_fast_path_too(
    isolated_app: TestClient,
    temp_gallery: Path,
    isolated_metadata_db: Path,
    fast_path: DerivativeFastPath,
    lookups: dict[str, int],
) -> None:
    path = temp_gallery / "album_a" / "001.png"
    with open_connection(isolated_metadata_db) as conn:
        asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (str(path),)).fetchone()[0]
    first = isolated_app.get("/api/thumbnail", params={"asset_id": asset_id, "max_long_edge": 128})
    cold = dict(lookups)

    second = isolated_app.get("/api/thumbnail", params={"asset_id": asset_id, "max_long_edge": 128})

    assert first.status_code == second.status_code == 200 and second.content == first.content
    assert lookups == cold


def test_an_entry_never_serves_a_derivative_of_a_rewritten_source(
    isolated_app: TestClient, temp_gallery: Path, fast_path: DerivativeFastPath
) -> None:
    path = temp_gallery / "album_a" / "001.png"
    old = _thumb(isolated_app, path)
    with Image.open(BytesIO(old.content)) as img:
        assert img.size[0] > img.size[1], "landscape source"
    assert len(fast_path) == 1

    create_test_png(path, size=(300, 900), color=(200, 30, 30))  # portrait, same path, well inside the TTL
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 7_000_000_000))
    stat = path.stat()
    assert index_file(path, path.name, path.parent, "image", stat.st_mtime, stat.st_size, 300, 900)

    new = _thumb(isolated_app, path)

    assert new.status_code == 200
    assert new.headers["etag"] != old.headers["etag"]
    with Image.open(BytesIO(new.content)) as img:
        assert img.size[1] > img.size[0], "the rewritten (portrait) source must be served, not the cached landscape"


def test_a_rewritten_source_the_catalog_has_not_indexed_yet_is_never_answered_with_the_old_bytes(
    isolated_app: TestClient, temp_gallery: Path, fast_path: DerivativeFastPath
) -> None:
    path = temp_gallery / "album_a" / "001.png"
    old = _thumb(isolated_app, path)
    create_test_png(path, size=(300, 900))
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 7_000_000_000))

    new = _thumb(isolated_app, path)

    assert not (new.status_code == 200 and new.content == old.content)


def test_a_deleted_cache_file_falls_back_to_regeneration(
    isolated_app: TestClient, temp_gallery: Path, fast_path: DerivativeFastPath
) -> None:
    path = temp_gallery / "album_a" / "001.png"
    first = _thumb(isolated_app, path)
    (entry,) = fast_path._entries.values()
    Path(entry.cache_path).unlink()

    second = _thumb(isolated_app, path)

    assert second.status_code == 200
    assert second.content and second.headers["etag"] == first.headers["etag"]
    assert Path(entry.cache_path).is_file(), "the derivative must have been regenerated"


def test_entries_expire_and_a_deactivated_asset_is_not_served_after_the_ttl(
    isolated_app: TestClient,
    temp_gallery: Path,
    isolated_metadata_db: Path,
    fast_path: DerivativeFastPath,
    lookups: dict[str, int],
) -> None:
    path = temp_gallery / "album_a" / "001.png"
    assert _thumb(isolated_app, path).status_code == 200
    cold = dict(lookups)

    fast_path.clock.now += 4.0  # type: ignore[attr-defined]
    assert _thumb(isolated_app, path).status_code == 200
    assert lookups == cold, "still inside the time-to-live"

    fast_path.clock.now += 2.0  # type: ignore[attr-defined]
    assert _thumb(isolated_app, path).status_code == 200
    assert lookups["authorize"] > cold["authorize"], "an expired entry is re-authorized through the catalog"

    with open_connection(isolated_metadata_db) as conn:
        conn.execute("UPDATE assets SET offline = 1 WHERE path = ?", (str(path),))
    fast_path.clock.now += 6.0  # type: ignore[attr-defined]
    assert _thumb(isolated_app, path).status_code == 404, "catalog deactivation is honoured once the entry expired"


def test_the_lru_is_bounded_and_evicts_the_least_recently_used_entry() -> None:
    clock = FakeClock()
    lru = DerivativeFastPath(3, 60.0, clock=clock)

    def put(name: str) -> tuple[str, str, str, str, str]:
        key = fast_path_key("db", name, None, "thumbnail", "thumb_256")
        assert key is not None
        lru.put(
            key,
            source_path=name,
            mtime_ns=1,
            size=1,
            asset_id=1,
            derivative_id=1,
            cache_path=name,
            etag='"e"',
        )
        return key

    first, second, third = put("a"), put("b"), put("c")
    assert lru.get(first) is not None  # a is now most recently used
    fourth = put("d")

    assert len(lru) == 3
    assert lru.get(second) is None, "the least recently used entry goes first"
    assert all(lru.get(key) is not None for key in (first, third, fourth))


def test_entries_are_keyed_by_database_and_request_shape() -> None:
    by_path = fast_path_key("db1", "/x.png", None, "thumbnail", "thumb_256")
    by_asset = fast_path_key("db1", "/x.png", 7, "thumbnail", "thumb_256")
    other_db = fast_path_key("db2", "/x.png", None, "thumbnail", "thumb_256")
    other_variant = fast_path_key("db1", "/x.png", None, "thumbnail", "thumb_512")

    assert len({by_path, by_asset, other_db, other_variant}) == 4
    assert fast_path_key("db1", None, None, "thumbnail", "thumb_256") is None


@pytest.mark.parametrize(("entries", "ttl"), [(0, 5.0), (64, 0.0)])
def test_a_disabled_fast_path_never_remembers_anything(entries: int, ttl: float) -> None:
    lru = DerivativeFastPath(entries, ttl)
    key = fast_path_key("db", "/x.png", None, "thumbnail", "thumb_256")
    assert key is not None
    lru.put(key, source_path="/x", mtime_ns=1, size=1, asset_id=1, derivative_id=1, cache_path="/c", etag='"e"')

    assert not lru.enabled
    assert lru.get(key) is None and len(lru) == 0


# --- coalesced last_accessed_at touches ----------------------------------------------------------------


@pytest.fixture
def ready_derivatives(
    isolated_metadata_db: Path, isolated_gallery_root: Path, isolated_thumbnail_cache: Path, tmp_path: Path
):
    """A scheduler plus five 'ready' derivatives: ``(db_path, scheduler, [(derivative_id, cache_file)])``."""
    root = isolated_gallery_root / "touch"
    root.mkdir(parents=True, exist_ok=True)
    seed_library(root)
    local = DerivativeScheduler(worker_count=1, quota_bytes=BIG_QUOTA)
    ready: list[tuple[int, Path]] = []
    for index in range(5):
        image = root / f"img_{index}.png"
        create_test_png(image, size=(48, 32))
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 48, 32)
        asset_id = local.find_asset_id(image)
        derivative_id = local.schedule_derivative(asset_id, "thumbnail", "thumb_128", 3, max_long_edge=128, quality=78)
        cache_file = tmp_path / "touch_cache" / f"{index}.webp"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(b"x" * 100)
        with open_connection(isolated_metadata_db) as conn:
            conn.execute(
                "UPDATE asset_derivatives SET status = 'ready', cache_path = ?, byte_size = 100, "
                "last_accessed_at = NULL WHERE id = ?",
                (str(cache_file), derivative_id),
            )
            conn.execute("UPDATE derivative_jobs SET state = 'done' WHERE derivative_id = ?", (derivative_id,))
        ready.append((derivative_id, cache_file))
    return isolated_metadata_db, local, ready


def _accessed(db_path: Path) -> dict[int, float | None]:
    with open_connection(db_path) as conn:
        return {row[0]: row[1] for row in conn.execute("SELECT id, last_accessed_at FROM asset_derivatives")}


def test_touches_inside_a_window_are_one_writer_op(
    ready_derivatives, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, local, ready = ready_derivatives
    submits = install_submit_spy(monkeypatch)
    stamp = 2_460_000.5

    for offset, (derivative_id, cache_file) in enumerate(ready):
        local._touch_derivative(derivative_id, stamp + offset, str(cache_file))

    assert len(submits) == 1, "the first touch is written at once, the rest of the window is coalesced"
    assert len(local._touch_pending) == len(ready) - 1

    local.flush_touches(wait=True)

    assert len(submits) == 2, "the pending touches are one op, not one per file"
    accessed = _accessed(db_path)
    for offset, (derivative_id, _file) in enumerate(ready):
        assert accessed[derivative_id] == pytest.approx(stamp + offset), derivative_id
    assert local._touch_pending == {}


def test_a_touch_after_the_window_flushes_the_pending_ones(
    ready_derivatives, started_writer, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path, local, ready = ready_derivatives
    monkeypatch.setattr(local, "_TOUCH_COALESCE_SECONDS", 0.5)
    first, second = ready[0], ready[1]

    local._touch_derivative(first[0], 2_460_001.0, str(first[1]))
    local._touch_derivative(second[0], 2_460_002.0, str(second[1]))
    assert local._touch_pending == {second[0]: 2_460_002.0}
    time.sleep(0.6)
    local._touch_derivative(ready[2][0], 2_460_003.0, str(ready[2][1]))
    run_write(lambda conn: None)  # barrier: the normal lane is FIFO, so the touch ops above have committed

    accessed = _accessed(db_path)
    assert accessed[second[0]] == pytest.approx(2_460_002.0)
    assert accessed[ready[2][0]] == pytest.approx(2_460_003.0)


def test_stop_flushes_the_pending_touches(ready_derivatives, started_writer) -> None:
    db_path, local, ready = ready_derivatives
    local._touch_derivative(ready[0][0], 2_460_001.0, str(ready[0][1]))
    local._touch_derivative(ready[1][0], 2_460_002.0, str(ready[1][1]))
    assert local._touch_pending

    local.stop()

    assert local._touch_pending == {}
    assert _accessed(db_path)[ready[1][0]] == pytest.approx(2_460_002.0)


def test_a_touch_the_writer_dropped_is_retried(ready_derivatives, started_writer) -> None:
    db_path, local, ready = ready_derivatives
    stamp = 2_460_005.0

    with maintenance_gate():  # post_write drops best-effort ops (from other threads) while maintenance holds it
        request = threading.Thread(
            target=local._touch_derivative, args=(ready[0][0], stamp, str(ready[0][1])), daemon=True
        )
        request.start()
        request.join(10)
        assert local._touch_pending == {ready[0][0]: stamp}, "a dropped touch stays pending"
    assert _accessed(db_path)[ready[0][0]] is None

    local.flush_touches(wait=True)

    assert _accessed(db_path)[ready[0][0]] == pytest.approx(stamp)


def test_touches_apply_without_a_writer_too(ready_derivatives, no_active_writer) -> None:
    db_path, local, ready = ready_derivatives

    local._touch_derivative(ready[0][0], 2_460_001.0, str(ready[0][1]))
    local._touch_derivative(ready[1][0], 2_460_002.0, str(ready[1][1]))
    local.flush_touches()

    accessed = _accessed(db_path)
    assert accessed[ready[0][0]] == pytest.approx(2_460_001.0)
    assert accessed[ready[1][0]] == pytest.approx(2_460_002.0)


def test_eviction_honours_touches_that_were_not_flushed_yet(ready_derivatives, started_writer) -> None:
    """A just-served file whose touch is still pending must not be chosen as least recently used."""
    db_path, local, ready = ready_derivatives
    local.quota_bytes = 500
    with open_connection(db_path) as conn:
        for offset, (derivative_id, _file) in enumerate(ready):
            conn.execute(
                "UPDATE asset_derivatives SET last_accessed_at = ? WHERE id = ?",
                (2_460_000.0 + offset, derivative_id),
            )
    oldest = ready[0]
    local._touch_pending[oldest[0]] = 2_461_000.0  # served just now, not written yet

    assert local._reserve_capacity(100) is True

    statuses = {}
    with open_connection(db_path) as conn:
        for derivative_id, status in conn.execute("SELECT id, status FROM asset_derivatives"):
            statuses[derivative_id] = status
    assert statuses[oldest[0]] == "ready", "the file with a pending touch is the most recently used one"
    assert statuses[ready[1][0]] == "evicted", "the next oldest file is evicted instead"
    assert oldest[1].is_file() and not ready[1][1].is_file()
