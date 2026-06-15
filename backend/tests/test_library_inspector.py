from pathlib import Path

from fastapi.testclient import TestClient

from .test_api_integration_metadata_search_facets import _index_gallery_images


def test_library_inspector_empty_query_returns_latest_rows(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    _index_gallery_images(temp_gallery_with_metadata)

    resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "limit": 200})

    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == ""
    assert data["scope"] == "all"
    assert data["returned"] >= 2
    assert data["rows"][0]["path"]
    assert "prompt" not in data["rows"][0]
    assert "negative_prompt" not in data["rows"][0]
    assert "raw_metadata" not in data["rows"][0]
    for key in ("prompt_preview", "has_prompt", "has_negative", "has_lora", "lora_count", "lora_preview", "metadata_detail_available"):
        assert key in data["rows"][0]


def test_library_inspector_does_not_change_search_empty_behavior(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    _index_gallery_images(temp_gallery_with_metadata)

    resp = isolated_app.get("/api/search", params={"q": "", "scope": "all"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["albums"] == []
    assert data["photos"] == []
    assert data["prompt"] == []


def test_library_inspector_reuses_fielded_prompt_and_seed_semantics(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    _index_gallery_images(temp_gallery_with_metadata)

    prompt_resp = isolated_app.get("/api/library/inspector", params={"q": "prompt:mika", "scope": "all"})
    seed_resp = isolated_app.get("/api/library/inspector", params={"q": "seed:12345", "scope": "all"})

    assert prompt_resp.status_code == 200
    assert seed_resp.status_code == 200
    assert [row["name"] for row in prompt_resp.json()["rows"]] == ["mika_portrait.png"]
    assert [row["name"] for row in seed_resp.json()["rows"]] == ["mika_portrait.png"]


def test_library_inspector_detail_is_db_first(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    _index_gallery_images(temp_gallery_with_metadata)
    path = str((temp_gallery_with_metadata / "mika_album" / "mika_portrait.png").resolve())

    resp = isolated_app.get("/api/library/inspector/metadata", params={"path": path})

    assert resp.status_code == 200
    data = resp.json()
    assert "mika" in data["prompt"]
    assert "low quality" in data["negative_prompt"]
    assert data["seed"] == "12345"
    assert isinstance(data["loras"], list)
    assert isinstance(data["resources"], list)


def test_library_inspector_detail_rejects_unindexed_path(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    path = temp_gallery_with_metadata / "mika_album" / "mika_portrait.png"

    resp = isolated_app.get("/api/library/inspector/metadata", params={"path": str(path.resolve())})

    assert resp.status_code == 404
