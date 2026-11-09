"""Image pipeline plan B3: versioned thumbnail/preview URLs.

Purpose:
Pin the additive `content_version` / `cover_versions` response fields and the optional `v` query parameter of
`/api/thumbnail` and `/api/preview`. Before this, no URL carried the file identity, so every thumbnail response
had to be revalidated (one 304 round trip per image on every revisit).

Guarantees:
Browse (virtual root and folder listings), search (media and album rows) and related results expose
`content_version` as `"<mtime_ns>-<size>"` of the catalog asset and `cover_versions` aligned with
`cover_images`; `/api/thumbnail` and `/api/preview` answer `public, max-age=31536000, immutable` only when `v`
equals the source identity on disk right now (200 and 304 alike, same ETag); an absent, malformed or stale `v`
keeps `public, max-age=0, must-revalidate`; a rewritten source invalidates the old `v`.

Run when:
Changing browse/search/related item shapes, `content_version` or `cover_versions`, the `v` parameter, or the
cache headers of the derivative endpoints.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.metadata_store import index_directory_tree, index_file, list_libraries
from backend.metadata_store._db import open_connection
from backend.related_ranking import rank_related_metadata
from backend.search_scope import SearchScopeContext
from tests.conftest import create_test_png
from tests.test_related_assets_ranking import _seed_fixture

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "public, max-age=0, must-revalidate"


def content_version(mtime_ns: int, size: int) -> str:
    """The documented public identity, spelled out independently of the implementation under test."""
    return f"{mtime_ns}-{size}"


def _assets_by_path(db_path: Path) -> dict[str, tuple[int, int]]:
    with open_connection(db_path) as conn:
        return {
            path: (mtime_ns, size) for path, mtime_ns, size in conn.execute("SELECT path, mtime_ns, size FROM assets")
        }


def _version_of(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_mtime_ns}-{stat.st_size}"


def test_content_version_is_mtime_ns_dash_size_and_none_when_unknown() -> None:
    from backend.files import content_version as implementation

    assert implementation(1_700_000_000_123_456_789, 4096) == "1700000000123456789-4096"
    assert implementation(None, 10) is None
    assert implementation(10, None) is None


def test_browse_listing_exposes_content_version_and_aligned_cover_versions(
    isolated_app: TestClient, temp_gallery: Path, isolated_metadata_db: Path
) -> None:
    create_test_png(temp_gallery / "top.png", size=(320, 240))  # a cover for the library root itself
    index_directory_tree(temp_gallery)
    library_id = int(list_libraries()[0]["id"])
    identities = _assets_by_path(isolated_metadata_db)

    listing = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(temp_gallery / "album_a")})
    assert listing.status_code == 200
    media = listing.json()["media"]
    assert media, "fixture album must list images"
    for item in media:
        assert item["content_version"] == content_version(*identities[item["path"]])
        assert item["content_version"] == _version_of(Path(item["path"])), "catalog identity matches the file"

    root = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(temp_gallery)})
    folders = {folder["name"]: folder for folder in root.json()["folders"]}
    assert set(folders) >= {"album_a", "album_b"}
    for folder in folders.values():
        assert folder["content_version"] is None
        assert len(folder["cover_versions"]) == len(folder["cover_images"]) > 0
        for cover, version in zip(folder["cover_images"], folder["cover_versions"], strict=True):
            assert version == content_version(*identities[cover])

    virtual_root = isolated_app.get("/api/browse", params={"library_id": library_id})
    assert virtual_root.status_code == 200
    for folder in virtual_root.json()["folders"]:
        assert len(folder["cover_versions"]) == len(folder["cover_images"]) > 0
        for cover, version in zip(folder["cover_images"], folder["cover_versions"], strict=True):
            assert version == content_version(*identities[cover])


def test_search_results_expose_content_version_and_cover_versions(
    isolated_app: TestClient, temp_gallery: Path, isolated_metadata_db: Path
) -> None:
    library_id = int(list_libraries()[0]["id"])
    identities = _assets_by_path(isolated_metadata_db)

    media_search = isolated_app.get(
        "/api/search", params={"q": "001", "scope": "library", "library_id": library_id, "limit": 20}
    )
    assert media_search.status_code == 200
    media = media_search.json()["media"]
    assert any(item["name"] == "001.png" for item in media)
    for item in media:
        assert item["content_version"] == content_version(*identities[item["path"]])

    album_search = isolated_app.get(
        "/api/search", params={"q": "album_a", "scope": "library", "library_id": library_id, "limit": 20}
    )
    albums = album_search.json()["albums"]
    assert albums and albums[0]["name"] == "album_a"
    assert len(albums[0]["cover_versions"]) == len(albums[0]["cover_images"]) > 0
    for cover, version in zip(albums[0]["cover_images"], albums[0]["cover_versions"], strict=True):
        assert version == content_version(*identities[cover])


def test_related_results_expose_content_version(isolated_gallery_root: Path, isolated_metadata_db: Path) -> None:
    primary, _secondary, ids = _seed_fixture(isolated_gallery_root)
    context = SearchScopeContext(kind="library", library_id=primary["id"], library_name=primary["name"])

    results = rank_related_metadata(ids["reference"], context, profile="related", limit=60)

    assert results
    with open_connection(isolated_metadata_db) as conn:
        identities = {row[0]: (row[1], row[2]) for row in conn.execute("SELECT id, mtime_ns, size FROM assets")}
    for item in results:
        assert item.content_version == content_version(*identities[item.asset_id])


@pytest.fixture
def versioned(isolated_app: TestClient, temp_gallery: Path) -> dict[str, Any]:
    path = temp_gallery / "album_a" / "001.png"
    return {"client": isolated_app, "path": path, "v": _version_of(path)}


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [("/api/thumbnail", {"max_long_edge": 512}), ("/api/thumbnail", {"max_long_edge": 256}), ("/api/preview", {})],
)
def test_a_matching_v_makes_the_response_immutable_and_only_then(
    versioned: dict[str, Any], endpoint: str, params: dict[str, Any]
) -> None:
    client: TestClient = versioned["client"]
    base = {"path": str(versioned["path"]), **params}

    plain = client.get(endpoint, params=base)
    matching = client.get(endpoint, params={**base, "v": versioned["v"]})
    stale = client.get(endpoint, params={**base, "v": "1-1"})
    malformed = client.get(endpoint, params={**base, "v": "not-a-version"})
    empty = client.get(endpoint, params={**base, "v": ""})

    assert plain.status_code == matching.status_code == stale.status_code == 200
    assert plain.headers["cache-control"] == REVALIDATE
    assert matching.headers["cache-control"] == IMMUTABLE
    assert stale.headers["cache-control"] == REVALIDATE
    assert malformed.headers["cache-control"] == REVALIDATE
    assert empty.headers["cache-control"] == REVALIDATE
    assert plain.headers["etag"] == matching.headers["etag"] == stale.headers["etag"]
    assert matching.content == plain.content


def test_a_conditional_request_with_a_matching_v_is_a_304_that_is_also_immutable(
    versioned: dict[str, Any],
) -> None:
    client: TestClient = versioned["client"]
    base = {"path": str(versioned["path"])}
    etag = client.get("/api/thumbnail", params=base).headers["etag"]

    matching = client.get("/api/thumbnail", params={**base, "v": versioned["v"]}, headers={"If-None-Match": etag})
    stale = client.get("/api/thumbnail", params={**base, "v": "1-1"}, headers={"If-None-Match": etag})

    assert matching.status_code == 304
    assert matching.headers["cache-control"] == IMMUTABLE
    assert matching.headers["etag"] == etag
    assert stale.status_code == 304
    assert stale.headers["cache-control"] == REVALIDATE


def test_asset_id_requests_honour_v_too(versioned: dict[str, Any], isolated_metadata_db: Path) -> None:
    client: TestClient = versioned["client"]
    first = client.get("/api/thumbnail", params={"path": str(versioned["path"])})
    assert first.status_code == 200
    with open_connection(isolated_metadata_db) as conn:
        asset_id = conn.execute("SELECT id FROM assets WHERE path = ?", (str(versioned["path"]),)).fetchone()[0]

    response = client.get("/api/thumbnail", params={"asset_id": asset_id, "v": versioned["v"]})

    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE


def test_a_rewritten_source_invalidates_the_old_version(versioned: dict[str, Any]) -> None:
    client: TestClient = versioned["client"]
    path: Path = versioned["path"]
    old_version = versioned["v"]
    assert (
        client.get("/api/thumbnail", params={"path": str(path), "v": old_version}).headers["cache-control"] == IMMUTABLE
    )

    create_test_png(path, size=(900, 700))
    os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))
    stat = path.stat()
    assert index_file(path, path.name, path.parent, "image", stat.st_mtime, stat.st_size, 900, 700)  # rescan
    new_version = _version_of(path)
    assert new_version != old_version

    stale = client.get("/api/thumbnail", params={"path": str(path), "v": old_version})
    fresh = client.get("/api/thumbnail", params={"path": str(path), "v": new_version})

    assert stale.status_code == fresh.status_code == 200
    assert stale.headers["cache-control"] == REVALIDATE
    assert fresh.headers["cache-control"] == IMMUTABLE
    assert stale.headers["etag"] == fresh.headers["etag"]
