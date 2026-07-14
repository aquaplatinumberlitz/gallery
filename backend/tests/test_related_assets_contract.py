"""Related Assets R0 vocabulary, fixture, request, response, and error contracts.

Purpose:
Lock the non-semantic product language, deterministic golden fixture cases,
canonical scope validation, and typed `/api/search/related` OpenAPI surface.

Guarantees:
Invalid requests return 422; out-of-scope references return 404; inactive or
non-image references return 409; missing and unusable relation indexes remain
distinct; the v1 response is bounded, cursor-free, and excludes its reference.

Run when:
Changing Related Assets request/result/status models, reason codes, reference
authorization, readiness errors, or deterministic relation fixtures.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.related_assets as related_module
from backend.metadata_store import register_library
from backend.metadata_store._db import _connect
from backend.models import RelatedIndexComponentStatusV1, RelatedSearchResultV1, RelatedSearchStatusV1

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "related_assets_v1.json"


def _seed_references(root: Path) -> tuple[dict, dict, dict[str, int]]:
    primary_root = root / "primary"
    secondary_root = root / "secondary"
    primary_root.mkdir()
    secondary_root.mkdir()
    primary = register_library(primary_root, name="Primary relations")
    secondary = register_library(secondary_root, name="Secondary relations")
    ids: dict[str, int] = {}
    with _connect() as conn:
        rows = [
            ("active", primary["id"], primary_root / "active.png", "image", 0, None),
            ("video", primary["id"], primary_root / "clip.mp4", "video", 0, None),
            ("offline", primary["id"], primary_root / "offline.png", "image", 1, None),
            ("outside", secondary["id"], secondary_root / "outside.png", "image", 0, None),
        ]
        for key, library_id, path, asset_type, offline, deleted_at in rows:
            cursor = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  metadata_state, offline, deleted_at, indexed_at
                ) VALUES (?, ?, ?, ?, ?, 1000, 100, 'done', ?, ?, 1)
                """,
                (library_id, str(path), str(path.parent), path.name, asset_type, offline, deleted_at),
            )
            ids[key] = int(cursor.lastrowid)
    return primary, secondary, ids


def _status(metadata_state: str = "ready", visual_state: str = "not_ready") -> RelatedSearchStatusV1:
    return RelatedSearchStatusV1(
        metadata=RelatedIndexComponentStatusV1(
            index_name="generation_signatures",
            state=metadata_state,
            usable=metadata_state in {"ready", "degraded"},
        ),
        visual=RelatedIndexComponentStatusV1(
            index_name="visual_fingerprints",
            state=visual_state,
            usable=visual_state in {"ready", "degraded"},
        ),
    )


def test_relation_fixture_covers_required_cases_and_stable_reasons() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assets = {item["key"]: item for item in fixture["assets"]}
    assert fixture["schema_version"] == 1
    assert fixture["reference"] == "reference"
    assert {
        "same_exact_recorded_settings",
        "same_family_different_seed",
        "same_model_unrelated_prompt",
        "shared_lora_unrelated_prompt",
        "rare_prompt_with_common_boilerplate",
        "missing_metadata",
        "malformed_metadata",
        "resized_variant",
        "reencoded_variant",
        "light_color_change",
        "large_crop_limit",
        "mirror_limit",
        "rotation_limit",
        "cross_library_match",
        "inactive_match",
    } <= assets.keys()
    assert assets["same_exact_recorded_settings"]["expected"] == {
        "profile": "related",
        "tier": 100,
        "reasons": ["same_exact_signature", "same_recipe", "same_generation_family"],
    }
    assert assets["same_family_different_seed"]["expected"]["reasons"] == [
        "same_recipe",
        "same_generation_family",
    ]
    assert all(
        asset["expected"]["reasons"] for asset in assets.values() if asset.get("expected", {}).get("tier") is not None
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": 2},
        {"profile": "semantic"},
        {"limit": 0},
        {"limit": 101},
        {"scope": {"kind": "library", "library_id": 0}},
    ],
)
def test_related_request_validation_returns_422(
    isolated_app: TestClient,
    patch: dict,
) -> None:
    request = {
        "schema_version": 1,
        "reference_asset_id": 1,
        "profile": "related",
        "scope": {"kind": "all"},
        "limit": 60,
        **patch,
    }
    response = isolated_app.post("/api/search/related", json=request)
    assert response.status_code == 422


def test_related_reference_scope_type_readiness_and_response_contract(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    primary, _secondary, ids = _seed_references(isolated_gallery_root)
    request = {
        "schema_version": 1,
        "reference_asset_id": ids["active"],
        "profile": "related",
        "scope": {"kind": "library", "library_id": primary["id"]},
    }

    not_ready = isolated_app.post("/api/search/related", json=request)
    assert not_ready.status_code == 409
    assert not_ready.json()["detail"]["error"] == "relation_index_not_ready"
    assert not_ready.json()["detail"]["status"]["metadata"]["state"] == "not_ready"

    outside = isolated_app.post(
        "/api/search/related",
        json={**request, "reference_asset_id": ids["outside"]},
    )
    assert outside.status_code == 404
    import_path_id = primary["import_paths"][0]["id"]
    folder_ready = {
        **request,
        "scope": {"kind": "folder", "library_id": primary["id"], "import_path_id": import_path_id, "relative_path": ""},
    }
    for key in ("video", "offline"):
        conflict = isolated_app.post(
            "/api/search/related",
            json={**request, "reference_asset_id": ids[key]},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["message"] == "Reference must be an active image"

    monkeypatch.setattr(related_module, "_related_status", lambda _asset_id: _status("failed"))
    unusable = isolated_app.post("/api/search/related", json=request)
    assert unusable.status_code == 503
    assert unusable.json()["detail"]["status"]["metadata"]["state"] == "failed"

    monkeypatch.setattr(related_module, "_related_status", lambda _asset_id: _status("ready", "ready"))
    ready = isolated_app.post("/api/search/related", json=request)
    assert ready.status_code == 200
    assert ready.json() == {
        "schema_version": 1,
        "reference_asset_id": ids["active"],
        "profile": "related",
        "scope": {"kind": "library", "library_id": primary["id"]},
        "items": [],
        "returned": 0,
        "limit": 60,
        "status": _status("ready", "ready").model_dump(mode="json"),
    }
    assert all(item["asset_id"] != ids["active"] for item in ready.json()["items"])
    assert isolated_app.post("/api/search/related", json=folder_ready).status_code == 200

    monkeypatch.setattr(
        related_module,
        "_reference_asset",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("private prompt and /local/path")),
    )
    caplog.set_level(logging.ERROR, logger="backend.related_assets")
    failed = isolated_app.post("/api/search/related", json=request)
    assert failed.status_code == 500
    assert failed.json()["detail"] == {"error": "server_error", "message": "Internal server error"}
    assert "private prompt" not in caplog.text
    assert "/local/path" not in caplog.text


def test_related_openapi_documents_request_result_status_and_errors(isolated_app: TestClient) -> None:
    schema = isolated_app.get("/openapi.json").json()
    operation = schema["paths"]["/api/search/related"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RelatedSearchRequestV1"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RelatedSearchResponseV1"
    }
    assert operation["responses"]["409"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RelatedAPIErrorResponseV1"
    }
    assert operation["responses"]["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HTTPValidationError"
    }
    components = schema["components"]["schemas"]
    for name in (
        "RelatedSearchRequestV1",
        "RelatedSearchResultV1",
        "RelatedSearchStatusV1",
        "RelationReasonCodeV1",
        "RelatedAPIErrorResponseV1",
    ):
        assert name in components


def test_combined_profile_merges_metadata_and_visual_evidence_deterministically() -> None:
    base = {
        "asset_id": 2,
        "library_id": 1,
        "library_name": "Library",
        "name": "candidate.png",
        "path": "/library/candidate.png",
        "type": "image",
        "parent_path": "/library",
        "relative_path": "",
        "mtime": 2,
        "width": 512,
        "height": 512,
    }
    metadata = RelatedSearchResultV1(
        **base,
        match_type="related",
        relation_tier=60,
        relation_reasons=["strong_prompt_overlap", "same_model_hash"],
        metadata_score=0.7,
    )
    visual = RelatedSearchResultV1(
        **base,
        match_type="visual_variant",
        relation_tier=80,
        relation_reasons=["visual_variant"],
        visual_distance=2,
    )
    merged = related_module._merge_related_items([metadata], [visual], limit=60)
    assert len(merged) == 1
    assert merged[0].relation_tier == 80
    assert [reason.value for reason in merged[0].relation_reasons] == [
        "strong_prompt_overlap",
        "same_model_hash",
        "visual_variant",
    ]
    assert merged[0].metadata_score == 0.7
    assert merged[0].visual_distance == 2


def test_combined_profile_keeps_metadata_when_reference_visual_coverage_is_missing(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary, _secondary, ids = _seed_references(isolated_gallery_root)
    item = RelatedSearchResultV1(
        asset_id=999,
        library_id=primary["id"],
        library_name=primary["name"],
        name="metadata-related.png",
        path=str(isolated_gallery_root / "primary" / "metadata-related.png"),
        type="image",
        parent_path=str(isolated_gallery_root / "primary"),
        relative_path="",
        mtime=2,
        width=512,
        height=512,
        match_type="related",
        relation_tier=90,
        relation_reasons=["same_recipe", "same_generation_family"],
        metadata_score=1.0,
    )
    monkeypatch.setattr(related_module, "_related_status", lambda _asset_id: _status("ready", "not_ready"))
    monkeypatch.setattr(related_module, "rank_related_metadata", lambda *_args, **_kwargs: [item])
    monkeypatch.setattr(
        related_module,
        "query_visual_variants",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("visual lookup should be skipped")),
    )

    response = isolated_app.post(
        "/api/search/related",
        json={
            "schema_version": 1,
            "reference_asset_id": ids["active"],
            "profile": "related",
            "scope": {"kind": "library", "library_id": primary["id"]},
            "limit": 60,
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["asset_id"] == 999
    assert response.json()["status"]["visual"] == {
        "index_name": "visual_fingerprints",
        "state": "not_ready",
        "usable": False,
        "indexed_count": 0,
        "target_count": 0,
    }
