"""DB-only search response and album aggregation regressions.

Purpose:
Verify search returns catalog-authorized rows and browse-equivalent album
metadata without enumerating or validating source files per result.

Guarantees:
* album suggestions use bounded catalog aggregation for direct counts/covers
* album suggestions remain first-page-only and limited to twelve
* search and metadata-search routes do not call stale path filters/cleanup
* all-scope media identifies its owning registered library
* registered import-path containment excludes corrupted catalog rows

Run when:
* changing search response authorization, album aggregation, browse folder
  counts, library/import-path joins, or stale catalog reconciliation ownership
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.albums as albums_module
import backend.metadata_store.search_store as search_store_module
import backend.search as search_module
from backend.metadata_store import (
    _connect,
    get_catalog_browse_listing,
    index_directory_tree,
    index_file,
    register_library,
    search_index,
    upsert_metadata_result,
)

from .conftest import create_test_png


def _seed_album(root: Path, *, album_name: str = "CatalogNeedleAlbum", images: int = 4) -> dict:
    library = register_library(root, name=f"Library {root.name}")
    album = root / album_name
    album.mkdir()
    base_ns = 1_760_000_000_000_000_000
    for index in range(images):
        image = album / f"catalogneedle_{index}.png"
        create_test_png(image)
        timestamp = base_ns + index * 1_000_000
        os.utime(image, ns=(timestamp, timestamp))
    index_directory_tree(root, include_metadata=False)
    return library


def test_album_suggestions_reuse_browse_aggregation_without_filesystem_calls(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    library = _seed_album(isolated_gallery_root)
    browse = get_catalog_browse_listing(int(library["id"]), path=isolated_gallery_root)
    browse_album = next(folder for folder in browse["folders"] if folder.name == "CatalogNeedleAlbum")

    def filesystem_call_forbidden(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("search album aggregation must stay DB-only")

    monkeypatch.setattr(albums_module, "build_album_metadata", filesystem_call_forbidden)
    monkeypatch.setattr(albums_module, "first_images_in_dir", filesystem_call_forbidden)
    monkeypatch.setattr(albums_module, "count_images_in_dir", filesystem_call_forbidden)
    monkeypatch.setattr(albums_module, "has_any_children", filesystem_call_forbidden)
    monkeypatch.setattr(search_store_module, "Path", PurePath)
    monkeypatch.setattr(
        search_store_module,
        "os",
        SimpleNamespace(sep=os.sep, scandir=filesystem_call_forbidden),
    )

    result = search_index("CatalogNeedleAlbum", "all", limit=20)
    assert len(result["albums"]) == 1
    album = result["albums"][0]
    assert album["library_id"] == library["id"]
    assert album["library_name"] == library["name"]
    assert album["image_count"] == browse_album.image_count == 4
    assert album["cover_images"] == browse_album.cover_images
    assert album["has_children"] == browse_album.has_children is True

    second_page = search_index("CatalogNeedleAlbum", "all", limit=20, cursor=1)
    assert second_page["albums"] == []


def test_album_suggestions_keep_twelve_result_limit(isolated_gallery_root: Path) -> None:
    library = register_library(isolated_gallery_root, name="Album limit")
    for index in range(15):
        album = isolated_gallery_root / f"NeedleAlbum{index:02d}"
        album.mkdir()
        create_test_png(album / "cover.png")
    index_directory_tree(isolated_gallery_root, include_metadata=False)

    result = search_index("NeedleAlbum", "all", limit=50)
    assert len(result["albums"]) == 12
    assert {album["library_id"] for album in result["albums"]} == {library["id"]}


def test_search_routes_do_not_filter_paths_or_schedule_cleanup(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_library(isolated_gallery_root, name="DB only")
    image = isolated_gallery_root / "dbonlyneedle.png"
    create_test_png(image)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    assert upsert_metadata_result(image, {"prompt": "dbonlyneedle prompt"})

    def legacy_hot_path_forbidden(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("search must not use response-time filesystem filtering")

    monkeypatch.setattr(search_module, "_filter_safe_paths", legacy_hot_path_forbidden)
    monkeypatch.setattr(search_module, "_schedule_stale_cleanup", legacy_hot_path_forbidden)

    search = isolated_app.get("/api/search", params={"q": "dbonlyneedle", "scope": "all"})
    assert search.status_code == 200
    assert search.json()["media"]

    metadata = isolated_app.get("/api/search-metadata", params={"q": "dbonlyneedle"})
    assert metadata.status_code == 200
    assert metadata.json()["results"]


def test_all_scope_media_includes_owning_library_context(isolated_gallery_root: Path) -> None:
    roots = [isolated_gallery_root / "first", isolated_gallery_root / "second"]
    libraries = []
    for index, root in enumerate(roots):
        root.mkdir()
        library = register_library(root, name=f"Context Library {index + 1}")
        libraries.append(library)
        image = root / f"librarycontextneedle_{index}.png"
        create_test_png(image)
        stat = image.stat()
        assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)

    result = search_index("librarycontextneedle", "all", limit=10)
    assert len(result["media"]) == 2
    assert {(row["library_id"], row["library_name"]) for row in result["media"]} == {
        (library["id"], library["name"]) for library in libraries
    }
    assert all(isinstance(row["asset_id"], int) for row in result["media"])


def test_corrupted_asset_outside_registered_import_path_is_excluded(isolated_gallery_root: Path) -> None:
    library_root = isolated_gallery_root / "registered"
    library_root.mkdir()
    library = register_library(library_root, name="Containment")
    corrupt_path = str(isolated_gallery_root / "outside" / "containmentneedle.png")

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO assets(library_id, path, parent_path, name, type, mtime_ns, size, offline)
            VALUES (?, ?, ?, 'containmentneedle.png', 'image', 1000000000, 8, 0)
            """,
            (library["id"], corrupt_path, str(Path(corrupt_path).parent)),
        )
        conn.execute(
            """
            INSERT INTO file_index(path, name, parent_path, type, mtime, mtime_ns, size, library_id)
            VALUES (?, 'containmentneedle.png', ?, 'image', 1.0, 1000000000, 8, ?)
            """,
            (corrupt_path, str(Path(corrupt_path).parent), library["id"]),
        )
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
            ("containmentneedle.png", corrupt_path, str(Path(corrupt_path).parent)),
        )

    result = search_index("containmentneedle", "all")
    assert result["media"] == []


def test_corrupted_traversal_asset_inside_raw_prefix_is_excluded(isolated_gallery_root: Path) -> None:
    library = register_library(isolated_gallery_root, name="Traversal containment")
    corrupt_path = f"{isolated_gallery_root.resolve()}{os.sep}safe{os.sep}..{os.sep}traversalneedle.png"
    parent_path = str(Path(corrupt_path).parent)

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO assets(library_id, path, parent_path, name, type, mtime_ns, size, offline)
            VALUES (?, ?, ?, 'traversalneedle.png', 'image', 1000000000, 8, 0)
            """,
            (library["id"], corrupt_path, parent_path),
        )
        conn.execute(
            """
            INSERT INTO file_index(path, name, parent_path, type, mtime, mtime_ns, size, library_id)
            VALUES (?, 'traversalneedle.png', ?, 'image', 1.0, 1000000000, 8, ?)
            """,
            (corrupt_path, parent_path, library["id"]),
        )
        conn.execute(
            "INSERT INTO file_index_fts(name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
            ("traversalneedle.png", corrupt_path, parent_path),
        )

    assert search_index("traversalneedle", "all")["media"] == []
