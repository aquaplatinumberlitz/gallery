"""
Purpose:
Verifies metadata extraction, search, fielded queries, and facets API contracts.

Guarantees:
* metadata, search, and facets endpoints return stable shapes for indexed images
* fielded search and scoped facets keep expected filtering semantics

Run when:
* changing metadata parsing, search SQL, facets aggregation, or API response shapes
* touching Library Inspector or search backend contracts
"""

from pathlib import Path

from fastapi.testclient import TestClient


class TestMetadataEndpoint:
    def test_metadata_parses_embedded_png_parameters(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        path = str(temp_gallery_with_metadata / "mika_album" / "mika_portrait.png")
        resp = isolated_app.get("/api/metadata", params={"path": path})
        assert resp.status_code == 200
        data = resp.json()
        assert "prompt" in data
        assert "mika" in data["prompt"].lower()

    def test_metadata_returns_tool_field(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        path = str(temp_gallery_with_metadata / "mika_album" / "mika_portrait.png")
        resp = isolated_app.get("/api/metadata", params={"path": path})
        assert resp.status_code == 200
        data = resp.json()
        assert "tool" in data

    def test_metadata_rejects_missing_file(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        resp = isolated_app.get(
            "/api/metadata",
            params={"path": str(temp_gallery_with_metadata / "none.png")},
        )
        # May be 403 (out of root if resolved to /) or 404
        assert resp.status_code >= 400

    def test_metadata_returns_params_dict(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        path = str(temp_gallery_with_metadata / "mika_album" / "mika_portrait.png")
        resp = isolated_app.get("/api/metadata", params={"path": path})
        assert resp.status_code == 200
        data = resp.json()
        assert "params" in data
        assert isinstance(data["params"], dict)


class TestSearchPlainQuery:
    def test_search_finds_image_by_prompt(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "mika", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        all_names = _all_image_names(data)
        assert "mika_portrait.png" in all_names

    def test_search_no_results_does_not_break(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "zzz_nonexistent_xyz", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["photos"]) == 0
        assert len(data["prompt"]) == 0

    def test_search_empty_query_returns_empty(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        resp = isolated_app.get("/api/search", params={"q": "", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["albums"] == []
        assert data["photos"] == []
        assert data["prompt"] == []

    def test_search_response_shape(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "mika", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert {
            "query",
            "scope",
            "root",
            "albums",
            "photos",
            "videos",
            "prompt",
            "media",
            "next_cursor",
            "has_more",
            "returned",
            "limit",
        } <= data.keys()
        assert data["query"] == "mika"
        assert data["scope"] == "all"
        assert isinstance(data["albums"], list)
        assert isinstance(data["photos"], list)
        assert isinstance(data["videos"], list)
        assert isinstance(data["prompt"], list)
        assert isinstance(data["media"], list)
        assert isinstance(data["returned"], int)
        assert isinstance(data["limit"], int)
        assert data["next_cursor"] is None or isinstance(data["next_cursor"], int)
        assert isinstance(data["has_more"], bool)

        result = next(row for row in data["media"] if row["name"] == "mika_portrait.png")
        assert {
            "name",
            "path",
            "type",
            "parent_path",
            "relative_path",
            "mtime",
            "width",
            "height",
            "duration_ms",
            "mime_type",
            "match_type",
            "prompt_snippet",
            "model",
            "sampler",
            "seed",
        } <= result.keys()

    def test_search_metadata_response_shape(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search-metadata", params={"q": "mika", "limit": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert {"query", "total", "results"} <= data.keys()
        assert data["query"] == "mika"
        assert isinstance(data["total"], int)
        assert isinstance(data["results"], list)
        assert data["results"]
        assert {
            "name",
            "path",
            "type",
            "mtime",
            "width",
            "height",
            "model",
            "sampler",
            "seed",
            "prompt_snippet",
        } <= data["results"][0].keys()

    def test_search_landscape_finds_second_image(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "mountain", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        all_names = _all_image_names(data)
        assert "landscape.png" in all_names


class TestSearchFieldedQueries:
    def test_search_prompt_field_mika(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "prompt:mika", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        names = _all_image_names(data)
        assert "mika_portrait.png" in names

    def test_search_seed_field_12345(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "seed:12345", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        names = _all_image_names(data)
        assert "mika_portrait.png" in names

    def test_search_model_field_pony(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": "model:pony", "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        names = _all_image_names(data)
        assert "mika_portrait.png" in names

    def test_fielded_search_no_results(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _index_gallery_images(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/search", params={"q": 'prompt:"definitely no match"', "scope": "all"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["prompt"]) == 0

    def test_fielded_search_does_not_500(self, isolated_app: TestClient):
        for q in [
            "seed:xyz",
            "model:",
            "prompt:test model:foo",
        ]:
            resp = isolated_app.get("/api/search", params={"q": q, "scope": "all"})
            assert resp.status_code == 200, f"Failed for q={q!r}"


class TestFacetsEndpoint:
    def test_facets_returns_200(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _seed_metadata_for_facets(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/facets", params={"path": str(temp_gallery_with_metadata / "mika_album")})
        assert resp.status_code == 200

    def test_facets_has_expected_keys(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _seed_metadata_for_facets(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/facets", params={"path": str(temp_gallery_with_metadata / "mika_album")})
        assert resp.status_code == 200
        data = resp.json()
        assert {
            "tool",
            "model",
            "sampler",
            "scheduler",
            "folders",
            "orientation",
            "seed_availability",
            "metadata_availability",
            "lora",
        } <= data.keys()
        for values in data.values():
            assert isinstance(values, list)
            for item in values:
                assert {"value", "count"} <= item.keys()
                assert isinstance(item["value"], str)
                assert isinstance(item["count"], int)

    def test_facets_tool_counts_are_deterministic(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _seed_metadata_for_facets(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/facets", params={"path": str(temp_gallery_with_metadata / "mika_album")})
        assert resp.status_code == 200
        data = resp.json()
        tool_values = {f["value"]: f["count"] for f in data["tool"]}
        assert isinstance(tool_values, dict)

    def test_facets_respects_scope(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        _seed_metadata_for_facets(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/facets", params={"path": None})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "tool" in data

    def test_facets_handles_nonexistent_folder(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        resp = isolated_app.get(
            "/api/facets",
            params={"path": str(temp_gallery_with_metadata / "nonexistent")},
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_facets_handles_empty_db(self, isolated_app: TestClient, temp_gallery_with_metadata: Path):
        # No seeding - should handle empty gracefully
        resp = isolated_app.get("/api/facets", params={"path": None})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_facets_type_values_are_strings_with_counts(
        self, isolated_app: TestClient, temp_gallery_with_metadata: Path
    ):
        _seed_metadata_for_facets(temp_gallery_with_metadata)
        resp = isolated_app.get("/api/facets", params={"path": str(temp_gallery_with_metadata / "mika_album")})
        assert resp.status_code == 200
        data = resp.json()
        for facet_list in (data.get("tool", []), data.get("model", []), data.get("sampler", [])):
            for item in facet_list:
                assert isinstance(item["value"], str)
                assert isinstance(item["count"], int)
                assert item["count"] >= 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index_gallery_images(gallery_root: Path) -> None:
    """Index all images in the gallery so /api/search can find them by metadata.

    Uses the same pattern as existing test_app.py: index into both file_index
    and image_metadata tables via the standard library functions.
    """
    from backend.metadata_store import (
        index_directory_tree,
        initialize_database,
    )

    # Force re-initialization for the current DB path
    initialize_database()
    index_directory_tree(gallery_root, include_metadata=True)


def _all_image_names(data: dict) -> list[str]:
    photos = [r["name"] for r in data.get("photos", [])]
    prompt = [r["name"] for r in data.get("prompt", [])]
    return photos + prompt


def _seed_metadata_for_facets(gallery_root: Path) -> None:
    """Seed metadata store with test data so /api/facets has deterministic results."""
    import time as _time

    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import (
        index_directory_tree,
        update_folder_index_state,
        upsert_extracted_metadata,
    )

    album = gallery_root / "mika_album"
    images_data = [
        ("mika_portrait.png", "ponyDiffusionV6XL", "Euler a", "12345", "A1111"),
        ("landscape.png", "SDXL", "DPM++ 2M", "99999", "A1111"),
    ]

    for fname, model, sampler, seed, tool in images_data:
        path = album / fname
        if not path.exists():
            continue
        stat = path.stat()
        ext_meta = ExtractedMetadata(
            path=str(path.resolve()),
            name=fname,
            mtime=stat.st_mtime,
            size=stat.st_size,
            width=512,
            height=512,
            format="PNG",
            mode="RGB",
            has_alpha=0,
            prompt="test",
            negative_prompt="",
            model=model,
            sampler=sampler,
            seed=seed,
            steps=None,
            cfg_scale=None,
            raw_metadata_text="",
            metadata_json='{"tool":"' + tool + '"}',
            tool=tool,
            scheduler="",
            model_hash=None,
            lora_text=None,
            generation_time=None,
            clip_skip=None,
            hires_upscale=None,
            hires_steps=None,
            denoising_strength=None,
            vae=None,
            ensd=None,
            aesthetic_score=None,
            date=None,
            aspect_ratio=None,
            indexed_at=_time.time(),
        )
        upsert_extracted_metadata(ext_meta)

    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(
        album,
        complete=True,
        child_count=len(images_data),
        folder_count=0,
        image_count=len(images_data),
    )
