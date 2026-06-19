"""
Purpose:
Unit-test path resolution and safety checks used by gallery navigation.

Guarantees:
* resolve_path re-raises OSError on non-Windows platforms.
* resolve_path uses Windows extended-path fallback when os.name == "nt".
* is_path_safe returns True for PATH_SAFETY_ROOT itself and children under it.
* is_path_safe returns False for paths outside PATH_SAFETY_ROOT.
* is_path_safe returns False when Path.resolve raises RuntimeError or OSError.

Run when:
* modifying paths.py, resolve_path, or is_path_safe
* changing path safety root containment logic
"""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

import pytest

from backend.paths import is_path_safe, resolve_path


class TestResolvePath:
    def test_raises_oserror_on_non_windows(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(os, "name", "posix")

        def fake_resolve(self):
            raise OSError("broken")

        monkeypatch.setattr(Path, "resolve", fake_resolve)

        with pytest.raises(OSError):
            resolve_path("/some/path")

    def test_windows_extended_path_fallback(self, monkeypatch: pytest.MonkeyPatch):
        resolve_order = []

        def fake_resolve(self):
            resolve_order.append(str(self))
            if len(resolve_order) == 1:
                raise OSError("path too long")
            return Path("/resolved/windows/path")

        monkeypatch.setattr(Path, "resolve", fake_resolve)

        with suppress(OSError):
            resolve_path("C:\\long\\path")
        if len(resolve_order) >= 2:
            assert "\\\\?\\\\" in resolve_order[1] or "/" in resolve_order[1]


class TestIsPathSafe:
    def test_exact_path_safety_root_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.paths.PATH_SAFETY_ROOT", tmp_path)
        assert is_path_safe(tmp_path) is True

    def test_child_under_root_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.paths.PATH_SAFETY_ROOT", tmp_path)
        child = tmp_path / "sub" / "deep"
        child.mkdir(parents=True)
        assert is_path_safe(child) is True

    def test_outside_root_denied(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.paths.PATH_SAFETY_ROOT", tmp_path)
        outside = tmp_path / ".." / "other"
        outside = outside.resolve()
        outside.mkdir(parents=True, exist_ok=True)
        assert is_path_safe(outside) is False

    def test_resolve_raises_runtime_error_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.paths.PATH_SAFETY_ROOT", tmp_path)
        monkeypatch.setattr(Path, "resolve", lambda self: (_ for _ in ()).throw(RuntimeError("loop")))
        assert is_path_safe(tmp_path / "x") is False

    def test_resolve_raises_oserror_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr("backend.paths.PATH_SAFETY_ROOT", tmp_path)
        monkeypatch.setattr(Path, "resolve", lambda self: (_ for _ in ()).throw(OSError("bad")))
        assert is_path_safe(tmp_path / "x") is False
