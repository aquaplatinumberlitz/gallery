"""
Purpose:
Verify the pure helpers of the offline launcher run_local.py: when the frontend must be rebuilt, port checks and
argument validation. The launcher itself (venv setup, building, starting uvicorn) is exercised manually.

Guarantees:
* needs_build is True when dist/index.html is missing, when a rebuild is forced, and when any build input is
  newer than the built index; it is False for an up-to-date build.
* port_is_free reports a bound loopback port as occupied.
* parse_args rejects ports outside 1-65535 and defaults to 4701.

Run when:
* changing run_local.py, its build-staleness rule, or its CLI options
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def run_local():
    spec = importlib.util.spec_from_file_location("run_local_under_test", ROOT / "run_local.py")
    assert spec and spec.loader
    sys.path.insert(0, str(ROOT))  # run_local imports start.py from the repo root
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    return module


def _make_frontend(tmp_path: Path) -> Path:
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "public").mkdir()
    (frontend / "dist").mkdir()
    (frontend / "index.html").write_text("<html></html>")
    (frontend / "package.json").write_text("{}")
    (frontend / "src" / "main.ts").write_text("export {}")
    return frontend


def _set_mtime(path: Path, value: float) -> None:
    os.utime(path, (value, value))


def test_needs_build_without_dist(run_local, tmp_path: Path):
    assert run_local.needs_build(_make_frontend(tmp_path)) is True


def test_needs_build_false_when_up_to_date(run_local, tmp_path: Path):
    frontend = _make_frontend(tmp_path)
    for path in (frontend / "index.html", frontend / "package.json", frontend / "src" / "main.ts"):
        _set_mtime(path, 1_000)
    (frontend / "dist" / "index.html").write_text("built")
    _set_mtime(frontend / "dist" / "index.html", 2_000)
    assert run_local.needs_build(frontend) is False
    assert run_local.needs_build(frontend, force=True) is True


def test_needs_build_when_a_source_is_newer(run_local, tmp_path: Path):
    frontend = _make_frontend(tmp_path)
    (frontend / "dist" / "index.html").write_text("built")
    _set_mtime(frontend / "dist" / "index.html", 2_000)
    for path in (frontend / "index.html", frontend / "package.json"):
        _set_mtime(path, 1_000)
    _set_mtime(frontend / "src" / "main.ts", 3_000)
    assert run_local.needs_build(frontend) is True


def test_port_is_free_detects_a_bound_port(run_local):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        assert run_local.port_is_free(port) is False
    assert run_local.port_is_free(port) is True


def test_parse_args_defaults_and_bounds(run_local, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("PORT", raising=False)
    assert run_local.parse_args([]).port == 4701
    assert run_local.parse_args(["--port", "5001", "--rebuild", "--no-browser"]).rebuild is True
    with pytest.raises(SystemExit):
        run_local.parse_args(["--port", "70000"])
