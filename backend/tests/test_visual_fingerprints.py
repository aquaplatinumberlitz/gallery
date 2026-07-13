"""Pillow-only visual fingerprint schema, worker, lookup, and HTTP contracts.

Purpose:
Protect R3 near-duplicate fingerprints, derivative-only extraction, indexed
band candidates, honest transform limits, and persisted visual requests.

Guarantees:
Fingerprints have fixed byte sizes and eight bands; resize/re-encode/light color
fixtures match while crop/mirror/rotation limits remain explicit; missing
derivatives queue normal work; migration is rollback-safe; HTTP never decodes.

Run when:
Changing visual algorithms, thresholds, schema/bands, derivative integration,
visual index lifecycle, scope filtering, or visual Related Assets responses.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

import backend.metadata_store._schema as schema_module
import backend.related_assets as related_module
import backend.visual_fingerprints as visual_module
from backend.metadata_store import register_library
from backend.metadata_store._db import _connect
from backend.metadata_store.search_index_store import create_search_index_job, get_search_index_job
from backend.search_indexer import run_search_index_once
from backend.search_scope import SearchScopeContext
from backend.visual_fingerprints import (
    VISUAL_DERIVATIVE_VERSION,
    VISUAL_FINGERPRINT_ALGORITHM_VERSION,
    VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
    compute_visual_fingerprint,
    extract_visual_fingerprint,
    persist_visual_fingerprint,
    query_visual_variants,
)


def _base_image(path: Path) -> None:
    image = Image.new("RGB", (320, 240), (238, 231, 214))
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 20, 145, 210), fill=(35, 75, 120))
    draw.ellipse((175, 25, 300, 150), fill=(198, 73, 54))
    draw.polygon(((170, 220), (245, 135), (315, 220)), fill=(54, 145, 88))
    for offset in range(0, 100, 12):
        draw.line((30, 35 + offset, 130, 55 + offset), fill=(235, 205, 90), width=4)
    image.save(path)


def _variants(root: Path) -> dict[str, Path]:
    paths = {
        key: root / f"{key}.png" for key in ("reference", "resize", "light", "crop", "mirror", "rotation", "unrelated")
    }
    _base_image(paths["reference"])
    with Image.open(paths["reference"]) as source:
        source.resize((160, 120), Image.Resampling.LANCZOS).save(paths["resize"])
        ImageEnhance.Color(ImageEnhance.Brightness(source).enhance(1.08)).enhance(0.78).save(paths["light"])
        source.crop((55, 35, 285, 215)).resize(source.size, Image.Resampling.LANCZOS).save(paths["crop"])
        ImageOps.mirror(source).save(paths["mirror"])
        source.rotate(90, expand=True).save(paths["rotation"])
    Image.new("RGB", (320, 240), (120, 120, 120)).save(paths["unrelated"])
    reencode = root / "reencode.jpg"
    with Image.open(paths["reference"]) as source:
        source.save(reencode, quality=68)
    paths["reencode"] = reencode
    return paths


def _distance(left: dict[str, bytes], right: dict[str, bytes]) -> int:
    return (
        int.from_bytes(left["dhash_horizontal"], "big") ^ int.from_bytes(right["dhash_horizontal"], "big")
    ).bit_count() + (
        int.from_bytes(left["dhash_vertical"], "big") ^ int.from_bytes(right["dhash_vertical"], "big")
    ).bit_count()


def _seed_visual_assets(root: Path, paths: dict[str, Path]) -> tuple[dict, dict[str, int]]:
    library = register_library(root, name="Visual variants")
    ids: dict[str, int] = {}
    with _connect() as conn:
        for ordinal, (key, path) in enumerate(paths.items()):
            stat = path.stat()
            with Image.open(path) as image:
                width, height = image.size
            cursor = conn.execute(
                """
                INSERT INTO assets (
                  library_id, path, parent_path, name, type, mtime_ns, size,
                  width, height, indexed_at, metadata_state, offline, deleted_at
                ) VALUES (?, ?, ?, ?, 'image', ?, ?, ?, ?, ?, 'done', 0, NULL)
                """,
                (
                    library["id"],
                    str(path),
                    str(path.parent),
                    path.name,
                    stat.st_mtime_ns,
                    stat.st_size,
                    width,
                    height,
                    float(ordinal + 1),
                ),
            )
            asset_id = int(cursor.lastrowid)
            ids[key] = asset_id
            payload = {
                **compute_visual_fingerprint(path),
                "source_mtime_ns": stat.st_mtime_ns,
                "source_size": stat.st_size,
                "derivative_role": "thumbnail:thumb_512",
                "derivative_version": VISUAL_DERIVATIVE_VERSION,
                "algorithm_version": VISUAL_FINGERPRINT_ALGORITHM_VERSION,
            }
            persist_visual_fingerprint(
                conn,
                {"id": asset_id, "library_id": library["id"]},
                payload,
            )
    return library, ids


def test_algorithm_fixed_sizes_and_documented_transform_distances(tmp_path: Path) -> None:
    paths = _variants(tmp_path)
    fingerprints = {key: compute_visual_fingerprint(path) for key, path in paths.items()}
    assert len(fingerprints["reference"]["dhash_horizontal"]) == 8
    assert len(fingerprints["reference"]["dhash_vertical"]) == 8
    assert len(fingerprints["reference"]["color_grid"]) == 48
    assert _distance(fingerprints["reference"], fingerprints["resize"]) <= 4
    assert _distance(fingerprints["reference"], fingerprints["reencode"]) <= 4
    assert _distance(fingerprints["reference"], fingerprints["light"]) <= 16
    assert _distance(fingerprints["reference"], fingerprints["crop"]) > 4
    assert _distance(fingerprints["reference"], fingerprints["mirror"]) > 16
    assert _distance(fingerprints["reference"], fingerprints["rotation"]) > 16


def test_indexed_visual_lookup_matches_variants_and_keeps_honest_limits(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
) -> None:
    paths = _variants(isolated_gallery_root)
    library, ids = _seed_visual_assets(isolated_gallery_root, paths)
    context = SearchScopeContext(kind="library", library_id=library["id"], library_name=library["name"])
    results = query_visual_variants(ids["reference"], context, limit=60)
    by_id = {item.asset_id: item for item in results}
    assert by_id[ids["resize"]].relation_tier == 80
    assert by_id[ids["reencode"]].relation_tier == 80
    assert by_id[ids["light"]].relation_tier == 60
    assert all([reason.value for reason in item.relation_reasons] == ["visual_variant"] for item in results)
    assert ids["crop"] not in by_id
    assert ids["mirror"] not in by_id
    assert ids["rotation"] not in by_id
    assert ids["unrelated"] not in by_id
    with _connect() as conn:
        assert conn.execute("SELECT count(*) FROM asset_visual_hash_bands").fetchone()[0] == len(ids) * 8


def test_extractor_uses_current_derivative_and_queues_missing_work(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _variants(isolated_gallery_root)
    library = register_library(isolated_gallery_root, name="Visual extractor")
    derivative_path = paths["resize"]
    source_path = paths["reference"]
    source_stat = source_path.stat()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, 1, 'done', 0, NULL)
            """,
            (
                library["id"],
                str(source_path),
                str(source_path.parent),
                source_path.name,
                source_stat.st_mtime_ns,
                source_stat.st_size,
            ),
        )
        asset_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format,
              quality, max_long_edge, status, cache_path
            ) VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'webp', 78, 512, 'ready', ?)
            """,
            (asset_id, source_stat.st_mtime_ns, source_stat.st_size, str(derivative_path)),
        )
    asset = {
        "id": asset_id,
        "library_id": library["id"],
        "path": str(source_path),
        "type": "image",
        "mtime_ns": source_stat.st_mtime_ns,
        "size": source_stat.st_size,
    }
    ready = extract_visual_fingerprint(asset)
    assert ready.status == "ready"
    assert ready.payload["derivative_role"] == "thumbnail:thumb_512"

    with _connect() as conn:
        conn.execute("DELETE FROM asset_derivatives WHERE asset_id = ?", (asset_id,))
    queued: list[int] = []
    monkeypatch.setattr(visual_module, "_queue_default_derivative", queued.append)
    pending = extract_visual_fingerprint(asset)
    assert pending.status == "skipped"
    assert pending.error_code == "derivative_pending"
    assert queued == [asset_id]


def test_durable_visual_backfill_is_atomic_and_idempotent(
    isolated_gallery_root: Path,
    isolated_metadata_db: Path,
) -> None:
    paths = _variants(isolated_gallery_root)
    library = register_library(isolated_gallery_root, name="Visual lifecycle")
    source, derivative = paths["reference"], paths["resize"]
    stat = source.stat()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO assets (
              library_id, path, parent_path, name, type, mtime_ns, size,
              width, height, indexed_at, metadata_state, offline, deleted_at
            ) VALUES (?, ?, ?, ?, 'image', ?, ?, 320, 240, 1, 'done', 0, NULL)
            """,
            (library["id"], str(source), str(source.parent), source.name, stat.st_mtime_ns, stat.st_size),
        )
        asset_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO asset_derivatives (
              asset_id, kind, variant, source_mtime_ns, source_size, format,
              quality, max_long_edge, status, cache_path
            ) VALUES (?, 'thumbnail', 'thumb_512', ?, ?, 'webp', 78, 512, 'ready', ?)
            """,
            (asset_id, stat.st_mtime_ns, stat.st_size, str(derivative)),
        )
    job = create_search_index_job(
        "visual_fingerprints",
        library["id"],
        mode="full",
        schema_version=1,
        extractor_version=VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
    )
    assert run_search_index_once(worker_id="visual-test") is True
    assert get_search_index_job(int(job["id"]))["state"] == "succeeded"
    with _connect() as conn:
        assert conn.execute("SELECT count(*) FROM asset_visual_fingerprints").fetchone()[0] == 1
        assert (
            conn.execute("SELECT count(*) FROM asset_visual_hash_bands WHERE asset_id = ?", (asset_id,)).fetchone()[0]
            == 8
        )
    missing = create_search_index_job(
        "visual_fingerprints",
        library["id"],
        mode="missing",
        schema_version=1,
        extractor_version=VISUAL_FINGERPRINT_EXTRACTOR_VERSION,
    )
    assert run_search_index_once(worker_id="visual-test") is True
    assert get_search_index_job(int(missing["id"]))["processed_count"] == 0


def test_v11_migration_is_transactional_and_has_no_inline_decode(
    isolated_metadata_db: Path,
) -> None:
    with _connect() as conn:
        conn.execute("DROP TABLE asset_visual_hash_bands")
        conn.execute("DROP TABLE asset_visual_fingerprints")
        conn.execute("PRAGMA user_version = 10")
        conn.commit()
        schema_module._migrate_v10_to_v11(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 11
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT count(*) FROM asset_visual_fingerprints").fetchone()[0] == 0
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v10.bak").exists()


def test_v11_migration_failure_rolls_back_and_keeps_backup(
    isolated_metadata_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect() as conn:
        conn.execute("DROP TABLE asset_visual_hash_bands")
        conn.execute("DROP TABLE asset_visual_fingerprints")
        conn.execute("PRAGMA user_version = 10")
        conn.commit()
    original = schema_module._execute_v11_migration_statement
    calls = 0

    def fail_second(conn: sqlite3.Connection, statement: str) -> None:
        nonlocal calls
        calls += 1
        original(conn, statement)
        if calls == 2:
            raise RuntimeError("v11 injected failure")

    monkeypatch.setattr(schema_module, "_execute_v11_migration_statement", fail_second)
    with _connect() as conn, pytest.raises(RuntimeError, match="injected"):
        schema_module._migrate_v10_to_v11(conn)
    with sqlite3.connect(isolated_metadata_db) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        assert (
            conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type = 'table' AND name = 'asset_visual_fingerprints'"
            ).fetchone()[0]
            == 0
        )
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v10.bak").exists()


def test_visual_http_reads_persisted_rows_without_decoding(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _variants(isolated_gallery_root)
    library, ids = _seed_visual_assets(isolated_gallery_root, paths)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO search_index_states (
              index_name, library_id, state, schema_version, extractor_version,
              indexed_count, target_count, failed_count, skipped_count, updated_at
            ) VALUES ('visual_fingerprints', ?, 'ready', 1, ?, 7, 7, 0, 0, 1)
            """,
            (library["id"], VISUAL_FINGERPRINT_EXTRACTOR_VERSION),
        )
    monkeypatch.setattr(
        visual_module,
        "compute_visual_fingerprint",
        lambda *_args: (_ for _ in ()).throw(AssertionError("HTTP decoded an image")),
    )
    response = isolated_app.post(
        "/api/search/related",
        json={
            "schema_version": 1,
            "reference_asset_id": ids["reference"],
            "profile": "visual",
            "scope": {"kind": "library", "library_id": library["id"]},
            "limit": 60,
        },
    )
    assert response.status_code == 200
    assert response.json()["returned"] >= 3


def test_visual_reference_without_current_fingerprint_returns_typed_409(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
) -> None:
    paths = _variants(isolated_gallery_root)
    library, ids = _seed_visual_assets(isolated_gallery_root, paths)
    with _connect() as conn:
        conn.execute(
            "DELETE FROM asset_visual_fingerprints WHERE asset_id = ?",
            (ids["reference"],),
        )
        conn.execute(
            """
            INSERT INTO search_index_states (
              index_name, library_id, state, schema_version, extractor_version,
              indexed_count, target_count, failed_count, skipped_count, updated_at
            ) VALUES ('visual_fingerprints', ?, 'degraded', 1, ?, 6, 7, 0, 1, 1)
            """,
            (library["id"], VISUAL_FINGERPRINT_EXTRACTOR_VERSION),
        )
    response = isolated_app.post(
        "/api/search/related",
        json={
            "schema_version": 1,
            "reference_asset_id": ids["reference"],
            "profile": "visual",
            "scope": {"kind": "library", "library_id": library["id"]},
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "reference_not_indexed"


def test_disabled_visual_index_does_not_disable_lexical_search(
    isolated_app: TestClient,
    isolated_gallery_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _variants(isolated_gallery_root)
    library, ids = _seed_visual_assets(isolated_gallery_root, paths)
    monkeypatch.setattr(related_module, "GALLERY_RELATED_VISUAL_ENABLED", False)
    visual = isolated_app.post(
        "/api/search/related",
        json={
            "schema_version": 1,
            "reference_asset_id": ids["reference"],
            "profile": "visual",
            "scope": {"kind": "library", "library_id": library["id"]},
        },
    )
    assert visual.status_code == 409
    assert visual.json()["detail"]["error"] == "feature_disabled"
    lexical = isolated_app.post(
        "/api/search/query",
        json={
            "schema_version": 1,
            "mode": "lexical",
            "text": "",
            "scope": {"kind": "library", "library_id": library["id"]},
            "filters": {"prompt_groups": [], "workflow_groups": []},
            "limit": 60,
        },
    )
    assert lexical.status_code == 200
