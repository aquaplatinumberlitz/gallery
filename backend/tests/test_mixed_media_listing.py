"""Mixed-media browse and search response compatibility coverage."""

from pathlib import Path

from backend.metadata_store import get_asset_folder_listing, index_file, register_library, search_index
from tests.conftest import create_test_png


def test_asset_listing_keeps_images_and_adds_videos_and_media(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    register_library(isolated_gallery_root)
    image = isolated_gallery_root / "photo.png"
    video = isolated_gallery_root / "clip.mp4"
    create_test_png(image)
    video.write_bytes(b"video")

    image_stat = image.stat()
    video_stat = video.stat()
    assert index_file(image, image.name, image.parent, "image", image_stat.st_mtime, image_stat.st_size, 32, 32)
    assert index_file(
        video,
        video.name,
        video.parent,
        "video",
        video_stat.st_mtime,
        video_stat.st_size,
        1920,
        1080,
        "video/mp4",
        65_000,
        "h264",
    )

    listing = get_asset_folder_listing(isolated_gallery_root)
    assert listing is not None
    assert [node.name for node in listing["images"]] == ["photo.png"]
    assert [node.name for node in listing["videos"]] == ["clip.mp4"]
    assert [node.name for node in listing["media"]] == ["clip.mp4", "photo.png"]
    assert listing["videos"][0].duration_ms == 65_000
    assert listing["videos"][0].mime_type == "video/mp4"
    assert listing["total_images"] == 1
    assert listing["total_videos"] == 1
    assert listing["total_assets"] == 2


def test_filename_search_returns_separate_video_results(
    isolated_metadata_db: Path,
    isolated_gallery_root: Path,
):
    register_library(isolated_gallery_root)
    video = isolated_gallery_root / "holiday-clip.mp4"
    video.write_bytes(b"video")
    stat = video.stat()
    assert index_file(video, video.name, video.parent, "video", stat.st_mtime, stat.st_size, None, None)

    result = search_index("holiday", "current", isolated_gallery_root)
    assert result["photos"] == []
    assert [item["name"] for item in result["videos"]] == ["holiday-clip.mp4"]
    assert result["videos"][0]["type"] == "video"
