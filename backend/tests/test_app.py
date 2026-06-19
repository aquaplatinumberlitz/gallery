"""
Purpose:
Verifies app-level routes, health checks, and broad fielded search semantics.

Guarantees:
* core routes stay registered and unsafe paths are rejected
* fielded, scoped, residual, and CJK search queries keep expected result semantics

Run when:
* changing FastAPI route registration, search parser integration, or metadata search behavior
* touching field aliases, scope filtering, or semantic search fixtures
"""

import json
import tempfile
import time
from contextlib import suppress
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import app
from backend.metadata_store import (
    _connect,
    _replace_image_resources_conn,
    index_file,
    initialize_database,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Module-level test data setup / teardown
# ---------------------------------------------------------------------------

_TEST_SEMANTIC_DIR = Path(tempfile.mkdtemp(prefix="test_fielded_semantic_"))
_TEST_SCOPE_DIR = Path(tempfile.mkdtemp(prefix="test_fielded_scope_"))
_TEST_INSERTED_PATHS: list[str] = []


def _create_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (64, 64), (40, 120, 200))
    img.save(path, format="PNG")


def _setup_test_data() -> None:
    """Insert fixture metadata rows into the shared DB for semantic tests."""
    initialize_database()

    now = time.time()
    semantic_root = _TEST_SEMANTIC_DIR.resolve()
    metadata_json_a = json.dumps({"some_key": "value", "workflow_field": "data"}, ensure_ascii=False, sort_keys=True)
    metadata_json_b = json.dumps({}, ensure_ascii=False, sort_keys=True)
    raw_text_a = "masterpiece, 1girl, rain, blue eyes watermark, blurry ponyDiffusionV6XL Euler a"

    files_data = [
        {
            "path": semantic_root / "rain_girl_001.png",
            "name": "rain_girl_001.png",
            "parent_path": semantic_root,
            "type": "photo",
            "prompt": "masterpiece, 1girl, rain, blue eyes",
            "negative_prompt": "watermark, blurry",
            "seed": "123",
            "steps": 30,
            "cfg_scale": 7.0,
            "sampler": "Euler a",
            "scheduler": "karras",
            "model": "ponyDiffusionV6XL",
            "model_hash": "abc123",
            "lora_text": "add_detail:0.8, lineart:0.4",
            "tool": "ComfyUI",
            "width": 1024,
            "height": 1536,
            "vae": "vae-ft-mse",
            "metadata_json": metadata_json_a,
            "raw_metadata_text": raw_text_a,
        },
        {
            "path": semantic_root / "snow_landscape_002.png",
            "name": "snow_landscape_002.png",
            "parent_path": semantic_root,
            "type": "photo",
            "prompt": "landscape, snow, mountain",
            "negative_prompt": "low quality",
            "seed": "999",
            "steps": 25,
            "cfg_scale": 7.5,
            "sampler": "DPM++ 2M",
            "scheduler": "normal",
            "model": "realisticVision",
            "model_hash": "def999",
            "lora_text": "",
            "tool": "A1111",
            "width": 512,
            "height": 768,
            "vae": "",
            "metadata_json": metadata_json_b,
            "raw_metadata_text": "",
        },
        {
            "path": semantic_root / "rain_wrong_seed.png",
            "name": "rain_wrong_seed.png",
            "parent_path": semantic_root,
            "type": "photo",
            "prompt": "sky, clouds landscape",
            "negative_prompt": "",
            "seed": "999",
            "steps": 20,
            "cfg_scale": 7.0,
            "sampler": "Euler a",
            "scheduler": "normal",
            "model": "realisticVision",
            "model_hash": "def999",
            "lora_text": "",
            "tool": "A1111",
            "width": 512,
            "height": 512,
            "vae": "",
            "metadata_json": metadata_json_b,
            "raw_metadata_text": "",
        },
    ]

    for fd in files_data:
        path = fd["path"]
        _create_png(path)
        resolved = str(path.resolve())

        # file_index + file_index_fts (index_file opens its own connection)
        index_file(
            path=resolved,
            name=fd["name"],
            parent_path=str(fd["parent_path"].resolve()),
            type=fd["type"],
            mtime=now,
            size=1024,
            width=fd["width"],
            height=fd["height"],
        )

        # image_metadata — own connection
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO image_metadata (
                  path, name, mtime, size, width, height, format, mode, has_alpha,
                  prompt, negative_prompt, model, sampler, seed, steps, cfg_scale,
                  raw_metadata_text, metadata_json, updated_at, indexed_at,
                  tool, scheduler, model_hash, lora_text, vae
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  prompt=excluded.prompt, negative_prompt=excluded.negative_prompt,
                  model=excluded.model, sampler=excluded.sampler, seed=excluded.seed,
                  steps=excluded.steps, cfg_scale=excluded.cfg_scale,
                  raw_metadata_text=excluded.raw_metadata_text,
                  metadata_json=excluded.metadata_json,
                  tool=excluded.tool, scheduler=excluded.scheduler,
                  model_hash=excluded.model_hash, lora_text=excluded.lora_text,
                  vae=excluded.vae
                """,
                (
                    resolved,
                    fd["name"],
                    now,
                    1024,
                    fd["width"],
                    fd["height"],
                    "PNG",
                    "RGB",
                    0,
                    fd["prompt"],
                    fd["negative_prompt"],
                    fd["model"],
                    fd["sampler"],
                    fd["seed"],
                    fd["steps"],
                    fd["cfg_scale"],
                    fd["raw_metadata_text"],
                    fd["metadata_json"],
                    now,
                    now,
                    fd["tool"],
                    fd["scheduler"],
                    fd["model_hash"],
                    fd["lora_text"],
                    fd["vae"],
                ),
            )
            _replace_image_resources_conn(conn, resolved, fd["metadata_json"], fd["lora_text"], now)
        _TEST_INSERTED_PATHS.append(resolved)

    # scope test data
    scope_root = _TEST_SCOPE_DIR.resolve()
    scope_files = [
        (scope_root / "current" / "rain_current.png", "rain_current.png", scope_root / "current"),
        (scope_root / "other" / "rain_other.png", "rain_other.png", scope_root / "other"),
    ]
    for fpath, fname, parent in scope_files:
        _create_png(fpath)
        resolved = str(fpath.resolve())
        index_file(
            path=resolved,
            name=fname,
            parent_path=str(parent.resolve()),
            type="photo",
            mtime=now,
            size=1024,
            width=64,
            height=64,
        )
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO image_metadata (
                  path, name, mtime, size, width, height, format, mode, has_alpha,
                  prompt, negative_prompt, model, sampler, seed, raw_metadata_text,
                  metadata_json, updated_at, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                  prompt=excluded.prompt, raw_metadata_text=excluded.raw_metadata_text
                """,
                (resolved, fname, now, 1024, 64, 64, "PNG", "RGB", 0, "rain", "", "", "", "", "", "", now, now),
            )
        _TEST_INSERTED_PATHS.append(resolved)


def _teardown_test_data() -> None:
    """Remove test data from DB and filesystem."""
    with _connect() as conn:
        for p in _TEST_INSERTED_PATHS:
            conn.execute("DELETE FROM file_index_fts WHERE path = ?", (p,))
            conn.execute("DELETE FROM file_index WHERE path = ?", (p,))
            conn.execute("DELETE FROM image_metadata WHERE path = ?", (p,))
    for p in _TEST_INSERTED_PATHS:
        with suppress(OSError):
            Path(p).unlink(missing_ok=True)
    _TEST_INSERTED_PATHS.clear()
    # Clean up dirs
    for d in [_TEST_SEMANTIC_DIR, _TEST_SCOPE_DIR / "current", _TEST_SCOPE_DIR / "other", _TEST_SCOPE_DIR]:
        with suppress(OSError):
            Path(d).rmdir()


def setup_module(module):
    _setup_test_data()


def teardown_module(module):
    _teardown_test_data()


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_unsafe_path_rejected():
    resp = client.get("/api/metadata?path=../../etc/passwd")
    # Returns 400 (invalid file) or 403 (path unsafe) depending on PATH_SAFETY_ROOT
    assert resp.status_code >= 400


def test_routes_registered():
    routes = [r.path for r in app.routes]
    assert "/api/scan" in routes
    assert "/api/metadata" in routes
    assert "/api/thumbnail" in routes
    assert "/api/preview" in routes
    assert "/api/health" in routes
    assert "/api/search" in routes
    assert "/api/folders" in routes
    assert "/api/image" in routes


def test_main_shim():
    from backend.main import app as main_app

    assert main_app is app


# ---------------------------------------------------------------------------
# Cors origins tests
# ---------------------------------------------------------------------------


def test_get_cors_origins_frontend_origin(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://example.com/")
    monkeypatch.delenv("FRONTEND_PORT", raising=False)

    from backend.app import _get_cors_origins

    origins = _get_cors_origins()
    assert "https://example.com" in origins


def test_get_cors_origins_frontend_port(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    monkeypatch.setenv("FRONTEND_PORT", "4180")

    from backend.app import _get_cors_origins

    origins = _get_cors_origins()
    assert "http://localhost:4180" in origins
    assert "http://127.0.0.1:4180" in origins


def test_get_cors_origins_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    monkeypatch.delenv("FRONTEND_PORT", raising=False)

    from backend.app import _get_cors_origins

    origins = _get_cors_origins()
    assert "http://localhost:5173" in origins


# ---------------------------------------------------------------------------
# Startup hook
# ---------------------------------------------------------------------------


def test_startup_hook_calls_refresh_and_watcher(monkeypatch: pytest.MonkeyPatch):
    import asyncio
    import importlib

    import backend.derivative_scheduler as derivative_scheduler_mod
    import backend.refresh as refresh_mod
    import backend.watcher as watcher_mod

    scheduler_called = []
    refresh_called = []
    watcher_called = []

    monkeypatch.setattr(derivative_scheduler_mod.scheduler, "start", lambda: scheduler_called.append(1))
    monkeypatch.setattr(refresh_mod, "start_refresh", lambda: refresh_called.append(1))
    monkeypatch.setattr(watcher_mod, "start_watcher", lambda: watcher_called.append(1))

    import backend.app as app_module

    importlib.reload(app_module)
    app = app_module.app

    handlers = app.router.on_startup
    assert len(handlers) >= 1

    async def run_all():
        for handler in handlers:
            await handler()

    asyncio.run(run_all())

    assert len(scheduler_called) == 1
    assert len(refresh_called) == 1
    assert len(watcher_called) == 1


# ---------------------------------------------------------------------------
# Import / startup tests
# ---------------------------------------------------------------------------


def test_search_index_fielded_import():
    from backend.metadata_store import search_index_fielded
    from backend.search import router as search_router

    assert callable(search_index_fielded)
    assert search_router is not None


# ---------------------------------------------------------------------------
# /api/search integration tests for fielded query response shape
# ---------------------------------------------------------------------------

SEARCH_BASE = "/api/search"


def _search(q: str, scope: str = "all"):
    return client.get(SEARCH_BASE, params={"q": q, "scope": scope})


def test_search_plain_query_shape():
    """Plain query returns compatible Albums / Photos / Prompt sections."""
    resp = _search("cat")
    assert resp.status_code == 200
    data = resp.json()
    assert "query" in data
    assert "scope" in data
    assert "albums" in data
    assert "photos" in data
    assert "prompt" in data
    assert isinstance(data["albums"], list)
    assert isinstance(data["photos"], list)
    assert isinstance(data["prompt"], list)


def test_search_fielded_query_no_crash():
    """Fielded query does not 500 and returns valid shape."""
    resp = _search('prompt:"girl" seed:123')
    assert resp.status_code == 200
    data = resp.json()
    assert "albums" in data
    assert "photos" in data
    assert "prompt" in data


def test_search_fielded_model_or_hash_no_crash():
    """model_or_hash: does not 500."""
    resp = _search("model_or_hash:abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert "prompt" in data


def test_search_fielded_param_no_crash():
    """param: does not 500."""
    resp = _search('param:some_key:"value"')
    assert resp.status_code == 200


def test_search_fielded_advanced_no_crash():
    """advanced: does not 500."""
    resp = _search('advanced:workflow_field:"data"')
    assert resp.status_code == 200


def test_search_fielded_raw_no_crash():
    """raw: does not 500."""
    resp = _search('raw:"ComfyUI workflow"')
    assert resp.status_code == 200


def test_search_fielded_no_results():
    """Fielded query with no matches returns empty sections, no 500."""
    resp = _search('prompt:"definitely-no-match" seed:999999999')
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["prompt"]) == 0


def test_search_scope_all_respected():
    """scope=all should work for fielded queries."""
    resp = client.get(SEARCH_BASE, params={"q": "seed:42", "scope": "all"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "all"


def test_search_steps_comparison_no_crash():
    """steps:>=20 should not 500."""
    resp = _search("steps:>=20")
    assert resp.status_code == 200


def test_search_mixed_residual_and_fields_no_crash():
    """rain seed:123 (residual + field) should not 500."""
    resp = _search("rain seed:123")
    assert resp.status_code == 200


def test_search_size_field_no_crash():
    """size:WxH should not 500."""
    resp = _search("size:1024x768")
    assert resp.status_code == 200


def test_search_generic_fallback_forms_no_crash():
    """All generic fallback forms should not 500."""
    for q in [
        "param:some_key",
        "param:some_key:value",
        'advanced:wf:"test"',
        "advanced:wf:test",
        'raw:"text"',
        "raw:text",
    ]:
        resp = _search(q)
        assert resp.status_code == 200, f"FAILED: {q!r}"


def test_search_empty_query_returns_empty():
    """Empty query returns empty sections."""
    resp = client.get(SEARCH_BASE, params={"q": "", "scope": "all"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["albums"] == []
    assert data["photos"] == []
    assert data["prompt"] == []


# ---------------------------------------------------------------------------
# Semantic match / non-match API tests
# ---------------------------------------------------------------------------

SEMANTIC_ROOT = str(_TEST_SEMANTIC_DIR.resolve())


def _search_path(q: str, scope: str = "all", path: str | None = None):
    params = {"q": q, "scope": scope}
    if path is not None:
        params["path"] = path
    return client.get(SEARCH_BASE, params=params)


def _prompt_names(data: dict) -> list[str]:
    return [r["name"] for r in data.get("prompt", [])]


def _photo_names(data: dict) -> list[str]:
    return [r["name"] for r in data.get("photos", [])]


def test_fielded_prompt_girl_returns_image_a():
    """prompt:girl returns Image A (rain_girl_001.png)."""
    resp = _search("prompt:girl")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_prompt_comma_and_returns_image_a():
    """prompt:"girl, rain" returns Image A (AND semantics)."""
    resp = _search('prompt:"girl, rain"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_prompt_comma_and_snow_does_not_return_image_a():
    """prompt:"girl, snow" does NOT return Image A (girl doesn't match snow prompt)."""
    resp = _search('prompt:"girl, snow"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" not in names


def test_fielded_positive_rain_returns_image_a():
    """positive:rain (alias for prompt) returns Image A."""
    resp = _search("positive:rain")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_negative_watermark_returns_image_a():
    """negative:watermark returns Image A."""
    resp = _search("negative:watermark")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_negative_comma_and_returns_image_a():
    """negative:"watermark, blurry" returns Image A."""
    resp = _search('negative:"watermark, blurry"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_lora_add_detail_returns_image_a():
    """lora:add_detail returns Image A."""
    resp = _search("lora:add_detail")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_source_comfyui_returns_image_a():
    """source:ComfyUI (alias for tool) returns Image A."""
    resp = _search("source:ComfyUI")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_tool_comfyui_returns_image_a():
    """tool:ComfyUI returns Image A."""
    resp = _search("tool:ComfyUI")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_model_pony_returns_image_a():
    """model:pony returns Image A (contains match on ponyDiffusionV6XL)."""
    resp = _search("model:pony")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_model_hash_exact_returns_image_a():
    """model_hash:abc123 returns Image A."""
    resp = _search("model_hash:abc123")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_model_or_hash_abc123_returns_image_a():
    """model_or_hash:abc123 returns Image A via hash."""
    resp = _search("model_or_hash:abc123")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_model_or_hash_pony_returns_image_a():
    """model_or_hash:pony returns Image A via model contains."""
    resp = _search("model_or_hash:pony")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_size_returns_image_a():
    """size:1024x1536 returns Image A."""
    resp = _search("size:1024x1536")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_width_1024_returns_image_a():
    """width:1024 returns Image A."""
    resp = _search("width:1024")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_height_1536_returns_image_a():
    """height:1536 returns Image A."""
    resp = _search("height:1536")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_param_key_value_returns_image_a():
    """param:some_key:"value" returns Image A."""
    resp = _search('param:some_key:"value"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_advanced_key_value_returns_image_a():
    """advanced:workflow_field:"data" returns Image A."""
    resp = _search('advanced:workflow_field:"data"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" in names


def test_fielded_prompt_snow_seed_999_returns_image_b():
    """prompt:snow seed:999 returns Image B."""
    resp = _search("prompt:snow seed:999")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "snow_landscape_002.png" in names


def test_fielded_prompt_snow_seed_123_does_not_return_image_a():
    """prompt:snow seed:123 does NOT return Image A (snow only in B, seed 123 only in A)."""
    resp = _search("prompt:snow seed:123")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" not in names
    assert "snow_landscape_002.png" not in names


def test_fielded_negative_watermark_seed_999_no_match():
    """negative:watermark seed:999 -> no Image A (seed mismatch)."""
    resp = _search("negative:watermark seed:999")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" not in names


def test_fielded_lora_missing_returns_none():
    """lora:missing_lora returns no results."""
    resp = _search("lora:missing_lora")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" not in names


def test_fielded_model_hash_missing_returns_none():
    """model_hash:missing_hash returns no results."""
    resp = _search("model_hash:missing_hash")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "rain_girl_001.png" not in names


def test_fielded_model_missing_returns_none():
    """model:missing_model returns no results."""
    resp = _search("model:missing_model")
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert len(names) == 0


# ---------------------------------------------------------------------------
# CJK fielded search tests
# ---------------------------------------------------------------------------


def _insert_cjk_fixture():
    """Insert a CJK-specific metadata row if not already present."""
    cjk_dir = Path(tempfile.mkdtemp(prefix="test_fielded_cjk_"))
    cjk_path = cjk_dir / "猫_雨.png"
    cjk_resolved = str(cjk_path.resolve())
    if cjk_resolved in _TEST_INSERTED_PATHS:
        return cjk_resolved

    initialize_database()
    _create_png(cjk_path)
    now = time.time()

    with _connect() as conn:
        index_file(
            path=cjk_resolved,
            name="猫_雨.png",
            parent_path=str(cjk_dir.resolve()),
            type="photo",
            mtime=now,
            size=1024,
            width=64,
            height=64,
        )
        conn.execute(
            """
            INSERT INTO image_metadata (
              path, name, mtime, size, width, height, format, mode, has_alpha,
              prompt, negative_prompt, model, sampler, seed, raw_metadata_text,
              metadata_json, updated_at, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              prompt=excluded.prompt, negative_prompt=excluded.negative_prompt
            """,
            (
                cjk_resolved,
                "猫_雨.png",
                now,
                1024,
                64,
                64,
                "PNG",
                "RGB",
                0,
                "masterpiece, 女の子, 雨, blue eyes",
                "文字, watermark",
                "",
                "",
                "",
                "",
                "",
                now,
                now,
            ),
        )
    _TEST_INSERTED_PATHS.append(cjk_resolved)
    return cjk_resolved


def test_cjk_prompt_girl_returns_image():
    """prompt:"女の子" returns the CJK test image (contains match)."""
    _insert_cjk_fixture()
    resp = _search('prompt:"女の子"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "猫_雨.png" in names


def test_cjk_prompt_rain_returns_image():
    """prompt:"雨" returns the CJK test image."""
    _insert_cjk_fixture()
    resp = _search('prompt:"雨"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "猫_雨.png" in names


def test_cjk_negative_text_returns_image():
    """negative:"文字" returns the CJK test image."""
    _insert_cjk_fixture()
    resp = _search('negative:"文字"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "猫_雨.png" in names


def test_cjk_name_cat_returns_image():
    """name:"猫" returns the CJK test image."""
    _insert_cjk_fixture()
    resp = _search('name:"猫"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "猫_雨.png" in names


def test_cjk_snow_does_not_return_image():
    """prompt:"雪" does NOT return the CJK test image (snow not in fixture)."""
    _insert_cjk_fixture()
    resp = _search('prompt:"雪"')
    assert resp.status_code == 200
    names = _prompt_names(resp.json())
    assert "猫_雨.png" not in names


# ---------------------------------------------------------------------------
# scope=current test with real directory on disk
# ---------------------------------------------------------------------------


def test_scope_current_returns_only_current():
    """scope=current with path=<tmp/root/current> returns only current/ files."""
    scope_dir = _TEST_SCOPE_DIR.resolve()
    current_root = str(scope_dir / "current")

    # rain_current.png is in current/
    resp = client.get(SEARCH_BASE, params={"q": "rain", "scope": "current", "path": current_root})
    assert resp.status_code == 200
    data = resp.json()
    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    # Both photos and prompt should include the current file
    assert "rain_current.png" in photo_names or "rain_current.png" in prompt_names, (
        f"rain_current.png not found in photos={photo_names} or prompt={prompt_names}"
    )
    # rain_other.png should NOT appear
    assert "rain_other.png" not in photo_names, f"rain_other.png unexpectedly in photos={photo_names}"


def test_scope_current_fielded_returns_only_current():
    """scope=current with path=<tmp/root/current> and fielded query returns only current/ files."""
    scope_dir = _TEST_SCOPE_DIR.resolve()
    current_root = str(scope_dir / "current")

    # name:rain matches both files; scope=current should filter to current/ only
    resp = client.get(SEARCH_BASE, params={"q": "name:rain", "scope": "current", "path": current_root})
    assert resp.status_code == 200
    data = resp.json()
    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    all_names = photo_names + prompt_names
    assert "rain_current.png" in all_names
    assert "rain_other.png" not in all_names


def test_scope_all_returns_both():
    """scope=all with path=<tmp/root/current> returns files from both dirs."""
    scope_dir = _TEST_SCOPE_DIR.resolve()
    current_root = str(scope_dir / "current")

    resp = client.get(SEARCH_BASE, params={"q": "rain", "scope": "all", "path": current_root})
    assert resp.status_code == 200
    data = resp.json()
    prompt_names = _prompt_names(data)
    photo_names = _photo_names(data)
    all_names = prompt_names + photo_names
    assert "rain_current.png" in all_names
    assert "rain_other.png" in all_names


# ---------------------------------------------------------------------------
# Phase 2B: Semantic regression — residual + field intersection
# ---------------------------------------------------------------------------


def test_fielded_residual_seed_123_does_not_leak_wrong_seed_photos():
    """rain seed:123 must NOT return rain_wrong_seed.png (seed=999) in photos."""
    resp = _search("rain seed:123")
    assert resp.status_code == 200
    data = resp.json()
    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    # rain_good_seed.png (rain_girl_001.png) has seed=123 → should appear
    assert "rain_girl_001.png" in photo_names or "rain_girl_001.png" in prompt_names
    # rain_wrong_seed.png has seed=999 → must NOT appear in any image section
    assert "rain_wrong_seed.png" not in photo_names, (
        f"rain_wrong_seed.png leaked into photos despite seed=123 filter: {photo_names}"
    )
    assert "rain_wrong_seed.png" not in prompt_names, (
        f"rain_wrong_seed.png leaked into prompt despite seed=123 filter: {prompt_names}"
    )


def test_fielded_residual_seed_999_returns_wrong_seed():
    """rain seed:999 must return rain_wrong_seed.png (seed=999) but NOT rain_girl_001 (seed=123)."""
    resp = _search("rain seed:999")
    assert resp.status_code == 200
    data = resp.json()
    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    # rain_wrong_seed.png matches filename 'rain' AND seed=999
    assert "rain_wrong_seed.png" in photo_names or "rain_wrong_seed.png" in prompt_names
    # rain_girl_001.png has seed=123 → must NOT appear
    assert "rain_girl_001.png" not in photo_names
    assert "rain_girl_001.png" not in prompt_names


def test_fielded_residual_model_pony_filters_photos():
    """rain model:pony must NOT return rain_wrong_seed.png (model=realisticVision) in photos."""
    resp = _search("rain model:pony")
    assert resp.status_code == 200
    data = resp.json()
    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    # rain_girl_001.png matches filename 'rain' AND model contains 'pony'
    assert "rain_girl_001.png" in photo_names or "rain_girl_001.png" in prompt_names
    # rain_wrong_seed.png has model=realisticVision → must NOT appear
    assert "rain_wrong_seed.png" not in photo_names, (
        f"rain_wrong_seed.png leaked into photos despite model:pony filter: {photo_names}"
    )
    assert "rain_wrong_seed.png" not in prompt_names


def test_fielded_only_seed_still_works():
    """seed:123 (no residual) must return rain_girl_001.png in prompt section."""
    resp = _search("seed:123")
    assert resp.status_code == 200
    data = resp.json()
    prompt_names = _prompt_names(data)
    assert "rain_girl_001.png" in prompt_names
    # Fields-only query should have no photos (no filename text to match)
    assert len(data["photos"]) == 0


def test_scope_current_fielded_residual_does_not_leak_other_folder():
    """scope=current + fielded query with residual must not leak other/ files."""
    scope_dir = _TEST_SCOPE_DIR.resolve()
    current_root = str(scope_dir / "current")

    resp = client.get(
        SEARCH_BASE,
        params={
            "q": "rain name:rain",
            "scope": "current",
            "path": current_root,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    all_names = photo_names + prompt_names
    assert "rain_current.png" in all_names
    assert "rain_other.png" not in all_names, f"rain_other.png leaked despite scope=current: {all_names}"


def _album_names(data: dict) -> list[str]:
    return [r["name"] for r in data.get("albums", [])]


def test_fielded_albums_are_folder_suggestions_not_field_filtered():
    """Albums are folder suggestions and intentionally not field-filtered.

    For a query like "rain seed:123":
    - Photos / Prompt sections exclude photos whose seed != 123.
    - Albums section may still return a folder whose name matches "rain"
      even though not all images inside satisfy seed:123.
    """
    album_dir = Path(tempfile.mkdtemp(prefix="test_fielded_album_"))
    album_dir_path = str(album_dir.resolve())
    album_name = "rain_folder"

    initialize_database()
    index_file(
        path=album_dir_path,
        name=album_name,
        parent_path=str(album_dir.parent.resolve()),
        type="folder",
        mtime=time.time(),
        size=0,
        width=0,
        height=0,
    )
    _TEST_INSERTED_PATHS.append(album_dir_path)

    resp = _search("rain seed:123")
    assert resp.status_code == 200
    data = resp.json()

    photo_names = _photo_names(data)
    prompt_names = _prompt_names(data)
    album_names = _album_names(data)

    # Photos/Prompt are field-filtered: wrong-seed images excluded
    assert "rain_girl_001.png" in photo_names or "rain_girl_001.png" in prompt_names, (
        "rain_girl_001.png (seed=123) should appear in photos or prompt"
    )
    assert "rain_wrong_seed.png" not in photo_names, (
        f"rain_wrong_seed.png leaked into photos despite seed=123 filter: {photo_names}"
    )
    assert "rain_wrong_seed.png" not in prompt_names, (
        f"rain_wrong_seed.png leaked into prompt despite seed=123 filter: {prompt_names}"
    )

    # Albums are folder suggestions based on residual text only — not
    # field-filtered.  The rain_folder matches "rain" in name and should
    # appear even though its contents are not guaranteed to satisfy seed:123.
    assert album_name in album_names, (
        f"Album '{album_name}' should appear as a folder suggestion "
        f"even though not field-filtered; got albums={album_names}"
    )
