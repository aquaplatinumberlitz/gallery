"""
Purpose:
Verifies DB-backed facet aggregation, scoping, output limits, and API endpoint behavior.

Guarantees:
* facets are read from indexed metadata without filesystem scans
* model, tool, sampler, folder, and LoRA facets respect scope and limit contracts

Run when:
* changing facets SQL, facet response shape, scope prefix handling, or LoRA extraction
* touching Library Inspector filters or metadata search facets
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import app
from backend.metadata_store import (
    _connect,
    _DB_LOCK,
    index_directory_tree,
    update_folder_index_state,
    upsert_extracted_metadata,
    initialize_database,
)
from backend.facets import build_facets
from backend.metadata_extract import ExtractedMetadata

client = TestClient(app)


def _seed_metadata(tmp_path: Path) -> None:
    """Create a folder with images and seed metadata into SQLite."""
    album = tmp_path / "album"
    album.mkdir()

    images_data = [
        ("img1.png", {"tool": "ComfyUI", "model": "ponyDiffusion", "sampler": "Euler a", "seed": "123", "scheduler": "normal"}),
        ("img2.png", {"tool": "ComfyUI", "model": "ponyDiffusion", "sampler": "Euler a", "seed": "456", "scheduler": "normal"}),
        ("img3.png", {"tool": "A1111", "model": "SDXL", "sampler": "DPM++ 2M", "seed": "789", "scheduler": "karras"}),
        ("img4.png", {"tool": "SwarmUI", "model": "SDXL", "sampler": "Euler a", "seed": "", "scheduler": "normal"}),
        ("img5.jpg", {"tool": "", "model": "", "sampler": "", "seed": "", "scheduler": ""}),
    ]

    for fname, meta in images_data:
        path = album / fname
        white = Image.new("RGB", (512, 512), (255, 255, 255))
        white.save(str(path))

        stat = path.stat()
        ext_meta = ExtractedMetadata(
            path=str(path.resolve()),
            name=fname,
            mtime=stat.st_mtime,
            size=stat.st_size,
            width=512,
            height=512,
            format="PNG" if fname.endswith(".png") else "JPEG",
            mode="RGB",
            has_alpha=0,
            prompt="test prompt",
            negative_prompt="",
            model=meta["model"],
            sampler=meta["sampler"],
            seed=meta["seed"],
            steps=None,
            cfg_scale=None,
            raw_metadata_text="",
            metadata_json='{"tool":"' + meta["tool"] + '"}',
            tool=meta["tool"],
            scheduler=meta["scheduler"],
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
            indexed_at=stat.st_mtime,
        )
        upsert_extracted_metadata(ext_meta)

    index_directory_tree(album, include_metadata=False)
    counts = {"child_count": len(images_data), "folder_count": 0, "image_count": len(images_data)}
    update_folder_index_state(album, complete=True, **counts)

    return album


def _scan_folder_counts(folder_path: Path) -> dict:
    import os
    folders = 0
    images = 0
    total = 0
    try:
        for entry in os.scandir(folder_path):
            if entry.name.startswith("."):
                continue
            total += 1
            try:
                if entry.is_dir():
                    folders += 1
                elif entry.is_file():
                    images += 1
            except OSError:
                pass
    except OSError:
        pass
    return {"child_count": total, "folder_count": folders, "image_count": images}


def test_facets_returns_model_tool_sampler_folder_counts_from_db(tmp_path: Path):
    album = _seed_metadata(tmp_path)

    facets = build_facets(folder_path=str(album))
    assert "tool" in facets
    assert "model" in facets
    assert "sampler" in facets
    assert "folders" in facets

    tool_values = {f["value"]: f["count"] for f in facets["tool"]}
    assert tool_values.get("ComfyUI", 0) == 2
    assert tool_values.get("A1111", 0) == 1

    model_values = {f["value"]: f["count"] for f in facets["model"]}
    assert model_values.get("ponyDiffusion", 0) == 2
    assert model_values.get("SDXL", 0) == 2


def test_facets_respects_scope(tmp_path: Path):
    album1 = _seed_metadata(tmp_path)
    album2 = tmp_path / "other"
    album2.mkdir()
    (album2 / "test.png").write_bytes(b"fake")

    index_directory_tree(album2, include_metadata=False)
    counts = _scan_folder_counts(album2)
    update_folder_index_state(album2, complete=True, **counts)

    facets_all = build_facets(folder_path=None)
    assert facets_all["tool"]

    facets_scoped = build_facets(folder_path=str(album2))
    assert facets_scoped["tool"] == []


def test_facets_does_not_scan_filesystem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    album = _seed_metadata(tmp_path)

    def fail_scandir(*args, **kwargs):
        raise AssertionError("facets must not scan filesystem")

    monkeypatch.setattr(Path, "iterdir", fail_scandir)

    facets = build_facets(folder_path=str(album))
    assert "tool" in facets


def test_facets_only_reads_db_not_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    album = _seed_metadata(tmp_path)

    def fail_scandir(*args, **kwargs):
        raise AssertionError("facets must not scan filesystem")

    monkeypatch.setattr(os, "scandir", fail_scandir)

    facets = build_facets(folder_path=str(album))
    assert "tool" in facets


def test_facets_caps_output_size(tmp_path: Path):
    album = _seed_metadata(tmp_path)

    facets = build_facets(folder_path=str(album), max_values=1)
    for key in ("tool", "model", "sampler", "folders"):
        assert len(facets.get(key, [])) <= 1


def test_facets_handles_empty_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.metadata_store as ms
    test_db = tmp_path / "test_empty_facets.db"
    monkeypatch.setattr(ms, "GALLERY_METADATA_DB", test_db)
    monkeypatch.setattr(ms, "_DB_INITIALIZED", False)

    facets = build_facets(folder_path=None)
    assert isinstance(facets, dict)
    for key in ("tool", "model", "sampler", "scheduler", "folders", "orientation"):
        assert key in facets
        assert isinstance(facets[key], list)
    assert "seed_availability" in facets
    assert "metadata_availability" in facets


def test_api_facets_endpoint(tmp_path: Path):
    album = _seed_metadata(tmp_path)

    response = client.get("/api/facets", params={"path": str(album)})
    assert response.status_code == 200
    data = response.json()
    assert "tool" in data
    assert "model" in data
    assert "folders" in data


def test_facets_scope_prefix_is_windows_safe():
    from backend.facets import _build_scope

    posix_where, posix_params = _build_scope("/home/user/images")
    assert posix_params["scope_prefix"].startswith("/home/user/images/")

    win_where, win_params = _build_scope("C:\\Users\\user\\images")
    sep = "\\"
    if os.sep == "/":
        resolved = str(Path("C:\\Users\\user\\images").resolve())
        expected_sep = os.sep
    else:
        expected_sep = "\\"
    assert win_params["scope_prefix"] is not None


def test_facets_lora_facet(tmp_path: Path):
    album = tmp_path / "album"
    album.mkdir()

    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import upsert_extracted_metadata, index_directory_tree, update_folder_index_state
    from PIL import Image

    path = album / "img1.png"
    white = Image.new("RGB", (512, 512), (255, 255, 255))
    white.save(str(path))

    stat = path.stat()
    ext_meta = ExtractedMetadata(
        path=str(path.resolve()),
        name="img1.png",
        mtime=stat.st_mtime,
        size=stat.st_size,
        width=512, height=512,
        format="PNG", mode="RGB", has_alpha=0,
        prompt="test", negative_prompt="",
        model="test", sampler="test", seed="",
        steps=None, cfg_scale=None,
        raw_metadata_text="",
        metadata_json='{}',
        tool="test", scheduler="",
        model_hash=None, lora_text="add_detail:0.8, lineart:0.4",
        generation_time=None,
        clip_skip=None, hires_upscale=None, hires_steps=None,
        denoising_strength=None, vae=None, ensd=None,
        aesthetic_score=None, date=None, aspect_ratio=None,
        indexed_at=stat.st_mtime,
    )
    upsert_extracted_metadata(ext_meta)

    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(album, complete=True, child_count=1, folder_count=0, image_count=1)

    facets = build_facets(folder_path=str(album))
    assert "lora" in facets
    lora_values = {f["value"]: f["count"] for f in facets["lora"]}
    assert lora_values.get("add_detail", 0) >= 1
    assert lora_values.get("lineart", 0) >= 1


def test_facets_empty_db_contains_lora(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.metadata_store as ms
    test_db = tmp_path / "test_facets_lora_empty.db"
    monkeypatch.setattr(ms, "GALLERY_METADATA_DB", test_db)
    monkeypatch.setattr(ms, "_DB_INITIALIZED", False)

    facets = build_facets(folder_path=None)
    assert "lora" in facets
    assert isinstance(facets["lora"], list)


def test_facets_lora_respects_output_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend.metadata_extract import ExtractedMetadata
    from backend.metadata_store import upsert_extracted_metadata, index_directory_tree, update_folder_index_state
    from PIL import Image

    album = tmp_path / "album"
    album.mkdir()
    for i in range(5):
        path = album / f"img{i}.png"
        white = Image.new("RGB", (512, 512), (255, 255, 255))
        white.save(str(path))
        stat = path.stat()
        ext_meta = ExtractedMetadata(
            path=str(path.resolve()), name=f"img{i}.png",
            mtime=stat.st_mtime, size=stat.st_size,
            width=512, height=512,
            format="PNG", mode="RGB", has_alpha=0,
            prompt="test", negative_prompt="",
            model="test", sampler="test", seed="",
            steps=None, cfg_scale=None,
            raw_metadata_text="", metadata_json='{}',
            tool="test", scheduler="",
            model_hash=None,
            lora_text="lora_a:1.0, lora_b:0.5" if i % 2 == 0 else "lora_c:0.8",
            generation_time=None,
            clip_skip=None, hires_upscale=None, hires_steps=None,
            denoising_strength=None, vae=None, ensd=None,
            aesthetic_score=None, date=None, aspect_ratio=None,
            indexed_at=stat.st_mtime,
        )
        upsert_extracted_metadata(ext_meta)

    index_directory_tree(album, include_metadata=False)
    update_folder_index_state(album, complete=True, child_count=5, folder_count=0, image_count=5)

    facets = build_facets(folder_path=str(album), max_values=2)
    assert len(facets["lora"]) <= 2
