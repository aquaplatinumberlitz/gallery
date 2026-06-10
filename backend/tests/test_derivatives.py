from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from backend.app import app
from backend import thumbnails


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
    assert thumbnail_key.startswith("thumbnail:v1:")
    assert preview_key.startswith("preview:v1:")


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
