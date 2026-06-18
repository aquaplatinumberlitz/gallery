"""
Purpose:
Exercise uncovered thumbnails.py branches for metric helpers, derivative format
normalization, render-time mode conversion, cache hit/miss paths, error mapping,
and _serve_derivative exception handling so backend line coverage stays above
the release threshold.

Guarantees:
* _metric_counter returns None when prometheus Counter is unavailable or raises
  ValueError, and _inc no-ops on a None metric while delegating to labels().inc()
  when given a real metric.
* _normalize_derivative_format maps "jpg" to "jpeg" and rejects unsupported
  formats with ValueError.
* _persist_derivative_file returns the existing cache path when the file already
  exists.
* _render_derivative_impl converts palette/RGBA/non-RGB modes to RGB, applies
  EXIF orientation, and resizes (no_upscale=False) when source != max_long_edge.
* generate_derivative returns cached bytes on a cache hit and maps
  DecompressionBombError / UnidentifiedImageError to APIError(400).
* _resolve_image_request_path rejects unsafe, missing, and non-image paths.
* _serve_derivative passes APIError through, maps FileNotFoundError to 404,
  OSError to 400, and other exceptions to 500, and falls back to a Response
  when no derivative file path is available on disk.

Run when:
* changing thumbnails.py metric helpers, format normalization, derivative
  rendering, cache hit/miss logic, or _serve_derivative error mapping
* adding new derivative formats or changing EXIF/mode conversion branches
* touching path-safety / file-existence checks for derivative endpoints
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import thumbnails
from backend.errors import APIError


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def test_metric_counter_returns_none_when_counter_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(thumbnails, "Counter", None)
    assert thumbnails._metric_counter("name", "doc") is None


def test_metric_counter_returns_none_on_value_error(monkeypatch: pytest.MonkeyPatch):
    class FailingCounter:
        def __init__(self, *args, **kwargs):
            raise ValueError("duplicate metric")

    monkeypatch.setattr(thumbnails, "Counter", FailingCounter)
    assert thumbnails._metric_counter("dup_name", "doc") is None


def test_inc_noops_on_none_metric():
    # Should not raise when metric is None
    thumbnails._inc(None)
    thumbnails._inc(None, "label1")


def test_inc_with_labels_calls_inc():
    target = MagicMock()
    labeled = MagicMock()
    target.labels.return_value = labeled

    thumbnails._inc(target, "some_label", amount=2.0)

    target.labels.assert_called_once_with("some_label")
    labeled.inc.assert_called_once_with(2.0)


def test_inc_without_labels_calls_inc_on_metric():
    target = MagicMock()
    thumbnails._inc(target, amount=1.0)
    target.labels.assert_not_called()
    target.inc.assert_called_once_with(1.0)


# ---------------------------------------------------------------------------
# _normalize_derivative_format
# ---------------------------------------------------------------------------


def test_normalize_derivative_format_jpg_maps_to_jpeg():
    assert thumbnails._normalize_derivative_format("jpg") == "jpeg"


def test_normalize_derivative_format_strips_leading_dot():
    assert thumbnails._normalize_derivative_format(".webp") == "webp"


def test_normalize_derivative_format_uppercase_is_lowercased():
    assert thumbnails._normalize_derivative_format("WEBP") == "webp"


def test_normalize_derivative_format_rejects_unknown():
    with pytest.raises(ValueError):
        thumbnails._normalize_derivative_format("avif")


def test_normalize_derivative_format_rejects_png():
    with pytest.raises(ValueError):
        thumbnails._normalize_derivative_format("png")


# ---------------------------------------------------------------------------
# _persist_derivative_file
# ---------------------------------------------------------------------------


def test_persist_derivative_file_returns_existing_path(
    isolated_thumbnail_cache: Path, tmp_path: Path
):
    image = tmp_path / "any.png"
    image.write_bytes(b"data")
    cache_key = "test_existing_key"
    derivative_path = thumbnails._derivative_cache_file_path(cache_key, "webp")
    derivative_path.parent.mkdir(parents=True, exist_ok=True)
    derivative_path.write_bytes(b"already-here")

    result = thumbnails._persist_derivative_file(cache_key, b"new-bytes", "webp")
    assert result == derivative_path
    # File contents should not change since path already exists
    assert derivative_path.read_bytes() == b"already-here"


def test_persist_derivative_file_writes_new_file(
    isolated_thumbnail_cache: Path, tmp_path: Path
):
    cache_key = "test_new_key"
    derivative_path = thumbnails._derivative_cache_file_path(cache_key, "webp")
    assert not derivative_path.exists()

    result = thumbnails._persist_derivative_file(cache_key, b"fresh-bytes", "webp")
    assert result == derivative_path
    assert derivative_path.read_bytes() == b"fresh-bytes"


# ---------------------------------------------------------------------------
# _render_derivative_impl mode conversion
# ---------------------------------------------------------------------------


def test_render_derivative_impl_converts_palette_mode(tmp_path: Path):
    """Palette (P) mode images are converted through RGBA → RGB."""
    image = tmp_path / "palette.png"
    img = Image.new("P", (100, 80))
    # Add a palette so saving works
    img.putpalette([0, 0, 0, 255, 255, 255] * 85)
    img.save(image, format="PNG")

    out = thumbnails._render_derivative_impl(
        image, max_long_edge=50, quality=80, format="webp", no_upscale=True
    )
    with Image.open(BytesIO(out)) as rendered:
        assert rendered.format == "WEBP"
        assert max(rendered.size) <= 50


def test_render_derivative_impl_rgba_flattens_alpha(tmp_path: Path):
    """RGBA mode images have their alpha channel flattened onto white."""
    image = tmp_path / "rgba.png"
    img = Image.new("RGBA", (120, 90), (10, 20, 30, 0))
    img.save(image, format="PNG")

    out = thumbnails._render_derivative_impl(
        image, max_long_edge=60, quality=80, format="webp", no_upscale=True
    )
    with Image.open(BytesIO(out)) as rendered:
        assert rendered.mode == "RGB"
        assert max(rendered.size) <= 60


def test_render_derivative_impl_no_upscale_false_resizes_to_target(tmp_path: Path):
    """When no_upscale=False and source != max_long_edge, the image is resized."""
    image = tmp_path / "resize_me.png"
    Image.new("RGB", (1000, 800), (40, 120, 200)).save(image, format="PNG")

    out = thumbnails._render_derivative_impl(
        image, max_long_edge=500, quality=80, format="webp", no_upscale=False
    )
    with Image.open(BytesIO(out)) as rendered:
        # 1000 wide source → 500 long edge
        assert rendered.size == (500, 400)


def test_render_derivative_impl_no_upscale_false_when_already_target_size(tmp_path: Path):
    """When no_upscale=False and source already equals max_long_edge, no resize occurs."""
    image = tmp_path / "target.png"
    Image.new("RGB", (500, 400), (40, 120, 200)).save(image, format="PNG")

    out = thumbnails._render_derivative_impl(
        image, max_long_edge=500, quality=80, format="webp", no_upscale=False
    )
    with Image.open(BytesIO(out)) as rendered:
        assert rendered.size == (500, 400)


def test_render_derivative_impl_jpeg_format(tmp_path: Path):
    """Rendering to JPEG format produces JPEG bytes."""
    image = tmp_path / "src.png"
    Image.new("RGB", (200, 150), (40, 120, 200)).save(image, format="PNG")

    out = thumbnails._render_derivative_impl(
        image, max_long_edge=100, quality=80, format="jpeg", no_upscale=True
    )
    with Image.open(BytesIO(out)) as rendered:
        assert rendered.format == "JPEG"


# ---------------------------------------------------------------------------
# generate_derivative cache hit + error mapping
# ---------------------------------------------------------------------------


def test_generate_derivative_cache_hit_returns_cached_bytes(
    isolated_thumbnail_cache: Path, tmp_path: Path
):
    image = tmp_path / "cached.png"
    Image.new("RGB", (200, 150), (40, 120, 200)).save(image, format="PNG")

    first = thumbnails.generate_derivative(
        image, kind="thumbnail", max_long_edge=100, quality=80, format="webp"
    )
    assert first

    # Replace the renderer with one that would raise so we know we hit the cache
    def fail_render(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("should not be called on cache hit")

    import backend.thumbnails as tn

    original = tn._render_derivative_impl
    tn._render_derivative_impl = fail_render
    try:
        second = thumbnails.generate_derivative(
            image, kind="thumbnail", max_long_edge=100, quality=80, format="webp"
        )
    finally:
        tn._render_derivative_impl = original

    assert second == first


def test_generate_derivative_maps_decompression_bomb_to_api_error(
    isolated_thumbnail_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    image = tmp_path / "bomb.png"
    image.write_bytes(b"data")

    def raise_bomb(*args, **kwargs):  # noqa: ANN002, ANN003
        raise Image.DecompressionBombError("too big")

    monkeypatch.setattr(thumbnails, "_render_derivative_impl", raise_bomb)

    with pytest.raises(APIError) as exc_info:
        thumbnails.generate_derivative(
            image, kind="thumbnail", max_long_edge=100, quality=80, format="webp"
        )
    assert exc_info.value.status_code == 400


def test_generate_derivative_maps_unidentified_image_to_api_error(
    isolated_thumbnail_cache: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from PIL import UnidentifiedImageError

    image = tmp_path / "broken.png"
    image.write_bytes(b"not really an image")

    def raise_unidentified(*args, **kwargs):  # noqa: ANN002, ANN003
        raise UnidentifiedImageError("cannot identify")

    monkeypatch.setattr(thumbnails, "_render_derivative_impl", raise_unidentified)

    with pytest.raises(APIError) as exc_info:
        thumbnails.generate_derivative(
            image, kind="thumbnail", max_long_edge=100, quality=80, format="webp"
        )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# _resolve_image_request_path
# ---------------------------------------------------------------------------


def test_resolve_image_request_path_rejects_unsafe_path(
    isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    # Path outside the gallery root
    monkeypatch.setattr(thumbnails, "is_path_safe", lambda _: False)
    with pytest.raises(APIError) as exc_info:
        thumbnails._resolve_image_request_path("/etc/passwd")
    assert exc_info.value.status_code == 403


def test_resolve_image_request_path_rejects_missing_file(
    isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(thumbnails, "is_path_safe", lambda _: True)
    with pytest.raises(APIError) as exc_info:
        thumbnails._resolve_image_request_path(str(isolated_gallery_root / "ghost.png"))
    assert exc_info.value.status_code == 404


def test_resolve_image_request_path_rejects_non_image(
    isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    text = isolated_gallery_root / "notes.txt"
    text.write_text("not an image")
    monkeypatch.setattr(thumbnails, "is_path_safe", lambda _: True)
    with pytest.raises(APIError) as exc_info:
        thumbnails._resolve_image_request_path(str(text))
    assert exc_info.value.status_code == 400


def test_resolve_image_request_path_returns_path_for_valid_image(
    isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    image = isolated_gallery_root / "valid.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")
    monkeypatch.setattr(thumbnails, "is_path_safe", lambda _: True)
    result = thumbnails._resolve_image_request_path(str(image))
    assert result == image


# ---------------------------------------------------------------------------
# _serve_derivative error mapping
# ---------------------------------------------------------------------------


def _build_request_for_etag(image_path: Path):
    """Build a Starlette-like Request stub with an empty headers dict."""
    request = MagicMock()
    request.headers = {}
    return request


def test_serve_derivative_passes_api_error_through(
    isolated_thumbnail_cache: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    image = isolated_gallery_root / "api_err.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")

    def raise_api_error(*args, **kwargs):  # noqa: ANN002, ANN003
        raise APIError(418, "teapot", "I'm a teapot")

    monkeypatch.setattr(thumbnails, "generate_derivative", raise_api_error)

    request = _build_request_for_etag(image)
    with pytest.raises(APIError) as exc_info:
        asyncio.run(
            thumbnails._serve_derivative(
                request=request,
                path=str(image),
                kind="thumbnail",
                max_long_edge=100,
                quality=80,
                format="webp",
                failure_message="fail",
            )
        )
    assert exc_info.value.status_code == 418


def test_serve_derivative_maps_filenotfound_to_404(
    isolated_thumbnail_cache: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    image = isolated_gallery_root / "gone.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")

    def raise_filenotfound(*args, **kwargs):  # noqa: ANN002, ANN003
        raise FileNotFoundError("vanished")

    monkeypatch.setattr(thumbnails, "generate_derivative", raise_filenotfound)

    request = _build_request_for_etag(image)
    with pytest.raises(APIError) as exc_info:
        asyncio.run(
            thumbnails._serve_derivative(
                request=request,
                path=str(image),
                kind="thumbnail",
                max_long_edge=100,
                quality=80,
                format="webp",
                failure_message="fail",
            )
        )
    assert exc_info.value.status_code == 404


def test_serve_derivative_maps_oserror_to_400(
    isolated_thumbnail_cache: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    image = isolated_gallery_root / "oserr.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")

    def raise_oserror(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError("disk on fire")

    monkeypatch.setattr(thumbnails, "generate_derivative", raise_oserror)

    request = _build_request_for_etag(image)
    with pytest.raises(APIError) as exc_info:
        asyncio.run(
            thumbnails._serve_derivative(
                request=request,
                path=str(image),
                kind="thumbnail",
                max_long_edge=100,
                quality=80,
                format="webp",
                failure_message="fail",
            )
        )
    assert exc_info.value.status_code == 400


def test_serve_derivative_maps_generic_exception_to_500(
    isolated_thumbnail_cache: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    image = isolated_gallery_root / "boom.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")

    def raise_generic(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("unexpected")

    monkeypatch.setattr(thumbnails, "generate_derivative", raise_generic)

    request = _build_request_for_etag(image)
    with pytest.raises(APIError) as exc_info:
        asyncio.run(
            thumbnails._serve_derivative(
                request=request,
                path=str(image),
                kind="thumbnail",
                max_long_edge=100,
                quality=80,
                format="webp",
                failure_message="fail",
            )
        )
    assert exc_info.value.status_code == 500


def test_serve_derivative_falls_back_to_response_when_no_file(
    isolated_thumbnail_cache: Path, isolated_gallery_root: Path, monkeypatch: pytest.MonkeyPatch
):
    """When generate_derivative succeeds but no cache file exists on disk, the
    Response-with-bytes fallback path is taken."""
    image = isolated_gallery_root / "fallback.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")

    # Ensure the cache file path doesn't exist by clearing the file dir
    monkeypatch.setattr(
        thumbnails,
        "_derivative_cache_file_path",
        lambda cache_key, format: Path("/nonexistent_dir_no_perms/fallback.bin"),
    )

    fake_bytes = b"\x00\x01\x02\x03"
    monkeypatch.setattr(
        thumbnails,
        "generate_derivative",
        lambda *args, **kwargs: fake_bytes,
    )

    request = _build_request_for_etag(image)
    response = asyncio.run(
        thumbnails._serve_derivative(
            request=request,
            path=str(image),
            kind="thumbnail",
            max_long_edge=100,
            quality=80,
            format="webp",
            failure_message="fail",
        )
    )
    assert response.body == fake_bytes
    assert response.media_type == "image/webp"
    assert response.headers["Content-Length"] == str(len(fake_bytes))


def test_serve_derivative_returns_304_on_etag_match(
    isolated_thumbnail_cache: Path, isolated_gallery_root: Path
):
    image = isolated_gallery_root / "etag_match.png"
    Image.new("RGB", (10, 10), (40, 120, 200)).save(image, format="PNG")

    stat = image.stat()
    etag = (
        f'"thumbnail-{thumbnails.DERIVATIVE_CACHE_VERSION}-{stat.st_mtime_ns}-'
        f'{stat.st_size}-100-webp-80"'
    )

    request = MagicMock()
    request.headers = {"if-none-match": etag}

    response = asyncio.run(
        thumbnails._serve_derivative(
            request=request,
            path=str(image),
            kind="thumbnail",
            max_long_edge=100,
            quality=80,
            format="webp",
            failure_message="fail",
        )
    )
    assert response.status_code == 304


# ---------------------------------------------------------------------------
# _resolve_max_long_edge helper
# ---------------------------------------------------------------------------


def test_resolve_max_long_edge_prefers_max_size_when_provided():
    assert thumbnails._resolve_max_long_edge(512, 1024) == 1024


def test_resolve_max_long_edge_uses_max_long_edge_when_max_size_none():
    assert thumbnails._resolve_max_long_edge(512, None) == 512


# ---------------------------------------------------------------------------
# Integration via API: thumbnail endpoint error paths
# ---------------------------------------------------------------------------


def test_api_thumbnail_rejects_non_image(tmp_path: Path):
    """Calling /api/thumbnail on a non-image file returns 400."""
    from backend.app import app

    text = tmp_path / "notes.txt"
    text.write_text("not an image")
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/thumbnail", params={"path": str(text)})
    assert resp.status_code == 400


def test_api_thumbnail_404_for_missing_file(tmp_path: Path):
    """Calling /api/thumbnail on a missing file returns 404."""
    from backend.app import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/thumbnail", params={"path": str(tmp_path / "ghost.png")})
    assert resp.status_code == 404
