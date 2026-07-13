"""Typed search/facet contracts and canonical scope parity regressions.

Purpose:
Verify FastAPI exposes validated search DTOs and that folder, library, and all
scope semantics are shared by search and facets.

Guarantees:
* OpenAPI documents search, metadata-search, facet, and public error schemas
* current remains a GET alias whose response uses canonical folder scope
* folder/library/all search and facets isolate the same active assets
* legacy grouped arrays are projections of canonical media rows
* metadata-search total is global rather than the returned page length
* blocking search/facet path operations are synchronous and map index failures

Run when:
* changing search/facet Pydantic models, FastAPI signatures, scope resolution,
  OpenAPI responses, compatibility arrays, totals, or error mapping
"""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.facets as facets_module
import backend.search as search_module
from backend.metadata_store import index_file, register_library, upsert_metadata_result
from backend.paths import InvalidPathError

from .conftest import create_test_png


def _seed_scoped_image(root: Path, name: str, *, model: str, prompt: str = "globaltotalneedle") -> Path:
    image = root / name
    create_test_png(image)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    assert upsert_metadata_result(
        image,
        {
            "prompt": prompt,
            "params": {"Model": model, "Seed": name},
            "width": 64,
            "height": 64,
        },
    )
    return image


def _seed_two_library_scope(root: Path) -> tuple[dict, dict, Path]:
    first_root = root / "first"
    second_root = root / "second"
    first_root.mkdir()
    second_root.mkdir()
    nested = first_root / "nested"
    nested.mkdir()
    first = register_library(first_root, name="First Library")
    second = register_library(second_root, name="Second Library")
    _seed_scoped_image(first_root, "scope_needle_first.png", model="Model First")
    _seed_scoped_image(nested, "scope_needle_nested.png", model="Model Nested")
    _seed_scoped_image(second_root, "scope_needle_second.png", model="Model Second")
    return first, second, nested


def test_openapi_documents_typed_search_and_error_contracts(isolated_app: TestClient) -> None:
    schema = isolated_app.get("/openapi.json").json()
    paths = schema["paths"]
    assert paths["/api/search"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SearchResponse"
    }
    assert paths["/api/search-metadata"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataSearchResponse"
    }
    assert paths["/api/facets"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FacetResponse"
    }
    for status in ("400", "404", "503", "500"):
        assert paths["/api/search"]["get"]["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/APIErrorResponse"
        }


def test_search_and_facets_share_folder_library_all_scope_semantics(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    first, second, nested = _seed_two_library_scope(isolated_gallery_root)

    all_search = isolated_app.get("/api/search", params={"q": "scope_needle", "scope": "all"}).json()
    assert {row["library_id"] for row in all_search["media"]} == {first["id"], second["id"]}

    library_search = isolated_app.get(
        "/api/search",
        params={"q": "scope_needle", "scope": "library", "library_id": first["id"]},
    )
    assert library_search.status_code == 200
    assert library_search.json()["scope"] == "library"
    assert {row["library_id"] for row in library_search.json()["media"]} == {first["id"]}
    assert len(library_search.json()["media"]) == 2

    folder_params = {
        "q": "scope_needle",
        "scope": "folder",
        "library_id": first["id"],
        "path": str(nested),
    }
    folder_search = isolated_app.get("/api/search", params=folder_params)
    assert folder_search.status_code == 200
    assert folder_search.json()["scope"] == "folder"
    assert [row["name"] for row in folder_search.json()["media"]] == ["scope_needle_nested.png"]

    legacy = isolated_app.get(
        "/api/search",
        params={**folder_params, "scope": "current"},
    )
    assert legacy.status_code == 200
    assert legacy.json()["scope"] == "folder"
    assert legacy.json()["media"] == folder_search.json()["media"]

    all_facets = isolated_app.get("/api/facets", params={"scope": "all"}).json()
    assert {item["value"] for item in all_facets["model"]} == {"Model First", "Model Nested", "Model Second"}

    library_facets = isolated_app.get(
        "/api/facets",
        params={"scope": "library", "library_id": first["id"]},
    ).json()
    assert {item["value"] for item in library_facets["model"]} == {"Model First", "Model Nested"}

    folder_facets = isolated_app.get(
        "/api/facets",
        params={"scope": "folder", "library_id": first["id"], "path": str(nested)},
    ).json()
    assert folder_facets["model"] == [{"value": "Model Nested", "count": 1}]


def test_scope_validation_status_policy(isolated_app: TestClient, isolated_gallery_root: Path) -> None:
    first, second, _nested = _seed_two_library_scope(isolated_gallery_root)
    second_root = Path(second["root_path"])

    outside = isolated_app.get(
        "/api/search",
        params={
            "q": "scope_needle",
            "scope": "folder",
            "library_id": first["id"],
            "path": str(second_root),
        },
    )
    assert outside.status_code == 404

    missing_library = isolated_app.get(
        "/api/search",
        params={"q": "scope_needle", "scope": "library"},
    )
    assert missing_library.status_code == 422

    invalid_scope = isolated_app.get(
        "/api/search",
        params={"q": "scope_needle", "scope": "nearby"},
    )
    assert invalid_scope.status_code == 422


def test_folder_scope_default_and_validation_branches(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    missing_path = isolated_app.get("/api/search", params={"q": "", "scope": "current"})
    assert missing_path.status_code == 422

    library = register_library(isolated_gallery_root, name="Default Library")
    default_scope = isolated_app.get("/api/search", params={"q": "", "scope": "current"})
    assert default_scope.status_code == 200
    assert default_scope.json()["root"] == str(isolated_gallery_root.resolve())

    relative = isolated_app.get(
        "/api/search",
        params={"q": "", "scope": "folder", "library_id": library["id"], "path": "relative/folder"},
    )
    assert relative.status_code == 422

    unknown_library = isolated_app.get(
        "/api/search",
        params={"q": "", "scope": "library", "library_id": library["id"] + 1000},
    )
    assert unknown_library.status_code == 404


def test_legacy_grouped_arrays_are_canonical_media_projections(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    _seed_two_library_scope(isolated_gallery_root)
    response = isolated_app.get("/api/search", params={"q": "scope_needle", "scope": "all"})
    assert response.status_code == 200
    data = response.json()
    grouped = [*data["photos"], *data["videos"], *data["prompt"]]
    assert sorted(row["asset_id"] for row in grouped) == sorted(row["asset_id"] for row in data["media"])
    assert {row["asset_id"]: row for row in grouped} == {row["asset_id"]: row for row in data["media"]}


def test_search_metadata_total_is_global_not_page_length(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    _seed_two_library_scope(isolated_gallery_root)
    response = isolated_app.get("/api/search-metadata", params={"q": "globaltotalneedle", "limit": 1})
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert len(response.json()["results"]) == 1


def test_search_and_facet_index_failures_map_to_503(
    isolated_app: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_module, "search_index", lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError())
    )
    search = isolated_app.get("/api/search", params={"q": "needle", "scope": "all"})
    assert search.status_code == 503

    monkeypatch.setattr(
        facets_module, "build_facets", lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError())
    )
    facets = isolated_app.get("/api/facets", params={"scope": "all"})
    assert facets.status_code == 503


def test_search_error_mapping_fielded_dispatch_and_decimal_cursor(
    isolated_app: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fielded_search(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {
            "query": args[0],
            "scope": "all",
            "root": "/",
            "albums": [],
            "photos": [],
            "videos": [],
            "prompt": [],
            "media": [],
            "next_cursor": None,
            "has_more": False,
            "returned": 0,
            "limit": args[3],
        }

    monkeypatch.setattr(search_module, "search_index_fielded", fielded_search)
    fielded = isolated_app.get(
        "/api/search",
        params={"q": 'model:"Flux Dev"', "scope": "all", "cursor": "12"},
    )
    assert fielded.status_code == 200
    assert fielded.headers["deprecation"] == "true"
    assert captured["args"] == ('model:"Flux Dev"', "all", None, 50, "12")

    monkeypatch.setattr(
        search_module, "search_index", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad cursor"))
    )
    invalid_cursor = isolated_app.get("/api/search", params={"q": "needle", "scope": "all"})
    assert invalid_cursor.status_code == 400

    monkeypatch.setattr(
        search_module, "search_index", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private"))
    )
    internal = isolated_app.get("/api/search", params={"q": "needle", "scope": "all"})
    assert internal.status_code == 500
    assert "private" not in internal.text

    monkeypatch.setattr(
        search_module, "search_metadata", lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError())
    )
    metadata_unavailable = isolated_app.get("/api/search-metadata", params={"q": "needle"})
    assert metadata_unavailable.status_code == 503


def test_search_path_filter_and_cleanup_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    safe_path = tmp_path / "safe.png"
    safe_path.write_bytes(b"safe")
    missing_path = tmp_path / "missing.png"

    def resolve(value: str) -> Path:
        if value == "invalid":
            raise InvalidPathError("invalid")
        return Path(value).resolve()

    monkeypatch.setattr(search_module, "resolve_path", resolve)
    monkeypatch.setattr(search_module, "is_path_safe", lambda value: value != missing_path.resolve())
    safe, stale = search_module._filter_safe_paths(
        [{"path": str(safe_path)}, {"path": str(missing_path)}, {"path": "invalid"}]
    )
    assert safe == [{"path": str(safe_path)}]
    assert stale == {str(missing_path), "invalid"}

    library_root = tmp_path / "library"
    stale_inside = library_root / "gone.png"
    stale_outside = tmp_path / "elsewhere" / "gone.png"
    cleanup_calls: list[str] = []
    monkeypatch.setattr(
        "backend.metadata_store.list_libraries",
        lambda: [{"root_path": str(library_root), "import_paths": [{"path": str(library_root)}]}],
    )
    monkeypatch.setattr(
        search_module,
        "cleanup_stale_index",
        lambda _library_id, root, **_kwargs: cleanup_calls.append(root) or 2,
    )
    removed = search_module._cleanup_registered_library_roots({str(stale_inside), str(stale_outside)})
    assert removed == 2
    assert cleanup_calls == [str(library_root.resolve())]


def test_blocking_search_and_facet_operations_are_sync() -> None:
    assert not inspect.iscoroutinefunction(search_module.api_search)
    assert not inspect.iscoroutinefunction(search_module.api_search_metadata)
    assert not inspect.iscoroutinefunction(facets_module.api_facets)
