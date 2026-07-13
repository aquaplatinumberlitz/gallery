"""Canonical Search V2 request and legacy-adapter contracts.

Purpose:
Verify the versioned POST search contract validates canonical ID-based scopes
and shares lexical execution with the legacy GET adapter.

Guarantees:
Folder requests never accept absolute/traversing paths, request bounds are
enforced, disabled modes are explicit, and equivalent GET/POST requests return
the same rows.

Run when:
Changing Search V2 models, scope authorization, request limits, or legacy
search compatibility.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.metadata_store import index_file, register_library
from backend.models import SearchAllScopeV1, SearchQueryRequestV1

from .conftest import create_test_png


def _seed_search_v2_library(root: Path) -> tuple[dict, Path]:
    nested = root / "CaseSensitive" / "Portraits"
    nested.mkdir(parents=True)
    library = register_library(root, name="Search V2")
    image = nested / "canonical_needle.png"
    create_test_png(image)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64)
    return library, nested


def test_search_v2_folder_scope_and_legacy_get_have_lexical_parity(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    library, nested = _seed_search_v2_library(isolated_gallery_root)
    import_path = library["import_paths"][0]
    request = {
        "schema_version": 1,
        "mode": "lexical",
        "text": "canonical_needle",
        "scope": {
            "kind": "folder",
            "library_id": library["id"],
            "import_path_id": import_path["id"],
            "relative_path": "CaseSensitive/Portraits",
        },
        "filters": {"prompt_groups": [], "workflow_groups": []},
        "cursor": None,
        "limit": 60,
    }
    v2 = isolated_app.post("/api/search/query", json=request)
    legacy = isolated_app.get(
        "/api/search",
        params={
            "q": "canonical_needle",
            "scope": "folder",
            "library_id": library["id"],
            "path": str(nested),
            "limit": 60,
        },
    )
    assert v2.status_code == legacy.status_code == 200
    assert v2.json()["media"] == legacy.json()["media"]
    assert v2.json()["scope"] == "folder"
    assert v2.json()["root"] == str(nested.resolve())


def test_search_v2_scope_and_request_bounds(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    library, _nested = _seed_search_v2_library(isolated_gallery_root)
    import_path = library["import_paths"][0]
    base = {
        "schema_version": 1,
        "mode": "lexical",
        "text": "needle",
        "scope": {"kind": "all"},
        "filters": {"prompt_groups": [], "workflow_groups": []},
        "limit": 60,
    }

    for field, value in (("schema_version", 2), ("limit", 101), ("text", "x" * 513)):
        response = isolated_app.post("/api/search/query", json={**base, field: value})
        assert response.status_code == 422

    absolute = isolated_app.post(
        "/api/search/query",
        json={
            **base,
            "scope": {
                "kind": "folder",
                "library_id": library["id"],
                "import_path_id": import_path["id"],
                "relative_path": "/absolute/path",
            },
        },
    )
    assert absolute.status_code == 422

    traversal = isolated_app.post(
        "/api/search/query",
        json={
            **base,
            "scope": {
                "kind": "folder",
                "library_id": library["id"],
                "import_path_id": import_path["id"],
                "relative_path": "safe/../escape",
            },
        },
    )
    assert traversal.status_code == 422

    wrong_import = isolated_app.post(
        "/api/search/query",
        json={
            **base,
            "scope": {
                "kind": "folder",
                "library_id": library["id"],
                "import_path_id": import_path["id"] + 1000,
                "relative_path": "",
            },
        },
    )
    assert wrong_import.status_code == 404

    disabled = isolated_app.post("/api/search/query", json={**base, "mode": "raw"})
    assert disabled.status_code == 409
    assert disabled.json()["detail"]["error"] == "feature_disabled"

    schema = isolated_app.get("/openapi.json").json()
    operation = schema["paths"]["/api/search/query"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SearchQueryRequestV1"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SearchResponse"
    }


def test_search_v2_decoded_body_limit_and_persistable_shape(isolated_app: TestClient) -> None:
    predicate = {"property": "filename_prefix", "op": "eq", "value": "\n" * 512}
    oversized = {
        "schema_version": 1,
        "mode": "workflow",
        "text": "",
        "scope": {"kind": "all"},
        "filters": {
            "prompt_groups": [],
            "workflow_groups": [{"node_type": "SaveImage", "predicates": [predicate] * 8} for _ in range(4)],
        },
        "limit": 60,
    }
    response = isolated_app.post("/api/search/query", json=oversized)
    assert response.status_code == 422
    assert "32 KiB" in response.text

    request = SearchQueryRequestV1(
        text="CaseSensitive",
        scope=SearchAllScopeV1(kind="all"),
        cursor="opaque",
        limit=25,
    )
    assert request.persistable() == {
        "schema_version": 1,
        "mode": "lexical",
        "text": "CaseSensitive",
        "scope": {"kind": "all"},
        "filters": {"prompt_groups": [], "workflow_groups": []},
    }


def test_legacy_get_keeps_its_pre_v2_limit_bound(isolated_app: TestClient) -> None:
    response = isolated_app.get("/api/search", params={"q": "", "scope": "all", "limit": 200})
    assert response.status_code == 200
    assert response.json()["limit"] == 200
