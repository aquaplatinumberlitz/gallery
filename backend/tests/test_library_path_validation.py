"""Library import-path overlap validation regressions.

Purpose:
Keep validation and persistence aligned for every pair of import paths.

Guarantees:
Decoy siblings do not hide nested overlaps; duplicates are rejected; true
siblings remain valid; create/update APIs enforce the same overlap contract.

Run when:
Changing library path normalization, validation, create, or update persistence.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.libraries import _path_overlaps


def test_validate_rejects_nested_path_hidden_by_lexicographic_decoy(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    parent = isolated_gallery_root / "a"
    decoy = isolated_gallery_root / "a-b"
    nested = parent / "b"
    nested.mkdir(parents=True)
    decoy.mkdir()
    paths = [str(parent), str(decoy), str(nested)]

    validation = isolated_app.post(
        "/api/libraries/validate",
        json={"name": "overlap", "import_paths": paths},
    )
    assert validation.status_code == 200
    body = validation.json()
    assert body["is_valid"] is False
    assert body["import_paths"][0]["is_valid"] is False
    assert body["import_paths"][1]["is_valid"] is True
    assert body["import_paths"][2]["is_valid"] is False

    created = isolated_app.post(
        "/api/libraries",
        json={"name": "overlap", "import_paths": paths},
    )
    assert created.status_code == 409
    assert created.json()["detail"]["error"] == "library_overlap"


def test_duplicates_rejected_and_siblings_allowed(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    first = isolated_gallery_root / "sibling-a"
    second = isolated_gallery_root / "sibling-b"
    first.mkdir()
    second.mkdir()

    duplicate = isolated_app.post(
        "/api/libraries/validate",
        json={"import_paths": [str(first), str(first)]},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["is_valid"] is False
    assert duplicate.json()["import_paths"][1]["message"] == "Duplicate import path"

    siblings = isolated_app.post(
        "/api/libraries/validate",
        json={"import_paths": [str(first), str(second)]},
    )
    assert siblings.status_code == 200
    assert siblings.json()["is_valid"] is True


def test_update_validation_and_persistence_reject_same_overlap(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    first = isolated_gallery_root / "first"
    nested = first / "nested"
    first.mkdir()
    nested.mkdir()
    created = isolated_app.post(
        "/api/libraries",
        json={"name": "Library", "import_paths": [str(first)]},
    )
    assert created.status_code == 201
    library_id = created.json()["id"]
    payload = {"import_paths": [str(first), str(nested)]}

    validation = isolated_app.post(f"/api/libraries/{library_id}/validate", json=payload)
    assert validation.status_code == 200
    assert validation.json()["is_valid"] is False

    update = isolated_app.patch(f"/api/libraries/{library_id}", json=payload)
    assert update.status_code == 409
    assert update.json()["detail"]["error"] == "library_overlap"


@pytest.mark.skipif(os.name != "nt", reason="Windows path semantics apply on Windows")
def test_windows_component_semantics() -> None:
    assert _path_overlaps(r"C:\Root\A", r"c:\root\a\child")
    assert not _path_overlaps(r"C:\Root\A", r"C:\Root\A-B")
