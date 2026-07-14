"""
Purpose:
Verifies Library Inspector backend scope, search, detail, exclusion, and fallback contracts.

Guarantees:
* inspector queries use metadata/search semantics without changing normal search behavior
* detail responses are DB-first and reject unindexed paths safely

Run when:
* changing library inspector endpoints, metadata detail lookup, or app-build exclusion policy
* touching LibraryInspector.vue contracts or inspector query keys
"""

import base64
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from .test_api_integration_metadata_search_facets import _index_gallery_images


def _seed_mika_lora_resource_metadata(gallery_root: Path) -> None:
    import time as _time

    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import upsert_extracted_metadata

    path = gallery_root / "mika_album" / "mika_portrait.png"
    stat = path.stat()
    metadata = {
        "tool": "A1111",
        "loras": [
            {
                "name": "detail_lora",
                "resource_hash": "lora-resource-abc",
                "weight": 0.8,
            }
        ],
        "resources": [
            {
                "name": "detail-resource",
                "resource_hash": "resource-hash-xyz",
                "weight": 0.5,
            }
        ],
    }
    upsert_extracted_metadata(
        ExtractedMetadata(
            path=str(path.resolve()),
            name=path.name,
            mtime=stat.st_mtime,
            size=stat.st_size,
            width=1024,
            height=1536,
            format="PNG",
            mode="RGB",
            has_alpha=0,
            prompt="masterpiece, 1girl, mika, blue eyes, rain",
            negative_prompt="low quality, blurry",
            model="ponyDiffusionV6XL",
            sampler="Euler a",
            seed="12345",
            steps=30,
            cfg_scale=7.0,
            raw_metadata_text="detail_lora lora-resource-abc resource-hash-xyz",
            metadata_json=json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            mtime_ns=stat.st_mtime_ns,
            tool="A1111",
            scheduler="karras",
            model_hash="checkpoint-abc",
            lora_text="detail_lora:0.8, lora-resource-abc, resource-hash-xyz",
            generation_time=None,
            clip_skip=None,
            hires_upscale=None,
            hires_steps=None,
            denoising_strength=None,
            vae=None,
            ensd=None,
            aesthetic_score=None,
            date="2026-01-02",
            aspect_ratio="2:3",
            indexed_at=_time.time(),
        )
    )


def test_library_inspector_scoped_current_returns_only_path_descendants(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    from backend.metadata_store import index_directory_tree, register_library

    from .conftest import create_test_png_with_metadata

    album_a = isolated_gallery_root / "album_a" / "sky.png"
    album_b = isolated_gallery_root / "album_b" / "ocean.png"
    create_test_png_with_metadata(album_a, prompt="blue sky", seed="1")
    create_test_png_with_metadata(album_b, prompt="deep ocean", seed="2")
    register_library(isolated_gallery_root)

    collected: list[Path] = []
    index_directory_tree(isolated_gallery_root, include_metadata=True, collected_image_paths=collected)
    scoped = isolated_app.get(
        "/api/library/inspector",
        params={"q": "", "scope": "current", "path": str(isolated_gallery_root / "album_a"), "limit": 200},
    )
    assert scoped.status_code == 200
    scoped_data = scoped.json()
    assert scoped_data["scope"] == "current"
    assert isinstance(scoped_data["generated_at"], (int, float))
    assert scoped_data["total_indexed"] == 1
    assert len(scoped_data["rows"]) == 1
    assert scoped_data["rows"][0]["name"] == "sky.png"

    default_scoped = isolated_app.get(
        "/api/library/inspector",
        params={"q": "", "path": str(isolated_gallery_root / "album_a"), "limit": 200},
    )
    assert default_scoped.status_code == 200
    default_scoped_data = default_scoped.json()
    assert default_scoped_data["scope"] == "current"
    assert default_scoped_data["total_indexed"] == 1
    assert default_scoped_data["rows"][0]["name"] == "sky.png"

    scoped_b = isolated_app.get(
        "/api/library/inspector",
        params={"q": "", "scope": "current", "path": str(isolated_gallery_root / "album_b"), "limit": 200},
    )
    assert scoped_b.status_code == 200
    scoped_b_data = scoped_b.json()
    assert scoped_b_data["total_indexed"] == 1
    assert scoped_b_data["rows"][0]["name"] == "ocean.png"

    all_resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "limit": 200})
    assert all_resp.status_code == 200
    assert all_resp.json()["total_indexed"] == 2


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
    assert data["total_indexed"] == 2
    assert data["returned"] >= 2
    assert data["rows"][0]["path"]
    assert "prompt" not in data["rows"][0]
    assert "negative_prompt" not in data["rows"][0]
    assert "raw_metadata" not in data["rows"][0]
    for key in (
        "prompt_preview",
        "has_prompt",
        "has_negative",
        "has_lora",
        "lora_count",
        "lora_preview",
        "metadata_detail_available",
    ):
        assert key in data["rows"][0]


def test_library_inspector_applies_model_and_prompt_filters_before_cursor_pagination(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    from backend.metadata_store import _DB_LOCK, _connect, index_directory_tree, register_library

    from .conftest import create_test_png_with_metadata

    album = isolated_gallery_root / "filtered_album"
    fixtures = [
        ("pony-prompt.png", "PonyXL", "portrait"),
        ("pony-empty.png", "PonyXL", ""),
        ("sdxl-prompt.png", "SDXL", "landscape"),
    ]
    for name, model, prompt in fixtures:
        create_test_png_with_metadata(album / name, model=model, prompt=prompt, seed=name)

    register_library(isolated_gallery_root)
    collected: list[Path] = []
    index_directory_tree(isolated_gallery_root, include_metadata=True, collected_image_paths=collected)
    with _DB_LOCK, _connect() as conn:
        conn.execute(
            "UPDATE image_metadata SET prompt = '' WHERE path = ?", (str((album / "pony-empty.png").resolve()),)
        )
        conn.commit()

    has_prompt = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "all", "limit": 1, "sort": "name_asc", "model": "PonyXL", "prompt": "has_prompt"},
    )
    assert has_prompt.status_code == 200
    assert [row["name"] for row in has_prompt.json()["rows"]] == ["pony-prompt.png"]
    assert has_prompt.json()["has_more"] is False

    no_prompt = isolated_app.get(
        "/api/library/inspector",
        params={"scope": "all", "limit": 1, "sort": "name_asc", "model": "PonyXL", "prompt": "no_prompt"},
    )
    assert no_prompt.status_code == 200
    assert [row["name"] for row in no_prompt.json()["rows"]] == ["pony-empty.png"]
    assert no_prompt.json()["has_more"] is False


def test_library_inspector_indexes_lora_from_json_when_lora_text_empty(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    import time as _time

    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import index_directory_tree, register_library, upsert_extracted_metadata

    from .conftest import create_test_png_with_metadata

    path = isolated_gallery_root / "json_lora" / "json-lora.png"
    create_test_png_with_metadata(path, prompt="json lora prompt", seed="10")
    stat = path.stat()
    register_library(isolated_gallery_root)
    index_directory_tree(isolated_gallery_root, include_metadata=False)
    metadata = {
        "loras": [
            {
                "name": "json_only_lora",
                "resource_hash": "json-lora-hash",
                "weight": 0.7,
            }
        ]
    }
    upsert_extracted_metadata(
        ExtractedMetadata(
            path=str(path.resolve()),
            name=path.name,
            mtime=stat.st_mtime,
            size=stat.st_size,
            width=512,
            height=512,
            format="PNG",
            mode="RGB",
            has_alpha=0,
            prompt="json lora prompt",
            negative_prompt="",
            model="model",
            sampler="sampler",
            seed="10",
            steps=None,
            cfg_scale=None,
            raw_metadata_text="",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            mtime_ns=stat.st_mtime_ns,
            tool="test",
            scheduler="",
            model_hash="",
            lora_text="",
            generation_time=None,
            clip_skip=None,
            hires_upscale=None,
            hires_steps=None,
            denoising_strength=None,
            vae=None,
            ensd=None,
            aesthetic_score=None,
            date="",
            aspect_ratio="",
            indexed_at=_time.time(),
        )
    )
    resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "limit": 20})
    assert resp.status_code == 200
    row = next(item for item in resp.json()["rows"] if item["name"] == "json-lora.png")
    assert row["has_lora"] is True
    assert row["lora_count"] == 1
    assert "json_only_lora" in row["lora_preview"]

    search_resp = isolated_app.get(
        "/api/library/inspector", params={"q": "lora:json_only_lora", "scope": "all", "limit": 20}
    )
    assert search_resp.status_code == 200
    assert [item["name"] for item in search_resp.json()["rows"]] == ["json-lora.png"]


def test_lora_resource_rows_dedupe_params_lora_and_lora_text():
    from backend.metadata_store._resources import _resource_rows_from_metadata

    metadata = {
        "params": {
            "Lora": [
                "ba_character/ba_shintanikai_illustriousXL:0.7",
                "style/Aiiko - Blue Archive Style - Anime:0.7",
                "style/ba_background:1.0",
            ]
        }
    }
    rows = _resource_rows_from_metadata(
        json.dumps(metadata, ensure_ascii=False),
        (
            "ba_character/ba_shintanikai_illustriousXL:0.7, "
            "style/Aiiko - Blue Archive Style - Anime:0.7, "
            "style/ba_background:1.0"
        ),
        0,
    )

    assert [(row["name"], row["weight"]) for row in rows] == [
        ("ba_character/ba_shintanikai_illustriousXL", "0.7"),
        ("style/Aiiko - Blue Archive Style - Anime", "0.7"),
        ("style/ba_background", "1.0"),
    ]


def test_library_inspector_accepts_gallery_sort_contract(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    from backend.metadata_store import index_directory_tree, register_library

    from .conftest import create_test_png_with_metadata

    album = isolated_gallery_root / "sorted_album"
    album.mkdir()
    fixtures = [
        ("b10.png", 1_700_000_010),
        ("a2.png", 1_700_000_020),
        ("a10.png", 1_700_000_030),
        ("c1.png", 1_700_000_040),
    ]
    for name, mtime in fixtures:
        path = album / name
        create_test_png_with_metadata(path, prompt=name, seed=str(mtime))
        os.utime(path, (mtime, mtime))

    register_library(isolated_gallery_root)
    collected: list[Path] = []
    index_directory_tree(isolated_gallery_root, include_metadata=True, collected_image_paths=collected)

    def sorted_names(sort: str) -> list[str]:
        resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "limit": 200, "sort": sort})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sort"] == sort
        return [row["name"] for row in data["rows"]]

    assert sorted_names("date_desc") == ["c1.png", "a10.png", "a2.png", "b10.png"]
    assert sorted_names("date_asc") == ["b10.png", "a2.png", "a10.png", "c1.png"]
    assert sorted_names("name_asc") == ["a2.png", "a10.png", "b10.png", "c1.png"]
    assert sorted_names("name_desc") == ["c1.png", "b10.png", "a10.png", "a2.png"]


def test_library_inspector_cursor_paginates_all_sort_options(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    from backend.metadata_store import index_directory_tree, register_library

    from .conftest import create_test_png_with_metadata

    album = isolated_gallery_root / "cursor_album"
    fixtures = [
        ("b10.png", 1_700_000_010),
        ("a2.png", 1_700_000_020),
        ("a10.png", 1_700_000_030),
        ("c1.png", 1_700_000_040),
        ("d1.png", 1_700_000_050),
    ]
    for name, mtime in fixtures:
        path = album / name
        create_test_png_with_metadata(path, prompt=f"cursor_prompt {name}", seed=str(mtime))
        os.utime(path, (mtime, mtime))

    register_library(isolated_gallery_root)
    collected: list[Path] = []
    index_directory_tree(isolated_gallery_root, include_metadata=True, collected_image_paths=collected)

    expected = {
        "date_desc": ["d1.png", "c1.png", "a10.png", "a2.png", "b10.png"],
        "date_asc": ["b10.png", "a2.png", "a10.png", "c1.png", "d1.png"],
        "name_asc": ["a2.png", "a10.png", "b10.png", "c1.png", "d1.png"],
        "name_desc": ["d1.png", "c1.png", "b10.png", "a10.png", "a2.png"],
    }

    for sort, expected_names in expected.items():
        cursor = None
        names: list[str] = []
        for page_index in range(3):
            params = {"q": "", "scope": "all", "limit": 2, "sort": sort}
            if cursor:
                params["cursor"] = cursor
            resp = isolated_app.get("/api/library/inspector", params=params)
            assert resp.status_code == 200
            data = resp.json()
            names.extend(row["name"] for row in data["rows"])
            if page_index < 2:
                assert data["has_more"] is True
                assert isinstance(data["next_cursor"], str)
            cursor = data["next_cursor"]
            if not cursor:
                break

        assert names == expected_names
        assert len(names) == len(set(names))

    cursor = None
    fielded_names: list[str] = []
    while True:
        params = {"q": "prompt:cursor_prompt", "scope": "all", "limit": 2, "sort": "name_asc"}
        if cursor:
            params["cursor"] = cursor
        resp = isolated_app.get("/api/library/inspector", params=params)
        assert resp.status_code == 200
        data = resp.json()
        fielded_names.extend(row["name"] for row in data["rows"])
        cursor = data["next_cursor"]
        if not cursor:
            assert data["has_more"] is False
            break

    assert fielded_names == expected["name_asc"]


def test_library_inspector_invalid_cursor_returns_bad_request(isolated_app: TestClient):
    resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "cursor": "not-a-valid-cursor"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == {
        "error": "bad_request",
        "message": "Invalid pagination cursor",
    }


def test_library_inspector_rejects_nonfinite_typed_and_overflow_cursors(isolated_app: TestClient):
    payloads = (
        {"mtime": True, "name": "a", "path": "/a"},
        {"mtime": float("inf"), "name": "a", "path": "/a"},
        {"mtime": 10**100, "name": "a", "path": "/a"},
        {"mtime": 1.0, "name": [], "path": {}},
    )
    for payload in payloads:
        cursor = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        response = isolated_app.get(
            "/api/library/inspector",
            params={"q": "", "scope": "all", "cursor": cursor},
        )
        assert response.status_code == 400


def test_library_inspector_missing_fts_returns_service_unavailable(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    from backend.metadata_store import _connect, index_directory_tree, register_library

    from .conftest import create_test_png_with_metadata

    path = isolated_gallery_root / "missing_fts.png"
    create_test_png_with_metadata(path, prompt="missing fts needle", seed="1")
    register_library(isolated_gallery_root)
    index_directory_tree(isolated_gallery_root, include_metadata=True)
    with _connect() as conn:
        conn.execute("DROP TABLE image_metadata_fts")

    response = isolated_app.get(
        "/api/library/inspector",
        params={"q": "needle", "scope": "all"},
    )

    assert response.status_code == 503


def test_library_inspector_excludes_app_build_assets_but_keeps_gallery_dist_folder(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
):
    from backend.metadata_store import _connect, index_directory_tree, register_library

    from .conftest import create_test_png_with_metadata

    app_dist_image = isolated_gallery_root / "frontend" / "dist" / "landpage" / "asset.png"
    app_public_image = isolated_gallery_root / "frontend" / "public" / "landpage" / "asset.png"
    node_modules_image = isolated_gallery_root / "node_modules" / "fixture.png"
    gallery_dist_image = isolated_gallery_root / "albums" / "dist" / "real-gallery-image.png"
    create_test_png_with_metadata(app_dist_image, prompt="app build asset", seed="1")
    create_test_png_with_metadata(app_public_image, prompt="app public asset", seed="4")
    create_test_png_with_metadata(node_modules_image, prompt="dependency asset", seed="2")
    create_test_png_with_metadata(gallery_dist_image, prompt="real gallery image", seed="3")

    register_library(isolated_gallery_root)
    collected: list[Path] = []
    index_directory_tree(isolated_gallery_root, include_metadata=True, collected_image_paths=collected)

    with _connect() as conn:
        image_metadata_paths = {row["path"] for row in conn.execute("SELECT path FROM image_metadata")}
        file_index_paths = {row["path"] for row in conn.execute("SELECT path FROM file_index WHERE type = 'image'")}

    assert str(app_dist_image.resolve()) not in image_metadata_paths
    assert str(app_dist_image.resolve()) not in file_index_paths
    assert str(app_public_image.resolve()) not in image_metadata_paths
    assert str(app_public_image.resolve()) not in file_index_paths
    assert str(node_modules_image.resolve()) not in image_metadata_paths
    assert str(gallery_dist_image.resolve()) in image_metadata_paths
    assert str(gallery_dist_image.resolve()) in file_index_paths

    resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "limit": 200})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_indexed"] == 1
    assert [row["name"] for row in data["rows"]] == ["real-gallery-image.png"]


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


def test_library_inspector_returns_422_for_invalid_field_values(isolated_app: TestClient) -> None:
    for query in (
        "steps:nan",
        "width:nan",
        "cfg:1e309",
        "steps:>nan",
        "steps:>999999999999999999999999",
        "size:999999999999999999999x1",
        f"size:{'9' * 5000}x1",
    ):
        response = isolated_app.get("/api/library/inspector", params={"q": query, "scope": "all"})
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "bad_request"


def test_library_inspector_reuses_negative_lora_resource_and_scope_fields(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    _index_gallery_images(temp_gallery_with_metadata)
    _seed_mika_lora_resource_metadata(temp_gallery_with_metadata)

    exact_queries = [
        "negative:blurry",
        "lora:detail_lora",
        "resource:detail_lora",
        "resource_hash:lora-resource-abc",
        "resource_hash:resource-hash-xyz",
        "date:2026-01-02",
    ]

    for query in exact_queries:
        resp = isolated_app.get("/api/library/inspector", params={"q": query, "scope": "all"})
        assert resp.status_code == 200
        assert [row["name"] for row in resp.json()["rows"]] == ["mika_portrait.png"]

    folder_resp = isolated_app.get("/api/library/inspector", params={"q": "folder:mika_album", "scope": "all"})
    assert folder_resp.status_code == 200
    assert "mika_portrait.png" in [row["name"] for row in folder_resp.json()["rows"]]


def test_library_inspector_resource_hash_does_not_match_model_hash(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    _index_gallery_images(temp_gallery_with_metadata)
    _seed_mika_lora_resource_metadata(temp_gallery_with_metadata)

    resp = isolated_app.get("/api/library/inspector", params={"q": "resource_hash:checkpoint-abc", "scope": "all"})

    assert resp.status_code == 200
    assert resp.json()["rows"] == []


def test_library_inspector_uses_file_index_dimension_fallback(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    from backend.metadata_store import _connect

    _index_gallery_images(temp_gallery_with_metadata)
    path = str((temp_gallery_with_metadata / "mika_album" / "mika_portrait.png").resolve())
    with _connect() as conn:
        conn.execute("UPDATE image_metadata SET width = NULL, height = NULL WHERE path = ?", (path,))
        conn.execute("UPDATE file_index SET width = 2048, height = 3072 WHERE path = ?", (path,))

    list_resp = isolated_app.get("/api/library/inspector", params={"q": "seed:12345", "scope": "all"})
    detail_resp = isolated_app.get("/api/library/inspector/metadata", params={"path": path})

    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200
    row = list_resp.json()["rows"][0]
    detail = detail_resp.json()
    assert row["width"] == 2048
    assert row["height"] == 3072
    assert detail["width"] == 2048
    assert detail["height"] == 3072


def test_library_inspector_overscans_when_limited_rows_are_stale(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
):
    from backend.metadata_store import _connect

    _index_gallery_images(temp_gallery_with_metadata)
    stale_path = str((temp_gallery_with_metadata / "mika_album" / "deleted.png").resolve())
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO file_index(path, name, parent_path, type, mtime, size, width, height, indexed_at)
            VALUES (?, 'deleted.png', ?, 'photo', 9999999999, 1, 1, 1, 9999999999)
            """,
            (stale_path, str((temp_gallery_with_metadata / "mika_album").resolve())),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO image_metadata(path, name, mtime, size, prompt, metadata_json, updated_at, indexed_at)
            VALUES (?, 'deleted.png', 9999999999, 1, 'stale prompt', '{}', 9999999999, 9999999999)
            """,
            (stale_path,),
        )

    resp = isolated_app.get("/api/library/inspector", params={"q": "", "scope": "all", "limit": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert data["returned"] == 1
    assert data["rows"][0]["name"] != "deleted.png"


def test_library_inspector_detail_is_db_first(
    isolated_app: TestClient,
    temp_gallery_with_metadata: Path,
    monkeypatch,
):
    _index_gallery_images(temp_gallery_with_metadata)
    path = str((temp_gallery_with_metadata / "mika_album" / "mika_portrait.png").resolve())

    def fail_extract(*args, **kwargs):
        raise AssertionError("detail endpoint must not parse original image files")

    monkeypatch.setattr("backend.metadata_store.extract_metadata", fail_extract)

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
