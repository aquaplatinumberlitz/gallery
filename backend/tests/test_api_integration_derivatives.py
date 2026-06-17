"""
Purpose:
Verifies the /api/image, /api/thumbnail, and /api/preview derivative endpoints.

Guarantees:
* original, thumbnail, and preview responses keep cache, sizing, and safety contracts
* derivative cache keys remain separated by endpoint kind and size

Run when:
* changing image serving, thumbnail/preview generation, cache headers, or derivative cache keys
* touching image path validation or PIL derivative behavior
"""

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image as PILImage

from .conftest import create_test_png


class TestApiImage:
    def test_image_returns_original_bytes(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        original = path.read_bytes()

        resp = isolated_app.get("/api/image", params={"path": str(path)})
        assert resp.status_code == 200
        assert resp.content == original

    def test_image_has_cache_headers_and_etag(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/image", params={"path": str(path)})
        assert resp.status_code == 200
        assert "cache-control" in resp.headers
        assert "etag" in resp.headers
        assert "immutable" in resp.headers["cache-control"].lower()

    def test_image_rejects_invalid_file(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "note.txt"
        resp = isolated_app.get("/api/image", params={"path": str(path)})
        assert resp.status_code == 400

    def test_image_404_for_missing(self, isolated_app: TestClient, temp_gallery: Path):
        resp = isolated_app.get("/api/image", params={"path": str(temp_gallery / "none.png")})
        assert resp.status_code == 404


class TestThumbnail:
    def test_thumbnail_returns_webp(self, isolated_app: TestClient, isolated_thumbnail_cache: Path, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/thumbnail", params={"path": str(path)})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"

    def test_thumbnail_default_max_long_edge_is_512(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/thumbnail", params={"path": str(path)})
        assert resp.status_code == 200
        with PILImage.open(BytesIO(resp.content)) as img:
            assert max(img.size) <= 512

    def test_thumbnail_custom_max_long_edge(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 256})
        assert resp.status_code == 200
        with PILImage.open(BytesIO(resp.content)) as img:
            assert max(img.size) <= 256

    def test_thumbnail_no_upscale_small_images(self, isolated_app: TestClient, isolated_gallery_root: Path):
        path = isolated_gallery_root / "small.png"
        create_test_png(path, size=(200, 150))
        resp = isolated_app.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 512})
        assert resp.status_code == 200
        with PILImage.open(BytesIO(resp.content)) as img:
            assert img.size == (200, 150)

    def test_thumbnail_has_cache_headers(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/thumbnail", params={"path": str(path)})
        assert resp.status_code == 200
        assert "cache-control" in resp.headers
        assert "etag" in resp.headers

    def test_thumbnail_if_none_match_returns_304(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        # First request to get the ETag
        resp1 = isolated_app.get("/api/thumbnail", params={"path": str(path)})
        assert resp1.status_code == 200
        etag = resp1.headers["etag"]

        # Second request with If-None-Match
        resp2 = isolated_app.get(
            "/api/thumbnail",
            params={"path": str(path)},
            headers={"if-none-match": etag},
        )
        assert resp2.status_code == 304


class TestPreview:
    def test_preview_returns_webp(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "002.jpg"
        resp = isolated_app.get("/api/preview", params={"path": str(path)})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"

    def test_preview_default_max_long_edge_is_1440(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/preview", params={"path": str(path)})
        assert resp.status_code == 200
        with PILImage.open(BytesIO(resp.content)) as img:
            assert max(img.size) <= 1440

    def test_preview_no_upscale_small_images(self, isolated_app: TestClient, isolated_gallery_root: Path):
        path = isolated_gallery_root / "small.png"
        create_test_png(path, size=(400, 300))
        resp = isolated_app.get("/api/preview", params={"path": str(path)})
        assert resp.status_code == 200
        with PILImage.open(BytesIO(resp.content)) as img:
            assert img.size == (400, 300)

    def test_preview_has_cache_headers(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp = isolated_app.get("/api/preview", params={"path": str(path)})
        assert resp.status_code == 200
        assert "cache-control" in resp.headers
        assert "etag" in resp.headers

    def test_preview_if_none_match_returns_304(self, isolated_app: TestClient, temp_gallery: Path):
        path = temp_gallery / "album_a" / "001.png"
        resp1 = isolated_app.get("/api/preview", params={"path": str(path)})
        assert resp1.status_code == 200
        etag = resp1.headers["etag"]

        resp2 = isolated_app.get(
            "/api/preview",
            params={"path": str(path)},
            headers={"if-none-match": etag},
        )
        assert resp2.status_code == 304


class TestDerivativeCacheSeparation:
    def test_thumbnail_and_preview_cache_keys_are_separated(self, isolated_app: TestClient, temp_gallery: Path):
        """A 512px thumbnail must not be reused as a 1440px preview, and vice versa."""
        from backend import thumbnails

        path = temp_gallery / "album_a" / "001.png"

        thumbnail_key = thumbnails._derivative_cache_key_str(
            path,
            kind="thumbnail",
            max_long_edge=512,
            quality=78,
            format="webp",
        )
        preview_key = thumbnails._derivative_cache_key_str(
            path,
            kind="preview",
            max_long_edge=1440,
            quality=86,
            format="webp",
        )

        assert thumbnail_key != preview_key
        assert "thumbnail" in thumbnail_key
        assert "preview" in preview_key

    def test_same_edge_different_kind_produces_different_keys(self, isolated_app: TestClient, temp_gallery: Path):
        from backend import thumbnails

        path = temp_gallery / "album_a" / "001.png"

        thumbnail_key = thumbnails._derivative_cache_key_str(
            path,
            kind="thumbnail",
            max_long_edge=512,
            quality=78,
            format="webp",
        )
        preview_key_same_edge = thumbnails._derivative_cache_key_str(
            path,
            kind="preview",
            max_long_edge=512,
            quality=78,
            format="webp",
        )

        assert thumbnail_key != preview_key_same_edge

    def test_thumbnail_512_not_used_as_preview_1440(self, isolated_app: TestClient, temp_gallery: Path):
        """Calling thumbnail at 512 then preview at 1440 must produce different sizes."""
        path = temp_gallery / "album_a" / "001.png"

        thumb_resp = isolated_app.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 512})
        assert thumb_resp.status_code == 200
        with PILImage.open(BytesIO(thumb_resp.content)) as img:
            thumb_size = img.size

        preview_resp = isolated_app.get("/api/preview", params={"path": str(path), "max_long_edge": 1440})
        assert preview_resp.status_code == 200
        with PILImage.open(BytesIO(preview_resp.content)) as img:
            preview_size = img.size

        assert thumb_size != preview_size

    def test_preview_1440_not_used_as_thumbnail_512(self, isolated_app: TestClient, temp_gallery: Path):
        """Calling preview at 1440 first then thumbnail at 512 must produce correct thumbnail size."""
        path = temp_gallery / "album_a" / "001.png"

        preview_resp = isolated_app.get("/api/preview", params={"path": str(path), "max_long_edge": 1440})
        assert preview_resp.status_code == 200

        thumb_resp = isolated_app.get("/api/thumbnail", params={"path": str(path), "max_long_edge": 512})
        assert thumb_resp.status_code == 200
        with PILImage.open(BytesIO(thumb_resp.content)) as img:
            assert max(img.size) <= 512
