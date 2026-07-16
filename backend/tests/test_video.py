"""Video indexing, streaming, poster generation, and stats coverage.

Purpose:
Cover video catalog indexing, byte-range streaming, poster generation, and
library stats.

Guarantees:
Video assets stream with correct range semantics, reject non-video files, and
contribute stable metadata/stats.

Run when:
Changing video routes, poster generation, media classification, or video stats.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from backend.errors import APIError
from backend.metadata_store import (
    get_library_for_path,
    get_library_stats,
    index_directory_tree,
    index_file,
    register_library,
)
from backend.metadata_store._schema import CATALOG_SCHEMA_VERSION

_FFMPEG = shutil.which("ffmpeg")


def _create_test_video(path: Path) -> None:
    """Create a short valid MP4 without relying on checked-in binary fixtures."""
    subprocess.run(
        [
            _FFMPEG,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x24:d=2",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )


def _catalog_video(path: Path) -> None:
    if get_library_for_path(path) is None:
        register_library(path.parent)
    stat = path.stat()
    assert index_file(path, path.name, path.parent, "video", stat.st_mtime, stat.st_size, None, None, "video/mp4")


@pytest.fixture
def video_file(isolated_gallery_root: Path) -> Path:
    if not _FFMPEG:
        pytest.skip("ffmpeg not found")
    path = isolated_gallery_root / "sample.mp4"
    _create_test_video(path)
    return path


@pytest.fixture
def simple_video_file(isolated_gallery_root: Path) -> Path:
    path = isolated_gallery_root / "sample.mp4"
    path.write_bytes(b"0123456789abcdefghijklmnopqrstuvwxyz")
    _catalog_video(path)
    return path


def test_video_indexing_and_library_stats(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
    video_file: Path,
):
    image = isolated_gallery_root / "image.png"
    image.write_bytes(b"indexed by extension")
    library_id = int(register_library(isolated_gallery_root)["id"])

    assert index_directory_tree(isolated_gallery_root, include_metadata=False) == 3

    with sqlite3.connect(isolated_metadata_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assets WHERE path = ?", (str(video_file.resolve()),)).fetchone()
        assert row is not None
        assert row["type"] == "video"
        assert row["mime_type"] == "video/mp4"
        assert row["duration_ms"] == pytest.approx(2000, abs=100)
        assert row["codec"] == "mpeg4"
        assert (row["width"], row["height"]) == (32, 24)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == CATALOG_SCHEMA_VERSION

    stats = get_library_stats(library_id)
    assert stats["photos"] == 1
    assert stats["videos"] == 1
    assert stats["total_assets"] == 2


def test_video_full_response(isolated_app, simple_video_file: Path):
    response = isolated_app.get("/api/video", params={"path": str(simple_video_file)})

    assert response.status_code == 200
    assert response.content == simple_video_file.read_bytes()
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert int(response.headers["content-length"]) == simple_video_file.stat().st_size


def test_video_byte_range(isolated_app, simple_video_file: Path):
    response = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={"Range": "bytes=4-15"},
    )

    assert response.status_code == 206
    assert response.content == simple_video_file.read_bytes()[4:16]
    assert response.headers["content-range"] == f"bytes 4-15/{simple_video_file.stat().st_size}"
    assert response.headers["content-length"] == "12"


def test_video_suffix_range(isolated_app, simple_video_file: Path):
    response = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={"Range": "bytes=-6"},
    )

    assert response.status_code == 206
    assert response.content == simple_video_file.read_bytes()[-6:]
    assert response.headers["content-range"] == f"bytes 30-35/{simple_video_file.stat().st_size}"
    assert response.headers["content-length"] == "6"


@pytest.mark.parametrize(
    "range_header", ["bytes=36-", "bytes=10-2", "bytes=-0", "bytes=-", "bytes=1-2,4-5", "items=1-2"]
)
def test_video_unsatisfiable_ranges(isolated_app, simple_video_file: Path, range_header: str):
    size = simple_video_file.stat().st_size
    response = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={"Range": range_header},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"


def test_video_rejects_non_video_file(isolated_app, isolated_gallery_root: Path):
    text_file = isolated_gallery_root / "notes.txt"
    text_file.write_text("not a video")

    response = isolated_app.get("/api/video", params={"path": str(text_file)})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "not_found"


def test_video_poster_generation(
    isolated_app,
    isolated_thumbnail_cache: Path,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
):
    import backend.video as video_module

    poster_dir = isolated_thumbnail_cache / "video_posters"
    monkeypatch.setattr(video_module, "POSTER_CACHE_DIR", poster_dir)
    original_run_in_threadpool = video_module.run_in_threadpool
    offloaded: list[str] = []

    async def tracked_run_in_threadpool(func, *args):
        offloaded.append(func.__name__)
        return await original_run_in_threadpool(func, *args)

    monkeypatch.setattr(video_module, "run_in_threadpool", tracked_run_in_threadpool)
    _catalog_video(video_file)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content.startswith(b"RIFF")
    assert len(list(poster_dir.glob("*.webp"))) == 1
    assert offloaded == ["_validate_video", "_get_or_generate_poster", "stat"]

    cached = isolated_app.get(
        "/api/video/poster",
        params={"path": str(video_file)},
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert cached.status_code == 304


def test_video_poster_reports_missing_ffmpeg(
    isolated_app,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
):
    monkeypatch.setenv("PATH", "")
    _catalog_video(video_file)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "video_tool_unavailable"


# ---------------------------------------------------------------------------
# _validate_video coverage: file not found (404) and not a video (400)
# ---------------------------------------------------------------------------


def test_validate_video_file_not_found():
    import backend.video as video_module

    with pytest.raises(APIError) as exc:
        video_module._validate_video("/nonexistent/video.mp4")
    assert exc.value.status_code == 404


def test_validate_video_not_a_video_file(isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.video as video_module

    text_file = isolated_gallery_root / "notes.txt"
    text_file.write_text("not a video")
    monkeypatch.setattr("backend.video.require_media_path_allowed", lambda p, k: Path(str(text_file)))
    with pytest.raises(APIError) as exc:
        video_module._validate_video(str(text_file))
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------
# iter_file_range: empty chunk break (line 76) — simulated via tiny file
# ---------------------------------------------------------------------------


def test_iter_file_range_empty_chunk_break(tmp_path: Path):
    import backend.video as video_module

    path = tmp_path / "small.txt"
    path.write_bytes(b"hello")
    chunks = list(video_module.iter_file_range(path, 0, 3, chunk_size=5))
    assert chunks == [b"hell"]


# ---------------------------------------------------------------------------
# _release_poster_serving: remaining > 0 (line 100)
# ---------------------------------------------------------------------------


def test_release_poster_serving_with_remaining():
    import backend.video as video_module

    video_module._acquire_poster_serving("/test/path")
    video_module._acquire_poster_serving("/test/path")
    video_module._release_poster_serving("/test/path")
    import threading
    with video_module._POSTER_STATE_LOCK:
        assert video_module._POSTER_SERVING_COUNTS.get("/test/path") == 1
    video_module._release_poster_serving("/test/path")


# ---------------------------------------------------------------------------
# _PosterServingLease: double release no-ops (line 115)
# ---------------------------------------------------------------------------


def test_poster_serving_lease_double_release():
    import backend.video as video_module
    from pathlib import Path

    lease = video_module._PosterServingLease(Path("/tmp/test.webp"))
    lease.release()
    lease.release()


# ---------------------------------------------------------------------------
# Poster quota eviction: protected path skipped (lines 151-152)
# ---------------------------------------------------------------------------


def test_poster_quota_eviction_skips_protected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.video as video_module

    cache_dir = tmp_path / "posters"
    cache_dir.mkdir()
    monkeypatch.setattr(video_module, "POSTER_CACHE_DIR", cache_dir)

    for i in range(3):
        p = cache_dir / f"poster_{i}.webp"
        p.write_bytes(b"\x00" * 100)
    monkeypatch.setattr(video_module, "VIDEO_POSTER_QUOTA_BYTES", 50)
    monkeypatch.setattr(video_module, "_POSTER_GENERATING_PATHS", set())
    monkeypatch.setattr(video_module, "_POSTER_SERVED_PATHS", {str(cache_dir / "poster_0.webp")})

    result = video_module._enforce_poster_quota()
    assert result is False


# ---------------------------------------------------------------------------
# 304 for if-none-match with no range (line 173)
# ---------------------------------------------------------------------------


def test_video_304_if_none_match(isolated_app, simple_video_file: Path):
    resp1 = isolated_app.get("/api/video", params={"path": str(simple_video_file)})
    etag = resp1.headers.get("etag")
    assert etag is not None

    resp2 = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={"If-None-Match": etag},
    )
    assert resp2.status_code == 304


# ---------------------------------------------------------------------------
# if-range header validation (lines 181-188)
# ---------------------------------------------------------------------------


def test_video_if_range_matching_etag(isolated_app, simple_video_file: Path):
    resp1 = isolated_app.get("/api/video", params={"path": str(simple_video_file)})
    etag = resp1.headers.get("etag")

    resp2 = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={
            "Range": "bytes=0-5",
            "If-Range": etag,
        },
    )
    assert resp2.status_code == 206


def test_video_if_range_matching_date(isolated_app, simple_video_file: Path):
    import email.utils
    from datetime import datetime, timezone

    resp1 = isolated_app.get("/api/video", params={"path": str(simple_video_file)})
    last_modified = resp1.headers.get("last-modified")
    dt = datetime.fromtimestamp(0, tz=timezone.utc)
    past_date = email.utils.formatdate(dt.timestamp(), usegmt=True)

    resp2 = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={
            "Range": "bytes=0-5",
            "If-Range": past_date,
        },
    )
    assert resp2.status_code == 200


def test_video_if_range_invalid_date_falls_back(isolated_app, simple_video_file: Path):
    resp2 = isolated_app.get(
        "/api/video",
        params={"path": str(simple_video_file)},
        headers={
            "Range": "bytes=0-5",
            "If-Range": "not-a-valid-date-string",
        },
    )
    assert resp2.status_code == 200


# ---------------------------------------------------------------------------
# ffmpeg poster generation failure (line 280)
# ---------------------------------------------------------------------------


def test_video_poster_ffmpeg_failure(
    isolated_app,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
):
    import backend.video as video_module
    import subprocess

    real_run = subprocess.run

    def failing_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", failing_run)
    _catalog_video(video_file)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "video_poster_failed"


def test_video_poster_os_error(
    isolated_app,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
):
    import backend.video as video_module
    import subprocess

    def failing_run(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(subprocess, "run", failing_run)
    _catalog_video(video_file)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Poster quota enforcement failure (lines 307-314)
# ---------------------------------------------------------------------------


def test_video_poster_quota_exceeded(
    isolated_app,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
    isolated_thumbnail_cache: Path,
):
    import backend.video as video_module

    poster_dir = isolated_thumbnail_cache / "video_posters"
    monkeypatch.setattr(video_module, "POSTER_CACHE_DIR", poster_dir)
    monkeypatch.setattr(video_module, "VIDEO_POSTER_QUOTA_BYTES", 1)
    _catalog_video(video_file)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 507


# ---------------------------------------------------------------------------
# RuntimeError when serving lease is not acquired (line 325)
# ---------------------------------------------------------------------------


def test_video_poster_missing_lease(
    isolated_app,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
    isolated_thumbnail_cache: Path,
):
    import backend.video as video_module

    poster_dir = isolated_thumbnail_cache / "video_posters"
    monkeypatch.setattr(video_module, "POSTER_CACHE_DIR", poster_dir)

    def failing_get(*args, **kwargs):
        return "/tmp/nonexistent.webp"

    monkeypatch.setattr(video_module, "_get_or_generate_poster", failing_get)
    _catalog_video(video_file)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 500
