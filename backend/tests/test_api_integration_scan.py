"""
Purpose:
Verifies the /api/scan endpoint shape, filtering, sort order, pagination, and hot-path contracts.

Guarantees:
* folders and media return stable response fields and natural ordering
* scan pagination and warm/cached dimension paths do not regress

Run when:
* changing scan_directory, scan endpoint response shape, pagination, or ignore policy
* touching warm listing or cached dimension scan behavior
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


class TestScanResponseShape:
    def test_api_scan_rejects_unknown_params(self, isolated_app: TestClient, isolated_gallery_root: Path):
        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(isolated_gallery_root), "unknown_param": "1"},
        )
        assert resp.status_code == 422
        assert "unknown_param" in resp.text

    def test_api_scan_rejects_legacy_image_cursor(self, isolated_app: TestClient, isolated_gallery_root: Path):
        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(isolated_gallery_root), "image_cursor": "100"},
        )
        assert resp.status_code == 422
        assert "image_cursor" in resp.text

    def test_api_scan_rejects_typo_param(self, isolated_app: TestClient, isolated_gallery_root: Path):
        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(isolated_gallery_root), "media_curser": "100"},
        )
        assert resp.status_code == 422
        assert "media_curser" in resp.text

    def test_api_scan_canonical_params_ok(self, isolated_app: TestClient, isolated_gallery_root: Path):
        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(isolated_gallery_root), "limit": "50", "media_cursor": "0"},
        )
        assert resp.status_code == 200

    def test_scan_returns_expected_keys(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) == {
            "folders",
            "media",
            "next_media_cursor",
            "total_images",
            "total_videos",
            "total_assets",
            "index_source",
        }

    def test_folders_have_correct_shape(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        for folder in data["folders"]:
            assert set(folder) == {
                "name",
                "path",
                "type",
                "has_children",
                "cover_images",
                "mtime",
                "image_count",
            }
            assert folder["type"] == "folder"

    def test_images_have_correct_shape(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        for img in data["media"]:
            assert set(img) == {
                "name",
                "path",
                "type",
                "has_children",
                "cover_images",
                "mtime",
                "image_count",
                "width",
                "height",
                "asset_id",
                "metadata_state",
                "derivative_ready",
            }
            assert img["type"] == "image"


class TestScanFiltering:
    def test_skips_hidden_files(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        names = [img["name"] for img in data["media"]]
        assert ".hidden.png" not in names

    def test_skips_non_image_files(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        names = [img["name"] for img in data["media"]]
        assert "note.txt" not in names

    def test_counts_images_correctly(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        # 3 images: 001.png, 002.jpg, 010.png (hidden and .txt skipped)
        assert data["total_images"] == 3
        assert len(data["media"]) == 3

    def test_counts_folders_correctly(self, isolated_app: TestClient, temp_gallery: Path):
        resp = isolated_app.get("/api/scan", params={"path": str(temp_gallery)})
        assert resp.status_code == 200
        data = resp.json()
        # album_a and album_b
        assert len(data["folders"]) == 2


class TestNaturalSortOrder:
    def test_images_sorted_naturally(self, isolated_app: TestClient, temp_gallery: Path):
        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        names = [img["name"] for img in data["media"]]
        assert names == ["001.png", "002.jpg", "010.png"]

    def test_natural_sort_numeric_groups(self, isolated_app: TestClient, isolated_gallery_root: Path):
        from .conftest import create_test_png

        album = isolated_gallery_root / "sort_test"
        album.mkdir()
        for name in ["image2.png", "image10.png", "image1.png", "image20.png"]:
            create_test_png(album / name, size=(64, 64))

        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200
        data = resp.json()
        names = [img["name"] for img in data["media"]]
        assert names == ["image1.png", "image2.png", "image10.png", "image20.png"]


class TestPagination:
    def test_limit_respected(self, isolated_app: TestClient, isolated_gallery_root: Path):
        from .conftest import create_test_png

        album = isolated_gallery_root / "pagination_test"
        album.mkdir()
        for i in range(5):
            create_test_png(album / f"{i:03d}.png", size=(64, 64))

        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["media"]) == 2
        assert data["total_images"] == 5
        assert data["next_media_cursor"] == 2

    def test_basic_limit_pagination(self, isolated_app: TestClient, isolated_gallery_root: Path):
        from .conftest import create_test_png

        album = isolated_gallery_root / "cursor_test"
        album.mkdir()
        for i in range(5):
            create_test_png(album / f"{i:03d}.png", size=(64, 64))

        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["media"]) == 2
        names = [img["name"] for img in data["media"]]
        assert names == ["000.png", "001.png"]

    def test_next_media_cursor_none_at_end(self, isolated_app: TestClient, isolated_gallery_root: Path):
        from .conftest import create_test_png

        album = isolated_gallery_root / "cursor_end_test"
        album.mkdir()
        for i in range(3):
            create_test_png(album / f"{i:03d}.png", size=(64, 64))

        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["next_media_cursor"] is None
        assert data["total_images"] == 3

    def test_total_images_accurate(self, isolated_app: TestClient, isolated_gallery_root: Path):
        from .conftest import create_test_png

        album = isolated_gallery_root / "total_test"
        album.mkdir()
        for i in range(7):
            create_test_png(album / f"{i:03d}.png", size=(64, 64))

        resp = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_images"] == 7
        assert len(data["media"]) == 3

    def test_media_invariant_no_gaps(self, isolated_app: TestClient, isolated_gallery_root: Path):
        from .conftest import create_test_png

        album = isolated_gallery_root / "media_cursor_test"
        album.mkdir()
        for name in ["asset1.png", "asset3.png", "asset5.png"]:
            create_test_png(album / name, size=(64, 64))
        for name in ["asset2.mp4", "asset4.mp4"]:
            (album / name).write_bytes(b"video")

        first = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 2, "media_cursor": 0},
        )
        second = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 2, "media_cursor": first.json()["next_media_cursor"]},
        )
        third = isolated_app.get(
            "/api/scan",
            params={"path": str(album), "limit": 2, "media_cursor": second.json()["next_media_cursor"]},
        )

        assert [item["name"] for item in first.json()["media"]] == ["asset1.png", "asset2.mp4"]
        assert [item["name"] for item in second.json()["media"]] == ["asset3.png", "asset4.mp4"]
        assert [item["name"] for item in third.json()["media"]] == ["asset5.png"]
        assert first.json()["next_media_cursor"] == 2
        assert second.json()["next_media_cursor"] == 4
        assert third.json()["next_media_cursor"] is None


class TestScanHotPathContract:
    def test_scan_hot_path_does_not_open_images(
        self, isolated_app: TestClient, temp_gallery: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Scan hot path must not call PIL.Image.open."""
        from PIL import Image as PILImage

        opened: list[str] = []

        original_open = PILImage.open

        def tracking_open(*args, **kwargs):  # noqa: ANN002, ANN003
            opened.append(str(args[0]) if args else "unknown")
            return original_open(*args, **kwargs)

        monkeypatch.setattr(PILImage, "open", tracking_open)

        album = temp_gallery / "album_a"
        resp = isolated_app.get("/api/scan", params={"path": str(album)})
        assert resp.status_code == 200

        # The hot path should not trigger any image opens - only the
        # background indexer tasks would, but those are disabled.
        assert len(opened) == 0, f"PIL.Image.open was called {len(opened)} times on: {opened}"
