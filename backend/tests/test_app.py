from backend.app import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


def test_unsafe_path_rejected():
    resp = client.get("/api/metadata?path=../../etc/passwd")
    # Returns 400 (invalid file) or 403 (path unsafe) depending on GALLERY_ROOT
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
