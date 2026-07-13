"""Secure metadata sidecar read regressions.

Purpose:
Exercise catalog-scoped, descriptor-based, bounded same-stem sidecar reads.

Guarantees:
Outside-root symlinks, replacement races, and growth races never disclose
content; used oversized API reads return 413; unused sidecars cannot break
embedded metadata; normal sidecars persist one identity.

Run when:
Changing metadata extraction, sidecar identity, metadata cache keys, or jobs.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import metadata_extract
from backend.metadata_extract import MetadataSidecarTooLargeError, extract_metadata
from backend.metadata_store import _DB_LOCK, _connect, index_file, register_library

from .conftest import create_test_png


@pytest.fixture(autouse=True)
def _isolated_database(isolated_metadata_db: Path) -> None:
    """Keep every sidecar test on a fresh schema."""


def _catalog_image(root: Path, name: str = "image.png") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    register_library(root)
    image = root / name
    create_test_png(image)
    stat = image.stat()
    assert index_file(image, image.name, image.parent, "image", stat.st_mtime, stat.st_size, 64, 64, "image/png")
    return image


def _valid_sidecar(prompt: str) -> str:
    return f"{prompt}\nNegative prompt: bad\nSteps: 20, Sampler: Euler a, Seed: 123"


def test_normal_sidecar_is_bounded_and_persists_same_descriptor_identity(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    image = _catalog_image(isolated_gallery_root / "library")
    sidecar = image.with_suffix(".txt")
    sidecar.write_text(_valid_sidecar("normal sidecar prompt"), encoding="utf-8")

    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 200
    assert response.json()["prompt"] == "normal sidecar prompt"
    sidecar_stat = sidecar.stat()
    with _DB_LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT source_path, source_mtime_ns, source_size FROM image_metadata WHERE path = ?",
            (str(image.resolve()),),
        ).fetchone()
    assert tuple(row) == (str(sidecar), sidecar_stat.st_mtime_ns, sidecar_stat.st_size)


def test_sidecar_symlink_outside_import_root_is_ignored(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    library = isolated_gallery_root / "library"
    image = _catalog_image(library)
    outside = isolated_gallery_root / "outside.txt"
    outside.write_text(_valid_sidecar("outside import secret"), encoding="utf-8")
    image.with_suffix(".txt").symlink_to(outside)

    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 200
    assert "outside import secret" not in response.text


def test_sidecar_symlink_outside_safety_root_is_ignored(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    tmp_path: Path,
) -> None:
    image = _catalog_image(isolated_gallery_root / "library")
    outside = tmp_path / "outside-safety.txt"
    outside.write_text(_valid_sidecar("outside safety secret"), encoding="utf-8")
    image.with_suffix(".txt").symlink_to(outside)

    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 200
    assert "outside safety secret" not in response.text


def test_sidecar_replacement_with_symlink_between_validation_and_open_is_ignored(
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _catalog_image(isolated_gallery_root / "library")
    sidecar = image.with_suffix(".txt")
    sidecar.write_text(_valid_sidecar("safe prompt"), encoding="utf-8")
    outside = isolated_gallery_root / "replacement-secret.txt"
    outside.write_text(_valid_sidecar("replacement secret"), encoding="utf-8")
    real_open = metadata_extract.os.open
    replaced = False

    def replace_then_open(path: os.PathLike[str] | str, flags: int) -> int:
        nonlocal replaced
        if Path(path) == sidecar and not replaced:
            replaced = True
            sidecar.unlink()
            sidecar.symlink_to(outside)
        return real_open(path, flags)

    monkeypatch.setattr(metadata_extract.os, "open", replace_then_open)
    extracted = extract_metadata(image)
    assert "replacement secret" not in extracted.raw_metadata_text
    assert extracted.source_path is None


def test_sidecar_growth_during_read_returns_413_and_background_error_is_bounded(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _catalog_image(isolated_gallery_root / "library")
    sidecar = image.with_suffix(".txt")
    sidecar.write_text("small", encoding="utf-8")
    monkeypatch.setattr(metadata_extract, "METADATA_SIDECAR_MAX_BYTES", 32)
    original_read = metadata_extract._read_sidecar_fd

    def grow_then_read(fd: int, max_bytes: int) -> bytes:
        with sidecar.open("a", encoding="utf-8") as stream:
            stream.write("x" * 128)
        return original_read(fd, max_bytes)

    monkeypatch.setattr(metadata_extract, "_read_sidecar_fd", grow_then_read)
    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 413
    assert response.json()["detail"]["error"] == "metadata_sidecar_too_large"

    with pytest.raises(MetadataSidecarTooLargeError) as caught:
        extract_metadata(image)
    assert str(sidecar) not in str(caught.value)
    assert len(str(caught.value)) < 100


def test_already_oversized_sidecar_returns_413(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _catalog_image(isolated_gallery_root / "library")
    image.with_suffix(".txt").write_bytes(b"x" * 65)
    monkeypatch.setattr(metadata_extract, "METADATA_SIDECAR_MAX_BYTES", 64)

    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 413


def test_unused_oversized_sidecar_does_not_override_or_break_embedded_metadata(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = _catalog_image(isolated_gallery_root / "library")
    image.with_suffix(".txt").write_bytes(b"x" * 65)
    monkeypatch.setattr(metadata_extract, "METADATA_SIDECAR_MAX_BYTES", 64)
    monkeypatch.setattr(
        metadata_extract,
        "_read_image_info",
        lambda _path: (
            64,
            64,
            "PNG",
            "RGB",
            0,
            {"parameters": "embedded prompt\nSteps: 20, Sampler: Euler a, Seed: 123"},
        ),
    )

    response = isolated_app.get("/api/metadata", params={"path": str(image)})
    assert response.status_code == 200
    assert response.json()["prompt"] == "embedded prompt"
    extracted = extract_metadata(image)
    assert extracted.prompt == "embedded prompt"
    assert extracted.source_path == str(image.with_suffix(".txt"))
    assert extracted.source_size == 65
