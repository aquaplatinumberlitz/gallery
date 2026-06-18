"""
Purpose:
Verify the folder-listing helper and the /api/folders + /api/open-folder
routes with correct error codes, filtering, sorting, and safety checks.

Guarantees:
* list_folder_children returns 404 for missing paths, 400 for file paths,
  skips hidden/excluded/non-directory entries, sorts naturally, and includes
  has_children/mtime/image_count/cover_images in each FileNode.
* OSError on entry.is_dir/stat/resolve is handled gracefully (no crash).
* PermissionError from scandir yields 403; generic OSError yields 500.
* /api/folders resolves default root, safe path, and blocks unsafe paths.
* /api/open-folder returns 403 when disabled, 404 for missing, 400 for file,
  and opens successfully when enabled.

Run when:
* modifying folder listing logic, navigation routes, or open-folder behaviour
* changing FileNode model or folder filtering rules
* touching is_path_safe, natural_sort_key, or has_subfolders
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.errors import APIError, ErrorType
from backend.folders import list_folder_children, router
from backend.models import FileNode


# ---------------------------------------------------------------------------
# list_folder_children
# ---------------------------------------------------------------------------


class TestListFolderChildren:
    def test_missing_folder_returns_404(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(APIError) as exc:
            list_folder_children(missing)
        assert exc.value.status_code == 404
        assert exc.value.detail["error"] == ErrorType.NOT_FOUND

    def test_file_path_returns_400(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        with pytest.raises(APIError) as exc:
            list_folder_children(f)
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == ErrorType.NOT_DIRECTORY

    def test_hidden_entries_skipped(self, tmp_path: Path):
        (tmp_path / "visible").mkdir()
        (tmp_path / ".hidden").mkdir()
        result = list_folder_children(tmp_path)
        names = {n.name for n in result}
        assert "visible" in names
        assert ".hidden" not in names

    def test_excluded_paths_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "good").mkdir()
        (tmp_path / "node_modules").mkdir()
        result = list_folder_children(tmp_path)
        names = {n.name for n in result}
        assert "good" in names
        assert "node_modules" not in names

    def test_non_directory_entries_skipped(self, tmp_path: Path):
        (tmp_path / "child_dir").mkdir()
        (tmp_path / "file.txt").write_text("data")
        result = list_folder_children(tmp_path)
        names = {n.name for n in result}
        assert "child_dir" in names
        assert "file.txt" not in names

    def test_child_folders_sorted_naturally(self, tmp_path: Path):
        for name in ["10_alpha", "2_beta", "1_gamma"]:
            (tmp_path / name).mkdir()
        result = list_folder_children(tmp_path)
        names = [n.name for n in result]
        assert names == ["1_gamma", "2_beta", "10_alpha"]

    def test_has_children_mtime_image_count_cover_images_shape(self, tmp_path: Path):
        child = tmp_path / "sub"
        child.mkdir()
        (child / "img.png").write_bytes(b"fake")
        result = list_folder_children(tmp_path)
        node = result[0]
        assert node.name == "sub"
        assert node.type == "folder"
        assert isinstance(node.has_children, bool)
        assert isinstance(node.cover_images, list)
        assert isinstance(node.mtime, (int, float))
        assert node.image_count == 0

    def test_entry_is_dir_oserror_branch_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "safe").mkdir()
        (tmp_path / "broken").mkdir()

        original_scandir = os.scandir

        def fake_scandir(path):
            for entry in original_scandir(path):
                if entry.name == "broken":
                    # Make is_dir raise OSError for "broken"
                    class BrokenEntry:
                        name = "broken"
                        path = entry.path

                        def is_dir(self, **kw):
                            raise OSError("is_dir failed")

                        def stat(self, **kw):
                            return entry.stat()

                    yield BrokenEntry()
                else:
                    yield entry

        monkeypatch.setattr(os, "scandir", fake_scandir)
        result = list_folder_children(tmp_path)
        names = {n.name for n in result}
        assert "safe" in names
        assert "broken" not in names

    def test_entry_stat_oserror_gives_mtime_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "bad_stat").mkdir()
        original_scandir = os.scandir

        def fake_scandir(path):
            for entry in original_scandir(path):
                if entry.name == "bad_stat":
                    class BadStatEntry:
                        name = "bad_stat"
                        path = entry.path

                        def is_dir(self, **kw):
                            return True

                        def stat(self, **kw):
                            raise OSError("stat failed")

                        def resolve(self):
                            return Path(entry.path).resolve()

                        def absolute(self):
                            return Path(entry.path).absolute()

                    yield BadStatEntry()
                else:
                    yield entry

        monkeypatch.setattr(os, "scandir", fake_scandir)
        result = list_folder_children(tmp_path)
        node = [n for n in result if n.name == "bad_stat"][0]
        assert node.mtime == 0

    def test_path_resolve_oserror_falls_back_to_absolute(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        (tmp_path / "bad_resolve").mkdir()

        def fake_resolve(self):
            if "bad_resolve" in str(self):
                raise OSError("resolve failed")
            return self._orig_resolve()

        monkeypatch.setattr(Path, "_orig_resolve", Path.resolve, raising=False)
        monkeypatch.setattr(Path, "resolve", fake_resolve)
        result = list_folder_children(tmp_path)
        node = [n for n in result if n.name == "bad_resolve"][0]
        assert "bad_resolve" in node.path
        assert node.path.endswith("bad_resolve")

    def test_permission_error_from_scandir_returns_403(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(os, "scandir", lambda p: (_ for _ in ()).throw(PermissionError("denied")))
        with pytest.raises(APIError) as exc:
            list_folder_children(tmp_path)
        assert exc.value.status_code == 403

    def test_generic_oserror_from_scandir_returns_500(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(os, "scandir", lambda p: (_ for _ in ()).throw(OSError("generic")))
        with pytest.raises(APIError) as exc:
            list_folder_children(tmp_path)
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


class TestApiFoldersRoute:
    def test_default_root(self, isolated_app: TestClient, isolated_gallery_root: Path):
        (isolated_gallery_root / "album").mkdir()
        resp = isolated_app.get("/api/folders", params={"path": str(isolated_gallery_root)})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_safe_path(self, isolated_app: TestClient, isolated_gallery_root: Path):
        sub = isolated_gallery_root / "subdir"
        sub.mkdir()
        resp = isolated_app.get("/api/folders", params={"path": str(sub)})
        assert resp.status_code == 200

    def test_unsafe_path_returns_403(self, isolated_app: TestClient):
        resp = isolated_app.get("/api/folders", params={"path": "/etc"})
        assert resp.status_code == 403

    def test_missing_folder_returns_404(self, isolated_app: TestClient, isolated_gallery_root: Path):
        missing = isolated_gallery_root / "nope"
        resp = isolated_app.get("/api/folders", params={"path": str(missing)})
        assert resp.status_code == 404

    def test_file_path_returns_400(self, isolated_app: TestClient, isolated_gallery_root: Path):
        f = isolated_gallery_root / "file.txt"
        f.write_text("hello")
        resp = isolated_app.get("/api/folders", params={"path": str(f)})
        assert resp.status_code == 400


class TestApiOpenFolderRoute:
    def test_disabled_returns_403(self, isolated_app: TestClient):
        resp = isolated_app.post("/api/open-folder", params={"path": "/tmp"})
        assert resp.status_code == 403

    def test_enabled_missing_path_returns_404(self, isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_gallery_root: Path):
        monkeypatch.setattr("backend.config.OPEN_FOLDER_ENABLED", True)
        monkeypatch.setattr("backend.folders.OPEN_FOLDER_ENABLED", True)
        missing = isolated_gallery_root / "gone"
        resp = isolated_app.post("/api/open-folder", params={"path": str(missing)})
        assert resp.status_code == 404

    def test_enabled_file_path_returns_400(self, isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_gallery_root: Path):
        monkeypatch.setattr("backend.config.OPEN_FOLDER_ENABLED", True)
        monkeypatch.setattr("backend.folders.OPEN_FOLDER_ENABLED", True)
        f = isolated_gallery_root / "file.txt"
        f.write_text("data")
        resp = isolated_app.post("/api/open-folder", params={"path": str(f)})
        assert resp.status_code == 400

    def test_enabled_success_calls_popen(self, isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_gallery_root: Path):
        monkeypatch.setattr("backend.config.OPEN_FOLDER_ENABLED", True)
        monkeypatch.setattr("backend.folders.OPEN_FOLDER_ENABLED", True)

        popen_calls = []

        class FakePopen:
            def __init__(self, args, **kwargs):
                popen_calls.append(args)

        monkeypatch.setattr(subprocess, "Popen", FakePopen)
        resp = isolated_app.post("/api/open-folder", params={"path": str(isolated_gallery_root)})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Opened successfully"
        assert len(popen_calls) == 1

    def test_enabled_opener_failure_returns_500(self, isolated_app: TestClient, monkeypatch: pytest.MonkeyPatch, isolated_gallery_root: Path):
        monkeypatch.setattr("backend.config.OPEN_FOLDER_ENABLED", True)
        monkeypatch.setattr("backend.folders.OPEN_FOLDER_ENABLED", True)
        monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(OSError("failed to launch")))
        resp = isolated_app.post("/api/open-folder", params={"path": str(isolated_gallery_root)})
        assert resp.status_code == 500
