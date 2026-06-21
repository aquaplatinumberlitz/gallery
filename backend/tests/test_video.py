"""Video indexing, streaming, poster generation, and stats coverage."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from backend.metadata_store import get_library_stats, index_directory_tree, register_library

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


@pytest.fixture
def video_file(isolated_gallery_root: Path) -> Path:
    if not _FFMPEG:
        pytest.skip("ffmpeg not found")
    path = isolated_gallery_root / "sample.mp4"
    _create_test_video(path)
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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9

    stats = get_library_stats(library_id)
    assert stats["photos"] == 1
    assert stats["videos"] == 1
    assert stats["total_assets"] == 2


def test_video_full_response(isolated_app, video_file: Path):
    response = isolated_app.get("/api/video", params={"path": str(video_file)})

    assert response.status_code == 200
    assert response.content == video_file.read_bytes()
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert int(response.headers["content-length"]) == video_file.stat().st_size


def test_video_byte_range(isolated_app, video_file: Path):
    response = isolated_app.get(
        "/api/video",
        params={"path": str(video_file)},
        headers={"Range": "bytes=4-15"},
    )

    assert response.status_code == 206
    assert response.content == video_file.read_bytes()[4:16]
    assert response.headers["content-range"] == f"bytes 4-15/{video_file.stat().st_size}"
    assert response.headers["content-length"] == "12"


def test_video_unsatisfiable_range(isolated_app, video_file: Path):
    size = video_file.stat().st_size
    response = isolated_app.get(
        "/api/video",
        params={"path": str(video_file)},
        headers={"Range": f"bytes={size}-"},
    )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"


def test_video_rejects_non_video_file(isolated_app, isolated_gallery_root: Path):
    text_file = isolated_gallery_root / "notes.txt"
    text_file.write_text("not a video")

    response = isolated_app.get("/api/video", params={"path": str(text_file)})

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_file"


def test_video_poster_generation(
    isolated_app,
    isolated_thumbnail_cache: Path,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
):
    import backend.video as video_module

    poster_dir = isolated_thumbnail_cache / "video_posters"
    monkeypatch.setattr(video_module, "POSTER_CACHE_DIR", poster_dir)

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content.startswith(b"RIFF")
    assert len(list(poster_dir.glob("*.webp"))) == 1


def test_video_poster_reports_missing_ffmpeg(
    isolated_app,
    monkeypatch: pytest.MonkeyPatch,
    video_file: Path,
):
    monkeypatch.setenv("PATH", "")

    response = isolated_app.get("/api/video/poster", params={"path": str(video_file)})

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "video_tool_unavailable"
