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
    assert resp.status_code == 403


def test_routes_registered():
    routes = [r.path for r in app.routes]
    assert "/api/scan" in routes
    assert "/api/metadata" in routes
    assert "/api/thumbnail" in routes
    assert "/api/health" in routes
    assert "/api/search" in routes
    assert "/api/folders" in routes
    assert "/api/image" in routes


def test_main_shim():
    from backend.main import app as main_app
    assert main_app is app
