"""
Purpose:
Protect derivative, poster, capacity, cache, and lease fixes from backend audit phase 4.

Guarantees:
* HTTP derivatives use durable scheduling and quota-zero requests return 507 without rendering
* diskcache stores path metadata and clears legacy byte values on the v3 cache bump
* heartbeat-renewed derivative claims are not reclaimed from stale snapshots
* unsupported legacy variants are terminalized and their files removed after commit
* poster saturation, quota protection, bounded subprocess output, and temp cleanup are enforced

Run when:
* changing derivative scheduling/quota/cache/leases, integrity repair, or video posters
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from backend import thumbnails, video
from backend.derivative_scheduler import DerivativeScheduler, scheduler
from backend.integrity_checker import integrity_checker
from backend.metadata_store import _DB_LOCK, _connect, create_library, index_file
from tests.conftest import create_test_png


def _catalog_image(root: Path) -> tuple[Path, int]:
    root.mkdir(parents=True, exist_ok=True)
    image = root / "image.png"
    create_test_png(image)
    library = create_library([root], name=root.name)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    with _DB_LOCK, _connect() as conn:
        asset_id = int(conn.execute("SELECT id FROM assets WHERE library_id = ?", (library["id"],)).fetchone()[0])
    return image, asset_id


def test_http_quota_zero_returns_507_without_rendering(
    isolated_app,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    image, _asset_id = _catalog_image(isolated_gallery_root / "quota-zero")
    monkeypatch.setattr(scheduler, "quota_bytes", 0)
    monkeypatch.setattr(
        thumbnails,
        "generate_derivative",
        lambda *_args, **_kwargs: pytest.fail("capacity refusal must happen before render"),
    )

    response = isolated_app.get("/api/thumbnail", params={"path": image, "max_long_edge": 128})

    assert response.status_code == 507
    with _DB_LOCK, _connect() as conn:
        assert conn.execute("SELECT count(*) FROM derivative_jobs").fetchone()[0] == 0
        assert conn.execute("SELECT status FROM asset_derivatives").fetchone()[0] == "deferred_capacity"


def test_cache_version_bump_clears_legacy_bytes(isolated_thumbnail_cache: Path):
    thumbnails._thumbnail_disk_cache.set("legacy", b"duplicate derivative bytes")
    thumbnails._thumbnail_disk_cache.set(thumbnails._CACHE_VERSION_KEY, "v2")

    thumbnails._initialize_path_metadata_cache()

    assert thumbnails._thumbnail_disk_cache.get("legacy") is None
    assert thumbnails._thumbnail_disk_cache.get(thumbnails._CACHE_VERSION_KEY) == "v3"


def test_renewed_claim_is_not_reclaimed_by_integrity_snapshot(isolated_gallery_root: Path):
    image, asset_id = _catalog_image(isolated_gallery_root / "lease")
    local = DerivativeScheduler(quota_bytes=1024 * 1024)
    derivative_id = local.schedule_derivative(asset_id, "thumbnail", "thumb_128", max_long_edge=128, quality=78)
    claimed = local._claim_job("lease-worker")
    assert claimed is not None
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "UPDATE derivative_jobs SET lease_expires_at = julianday('now', '-1 second') WHERE id = ?",
            (claimed["job_id"],),
        )
        rows = conn.execute(
            """
            SELECT j.id AS job_id, j.attempts, j.claim_token, d.id AS derivative_id,
                   d.source_mtime_ns, d.source_size, a.id AS asset_id, a.path,
                   a.type, a.deleted_at, a.offline, a.mtime_ns, a.size
            FROM derivative_jobs j JOIN asset_derivatives d ON d.id = j.derivative_id
            JOIN assets a ON a.id = d.asset_id WHERE j.id = ?
            """,
            (claimed["job_id"],),
        ).fetchall()
        conn.execute(
            "UPDATE derivative_jobs SET lease_expires_at = julianday('now', '+60 seconds') WHERE id = ?",
            (claimed["job_id"],),
        )
        result = integrity_checker._check_abandoned_derivative_jobs(
            conn,
            rows=rows,
            source_stats={str(image): image.stat()},
        )
        state = conn.execute("SELECT state FROM derivative_jobs WHERE derivative_id = ?", (derivative_id,)).fetchone()[
            0
        ]
    assert result == {"requeued": 0, "skipped": 0, "failed": 0}
    assert state == "running"


def test_integrity_removes_unsupported_variant_cache(isolated_gallery_root: Path, tmp_path: Path):
    image, asset_id = _catalog_image(isolated_gallery_root / "legacy")
    stat = image.stat()
    cache_path = tmp_path / "legacy.webp"
    cache_path.write_bytes(b"legacy")
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format,
              quality, max_long_edge, status, cache_path, byte_size
            ) VALUES (?, 'thumbnail', 'thumb_256_legacy', ?, ?, 'webp', 78, 256, 'ready', ?, 6)
            """,
            (asset_id, stat.st_mtime_ns, stat.st_size, str(cache_path)),
        )

    integrity_checker.run_all_checks()

    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT status, cache_path FROM asset_derivatives WHERE variant = 'thumb_256_legacy'"
        ).fetchone()
    assert row["status"] == "skipped"
    assert row["cache_path"] is None
    assert not cache_path.exists()


def test_poster_saturation_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")

    class Saturated:
        def acquire(self, timeout: float) -> bool:
            return False

        def release(self) -> None:
            pytest.fail("unacquired slot must not be released")

    monkeypatch.setattr(video, "_POSTER_SLOTS", Saturated())
    monkeypatch.setattr(video.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    with pytest.raises(Exception) as exc_info:
        video._get_or_generate_poster(source)
    assert getattr(exc_info.value, "status_code", None) == 503


def test_poster_quota_protects_served_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(video, "POSTER_CACHE_DIR", tmp_path)
    monkeypatch.setattr(video, "VIDEO_POSTER_QUOTA_BYTES", 4)
    protected = tmp_path / "protected.webp"
    evictable = tmp_path / "evictable.webp"
    protected.write_bytes(b"1234")
    evictable.write_bytes(b"5678")
    old = time.time_ns() - 2_000_000_000
    os.utime(protected, ns=(old, old))
    os.utime(evictable, ns=(old + 1, old + 1))
    video._POSTER_SERVED_PATHS.add(str(protected))
    try:
        assert video._enforce_poster_quota()
    finally:
        video._POSTER_SERVED_PATHS.clear()
    assert protected.exists()
    assert not evictable.exists()


def test_poster_subprocess_output_is_bounded_and_temp_is_cleaned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    poster_dir = tmp_path / "posters"
    observed: dict = {}

    def fake_run(args, **kwargs):
        observed.update(kwargs)
        Path(args[-1]).write_bytes(b"RIFFposter")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(video, "POSTER_CACHE_DIR", poster_dir)
    monkeypatch.setattr(video, "VIDEO_POSTER_QUOTA_BYTES", 1024)
    monkeypatch.setattr(video.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video.subprocess, "run", fake_run)
    monkeypatch.setattr(video, "_POSTER_SLOTS", threading.BoundedSemaphore(1))

    poster = video._get_or_generate_poster(source)

    assert poster.is_file()
    assert observed["stdout"] is subprocess.DEVNULL
    assert observed["stderr"] is subprocess.DEVNULL
    assert not list(poster_dir.glob("*.tmp.*"))
