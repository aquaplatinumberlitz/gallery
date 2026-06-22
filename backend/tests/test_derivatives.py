"""
Purpose:
Verifies derivative generation helpers, oriented dimensions, and API derivative edge cases.

Guarantees:
* thumbnail and preview sizing, aspect ratio, and no-upscale behavior remain stable
* EXIF-oriented dimensions flow through derivative, scan, metadata, and image endpoints

Run when:
* changing thumbnail generation, preview generation, EXIF handling, or dimension caching
* touching derivative failure handling or original image serving
"""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from backend import thumbnails
from backend.app import app
from backend.metadata_extract import get_oriented_dimensions
from backend.metadata_store import (
    get_cached_dimensions_for_files,
)

from .conftest import create_exif_rotated_jpeg

client = TestClient(app)


def _write_image(path, size: tuple[int, int], image_format: str = "PNG") -> None:
    image = Image.new("RGB", size, (40, 120, 200))
    image.save(path, format=image_format)


def _response_image_size(response) -> tuple[int, int]:
    with Image.open(BytesIO(response.content)) as image:
        return image.size


def test_thumbnail_default_max_long_edge_is_512(tmp_path):
    image_path = tmp_path / "wide.png"
    _write_image(image_path, (900, 600))

    response = client.get("/api/thumbnail", params={"path": str(image_path)})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert _response_image_size(response) == (512, 341)


def test_preview_default_max_long_edge_is_1440(tmp_path):
    image_path = tmp_path / "wide.png"
    _write_image(image_path, (1800, 1200))

    response = client.get("/api/preview", params={"path": str(image_path)})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert _response_image_size(response) == (1440, 960)


def test_thumbnail_and_preview_preserve_aspect_ratio_without_crop(tmp_path):
    portrait_path = tmp_path / "portrait.png"
    square_path = tmp_path / "square.png"
    _write_image(portrait_path, (1200, 1800))
    _write_image(square_path, (1800, 1800))

    portrait_response = client.get("/api/thumbnail", params={"path": str(portrait_path)})
    square_response = client.get("/api/preview", params={"path": str(square_path)})

    assert portrait_response.status_code == 200
    assert square_response.status_code == 200
    assert _response_image_size(portrait_response) == (341, 512)
    assert _response_image_size(square_response) == (1440, 1440)


def test_preview_does_not_upscale_small_images(tmp_path):
    image_path = tmp_path / "small.png"
    _write_image(image_path, (1000, 700))

    response = client.get("/api/preview", params={"path": str(image_path)})

    assert response.status_code == 200
    assert _response_image_size(response) == (1000, 700)


def test_derivative_cache_keys_are_separated_by_kind(tmp_path):
    image_path = tmp_path / "same-edge.png"
    _write_image(image_path, (900, 600))

    thumbnail_key = thumbnails._derivative_cache_key_str(
        image_path,
        kind="thumbnail",
        max_long_edge=512,
        quality=78,
        format="webp",
    )
    preview_key = thumbnails._derivative_cache_key_str(
        image_path,
        kind="preview",
        max_long_edge=512,
        quality=78,
        format="webp",
    )

    assert thumbnail_key != preview_key
    assert thumbnail_key.startswith("thumbnail:v2:")
    assert preview_key.startswith("preview:v2:")


def test_derivative_cache_version_is_v2():
    assert thumbnails.DERIVATIVE_CACHE_VERSION == "v2"


def test_oriented_dimensions_for_exif_rotated_jpeg(tmp_path):
    image_path = tmp_path / "iphone_photo.jpg"
    create_exif_rotated_jpeg(image_path, size=(1440, 1080), orientation=6)

    width, height = get_oriented_dimensions(image_path)

    assert width == 1080, f"expected oriented width=1080, got {width}"
    assert height == 1440, f"expected oriented height=1440, got {height}"


def test_oriented_dimensions_for_normal_image_is_unchanged(tmp_path):
    image_path = tmp_path / "normal.png"
    _write_image(image_path, (800, 600))

    width, height = get_oriented_dimensions(image_path)

    assert width == 800
    assert height == 600


def test_thumbnail_stores_oriented_dimensions_for_exif_jpeg(tmp_path, monkeypatch):
    import backend.metadata_store as ms

    monkeypatch.setattr(ms, "GALLERY_METADATA_DB", tmp_path / "test_thumb_dim.db")
    monkeypatch.setattr(ms, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms, "_DB_INITIALIZED_PATH", None)

    image_path = tmp_path / "iphone.jpg"
    create_exif_rotated_jpeg(image_path, size=(1440, 1080), orientation=6)

    response = client.get("/api/thumbnail", params={"path": str(image_path)})
    assert response.status_code == 200

    stat = image_path.stat()
    cached = get_cached_dimensions_for_files([(str(image_path.resolve()), stat.st_mtime, stat.st_size)])
    key = str(image_path.resolve())

    assert key in cached, f"no cached dimensions found for {key}"
    assert cached[key].width == 1080, f"expected width=1080, got {cached[key].width}"
    assert cached[key].height == 1440, f"expected height=1440, got {cached[key].height}"


def test_metadata_returns_oriented_dimensions_for_exif_jpeg(tmp_path, monkeypatch):
    import backend.metadata_store as ms

    monkeypatch.setattr(ms, "GALLERY_METADATA_DB", tmp_path / "test_meta_dim.db")
    monkeypatch.setattr(ms, "_DB_INITIALIZED", False)
    monkeypatch.setattr(ms, "_DB_INITIALIZED_PATH", None)

    image_path = tmp_path / "iphone_meta.jpg"
    create_exif_rotated_jpeg(image_path, size=(1440, 1080), orientation=6)

    response = client.get("/api/metadata", params={"path": str(image_path)})
    assert response.status_code == 200
    data = response.json()
    assert data["width"] == 1080, f"metadata width: expected 1080, got {data['width']}"
    assert data["height"] == 1440, f"metadata height: expected 1440, got {data['height']}"


def test_api_image_still_serves_original_file(tmp_path):
    image_path = tmp_path / "original.png"
    _write_image(image_path, (640, 480))
    original_bytes = image_path.read_bytes()

    response = client.get("/api/image", params={"path": str(image_path)})

    assert response.status_code == 200
    assert response.content == original_bytes


def test_preview_failure_returns_controlled_error(tmp_path, monkeypatch):
    error_client = TestClient(app, raise_server_exceptions=False)
    image_path = tmp_path / "broken-preview.png"
    _write_image(image_path, (900, 600))

    def fail_generate_derivative(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("preview renderer unavailable")

    monkeypatch.setattr(thumbnails, "generate_derivative", fail_generate_derivative)

    response = error_client.get("/api/preview", params={"path": str(image_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "error": "server_error",
        "message": "Unable to generate preview",
    }
