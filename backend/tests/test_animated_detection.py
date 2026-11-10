"""PR-04: animated images are detected from the container header, stored once per file identity and exposed.

Purpose:
Pin the header-only animated-image detector (GIF, WebP, APNG), the `assets.animated` column it fills (NULL means
not detected yet), its invalidation when a file changes, the bounded detection pass, the `animated` field of browse,
search and related rows, and the v15-to-v16 migration that adds the column and replaces the stale search-generation
trigger.

Guarantees:
* static and animated GIF, WebP and APNG files written by Pillow are told apart without decoding a frame
* garbage, empty, non-container and truncated files (every prefix of every sample) are "not animated" and never raise
* a PNG with a large text chunk before `acTL` is still found, and an `acTL` after `IDAT` is ignored
* a scan leaves `animated` NULL, the detection pass fills 0/1 for current files and leaves missing, changed or
  unreadable files NULL, and a rescan of a changed file resets the value so it is detected again
* browse, search and related rows carry `animated` (null while undetected)
* the v15 database migrates to v16 with a `.v15.bak` backup, the column, and a search-generation trigger that bumps
  the cache generation when `animated` changes; the migration is idempotent

Run when:
* changing `backend/animated.py`, `metadata_store/animated_store.py`, the `assets.animated` column, the scan upserts
  that reset it, or the `animated` field of the row models
"""

from __future__ import annotations

import io
import sqlite3
import struct
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.animated import detect_animated_file, sniff_animated
from backend.metadata_store import _connect, _connect_read, index_directory_tree, initialize_database, register_library
from backend.metadata_store._schema import CATALOG_SCHEMA_VERSION
from backend.metadata_store.animated_store import detect_pending_animated

FRAMES = [Image.new("RGB", (32, 32), (index * 70, 20, 90)) for index in range(3)]


def _encode(fmt: str, animated: bool, **extra: object) -> bytes:
    buffer = io.BytesIO()
    if animated:
        FRAMES[0].save(buffer, format=fmt, save_all=True, append_images=FRAMES[1:], duration=40, loop=0, **extra)
    else:
        FRAMES[0].save(buffer, format=fmt, **extra)
    return buffer.getvalue()


SAMPLES = {
    "gif-static": (_encode("GIF", False), False),
    "gif-animated": (_encode("GIF", True), True),
    "webp-static": (_encode("WEBP", False), False),
    "webp-static-alpha": (
        (lambda buffer: (Image.new("RGBA", (16, 16), (1, 2, 3, 4)).save(buffer, format="WEBP"), buffer.getvalue())[1])(
            io.BytesIO()
        ),
        False,
    ),
    "webp-animated": (_encode("WEBP", True), True),
    "png-static": (_encode("PNG", False), False),
    "png-animated": (_encode("PNG", True), True),
}


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + b"\x00\x00\x00\x00"


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_detector_tells_static_from_animated_containers(name: str, tmp_path: Path) -> None:
    data, expected = SAMPLES[name]
    assert sniff_animated(io.BytesIO(data)) is expected
    path = tmp_path / f"{name}.bin"
    path.write_bytes(data)
    assert detect_animated_file(path) is expected


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_detector_never_raises_on_any_truncation(name: str) -> None:
    data, _expected = SAMPLES[name]
    results = {sniff_animated(io.BytesIO(data[:length])) for length in range(len(data) + 1)}
    assert results <= {True, False}
    assert sniff_animated(io.BytesIO(data[:20])) is False  # too short to hold the animation marker


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF",
        b"GIF89a",
        b"RIFF",
        b"RIFF\x00\x00\x00\x00WEBP",
        b"RIFF\x00\x00\x00\x00WAVEfmt ",
        b"\x89PNG\r\n\x1a\n",
        b"\x89PNG\r\n\x1a\n" + b"\xff" * 8,
        b"\xff\xd8\xff\xe0" + b"\x00" * 64,
        bytes(range(256)) * 4,
        b"GIF89a" + b"\xff" * 200,
    ],
)
def test_detector_treats_garbage_as_not_animated(data: bytes) -> None:
    assert sniff_animated(io.BytesIO(data)) is False


def test_detector_is_none_for_a_missing_file_and_false_for_a_directory(tmp_path: Path) -> None:
    assert detect_animated_file(tmp_path / "missing.gif") is None
    assert detect_animated_file(tmp_path) is None


def test_png_actl_is_found_behind_a_large_text_chunk_and_ignored_after_idat() -> None:
    animated, _ = SAMPLES["png-animated"]
    signature, rest = animated[:8], animated[8:]
    ihdr_end = 8 + 4 + 4 + 13 + 4  # signature, then IHDR: length, tag, 13 bytes, crc
    big_text = _png_chunk(b"tEXt", b"parameters\x00" + b"x" * 200_000)
    padded = signature + rest[: ihdr_end - 8] + big_text + rest[ihdr_end - 8 :]
    assert sniff_animated(io.BytesIO(padded)) is True

    static, _ = SAMPLES["png-static"]
    idat_at = static.index(b"IDAT") - 4
    late_actl = static[:idat_at] + static[idat_at:].replace(b"IEND", b"acTL", 1)
    assert sniff_animated(io.BytesIO(late_actl)) is False


def test_gif_with_a_large_first_frame_is_still_detected_as_animated() -> None:
    big = Image.effect_noise((600, 600), 80).convert("RGB")
    buffer = io.BytesIO()
    big.save(buffer, format="GIF", save_all=True, append_images=[Image.new("RGB", (600, 600), (9, 9, 9))], duration=40)
    assert len(buffer.getvalue()) > 100_000  # many data sub-blocks before the second frame
    assert sniff_animated(io.BytesIO(buffer.getvalue())) is True


def test_webp_without_vp8x_but_with_an_anim_chunk_is_animated() -> None:
    payload = b"WEBP" + b"ANIM" + struct.pack("<I", 6) + b"\x00" * 6
    data = b"RIFF" + struct.pack("<I", len(payload)) + payload
    assert sniff_animated(io.BytesIO(data)) is True


# --- the stored value -------------------------------------------------------------------------------------------


def _write_gallery(root: Path) -> dict[str, Path]:
    folder = root / "animated"
    folder.mkdir()
    files = {
        "static.webp": SAMPLES["webp-static"][0],
        "moving.webp": SAMPLES["webp-animated"][0],
        "moving.gif": SAMPLES["gif-animated"][0],
        "still.gif": SAMPLES["gif-static"][0],
        "moving.png": SAMPLES["png-animated"][0],
        "still.png": SAMPLES["png-static"][0],
    }
    paths = {}
    for name, data in files.items():
        paths[name] = folder / name
        paths[name].write_bytes(data)
    jpeg = io.BytesIO()
    FRAMES[0].save(jpeg, format="JPEG")
    paths["photo.jpg"] = folder / "photo.jpg"
    paths["photo.jpg"].write_bytes(jpeg.getvalue())
    return paths


def _animated_by_name() -> dict[str, int | None]:
    with closing(_connect_read()) as conn:
        return {
            str(row["name"]): row["animated"]
            for row in conn.execute("SELECT name, animated FROM assets WHERE type = 'image'")
        }


@pytest.fixture
def gallery(isolated_gallery_root: Path, isolated_metadata_db: Path) -> tuple[int, dict[str, Path]]:
    paths = _write_gallery(isolated_gallery_root)
    library_id = int(register_library(isolated_gallery_root, name="Animated")["id"])
    index_directory_tree(isolated_gallery_root)
    return library_id, paths


def test_scan_leaves_animated_unknown_and_the_pass_fills_it(gallery: tuple[int, dict[str, Path]]) -> None:
    library_id, _paths = gallery
    assert set(_animated_by_name().values()) == {None}
    counters = detect_pending_animated(library_id)
    assert counters["detected"] == 7
    assert counters["animated"] == 3
    assert _animated_by_name() == {
        "static.webp": 0,
        "moving.webp": 1,
        "moving.gif": 1,
        "still.gif": 0,
        "moving.png": 1,
        "still.png": 0,
        "photo.jpg": 0,
    }
    assert detect_pending_animated(library_id) == {"detected": 0, "animated": 0, "unknown": 0}


def test_the_pass_runs_in_chunks_and_stops_on_request(gallery: tuple[int, dict[str, Path]]) -> None:
    library_id, _paths = gallery
    assert detect_pending_animated(library_id, should_stop=lambda: True)["detected"] == 0
    assert set(_animated_by_name().values()) == {None}
    assert detect_pending_animated(library_id, chunk_rows=2)["detected"] == 7
    assert None not in _animated_by_name().values()


def test_a_changed_file_is_detected_again(gallery: tuple[int, dict[str, Path]]) -> None:
    library_id, paths = gallery
    detect_pending_animated(library_id)
    assert _animated_by_name()["static.webp"] == 0

    paths["static.webp"].write_bytes(SAMPLES["webp-animated"][0])
    index_directory_tree(paths["static.webp"].parent.parent)
    assert _animated_by_name()["static.webp"] is None  # reset with the new identity
    assert _animated_by_name()["moving.webp"] == 1  # untouched files keep their value
    detect_pending_animated(library_id)
    assert _animated_by_name()["static.webp"] == 1


def test_a_row_whose_file_changed_since_the_scan_stays_unknown(gallery: tuple[int, dict[str, Path]]) -> None:
    library_id, paths = gallery
    paths["static.webp"].write_bytes(SAMPLES["webp-animated"][0])  # the row still holds the old identity
    paths["still.gif"].unlink()
    detect_pending_animated(library_id)
    by_name = _animated_by_name()
    assert by_name["static.webp"] is None
    assert by_name["still.gif"] is None
    assert by_name["moving.gif"] == 1


def test_unreadable_files_stay_unknown(gallery: tuple[int, dict[str, Path]], monkeypatch: pytest.MonkeyPatch) -> None:
    library_id, _paths = gallery
    import backend.metadata_store.animated_store as store

    monkeypatch.setattr(store, "detect_animated_file", lambda path: None)
    counters = detect_pending_animated(library_id)
    assert counters["unknown"] == 6  # the six GIF, WebP and PNG files; the JPEG needs no read
    by_name = _animated_by_name()
    assert by_name["photo.jpg"] == 0
    assert by_name["moving.gif"] is None


# --- API rows ---------------------------------------------------------------------------------------------------


def test_browse_and_search_rows_carry_animated(
    isolated_app: TestClient, gallery: tuple[int, dict[str, Path]], isolated_gallery_root: Path
) -> None:
    library_id, _paths = gallery
    folder = isolated_gallery_root / "animated"

    def browse() -> dict[str, bool | None]:
        response = isolated_app.get("/api/browse", params={"library_id": library_id, "path": str(folder)})
        assert response.status_code == 200
        return {item["name"]: item["animated"] for item in response.json()["media"]}

    def search() -> dict[str, bool | None]:
        response = isolated_app.get("/api/search", params={"q": "moving", "scope": "all"})
        assert response.status_code == 200
        return {item["name"]: item["animated"] for item in response.json()["media"]}

    assert set(browse().values()) == {None}
    assert set(search().values()) == {None}
    detect_pending_animated(library_id)
    listing = browse()
    assert listing["moving.webp"] is True
    assert listing["static.webp"] is False
    assert listing["still.gif"] is False
    assert listing["photo.jpg"] is False
    found = search()
    assert found == {"moving.webp": True, "moving.gif": True, "moving.png": True}


def test_related_rows_carry_animated(isolated_gallery_root: Path, isolated_metadata_db: Path) -> None:
    from backend.related_ranking import rank_related_metadata
    from backend.search_scope import SearchScopeContext

    from .test_related_assets_ranking import _seed_fixture

    primary, _secondary, ids = _seed_fixture(isolated_gallery_root)
    context = SearchScopeContext(kind="library", library_id=primary["id"], library_name=primary["name"])
    marked = ids["same_exact_recorded_settings"]
    with closing(_connect()) as conn:
        conn.execute("UPDATE assets SET animated = 1 WHERE id = ?", (marked,))
        conn.execute("UPDATE assets SET animated = 0 WHERE id = ?", (ids["same_family_different_seed"],))
        conn.commit()
    by_id = {
        item.asset_id: item for item in rank_related_metadata(ids["reference"], context, profile="related", limit=60)
    }
    assert by_id[marked].animated is True
    assert by_id[ids["same_family_different_seed"]].animated is False
    assert by_id[ids["rare_prompt_with_common_boilerplate"]].animated is None


def test_visual_related_rows_carry_animated(isolated_gallery_root: Path, isolated_metadata_db: Path) -> None:
    from backend.search_scope import SearchScopeContext
    from backend.visual_fingerprints import query_visual_variants

    from .test_visual_fingerprints import _seed_visual_assets, _variants

    paths = _variants(isolated_gallery_root)
    library, ids = _seed_visual_assets(isolated_gallery_root, paths)
    with closing(_connect()) as conn:
        conn.execute("UPDATE assets SET animated = 1 WHERE id = ?", (ids["resize"],))
        conn.commit()
    context = SearchScopeContext(kind="library", library_id=library["id"], library_name=library["name"])
    by_id = {item.asset_id: item for item in query_visual_variants(ids["reference"], context, limit=60)}
    assert by_id[ids["resize"]].animated is True
    assert by_id[ids["reencode"]].animated is None


# --- schema v16 --------------------------------------------------------------------------------------------------


def _generation() -> int:
    with closing(_connect_read()) as conn:
        return int(conn.execute("SELECT value FROM search_generation WHERE id = 1").fetchone()[0])


def test_v15_database_migrates_to_v16_with_backup_column_and_trigger(
    isolated_gallery_root: Path, isolated_metadata_db: Path
) -> None:
    from backend.metadata_store import _db

    paths = _write_gallery(isolated_gallery_root)
    register_library(isolated_gallery_root, name="Migration")
    index_directory_tree(isolated_gallery_root)
    with closing(_connect()) as conn:
        # Reconstruct a v15 database: no column, and the v15 trigger (it does not watch `animated`).
        conn.execute("DROP TRIGGER trg_search_generation_assets_update")
        conn.execute(
            "CREATE TRIGGER trg_search_generation_assets_update AFTER UPDATE OF library_id, path, parent_path, name, "
            "type, mtime_ns, size, width, height, offline, deleted_at, mime_type, duration_ms ON assets WHEN "
            "OLD.size IS NOT NEW.size BEGIN UPDATE search_generation SET value = value + 1 WHERE id = 1; END"
        )
        conn.execute("ALTER TABLE assets DROP COLUMN animated")
        conn.execute("PRAGMA user_version = 15")
        conn.commit()
    row_count = len(paths)

    _db._DB_INITIALIZED = False
    initialize_database()
    initialize_database()  # idempotent

    with closing(sqlite3.connect(isolated_metadata_db)) as raw:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == CATALOG_SCHEMA_VERSION == 16
        columns = {row[1] for row in raw.execute("PRAGMA table_info(assets)")}
        trigger = raw.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'trg_search_generation_assets_update'"
        ).fetchone()[0]
        assert raw.execute("SELECT count(*) FROM assets WHERE type = 'image'").fetchone()[0] == row_count
        assert raw.execute("SELECT count(*) FROM assets WHERE animated IS NOT NULL").fetchone()[0] == 0
    assert "animated" in columns
    assert "animated" in trigger
    assert isolated_metadata_db.with_suffix(f"{isolated_metadata_db.suffix}.v15.bak").exists()

    before = _generation()
    with closing(_connect()) as conn:
        conn.execute("UPDATE assets SET animated = 1 WHERE name = 'moving.gif'")
        conn.commit()
    assert _generation() > before, "a changed `animated` value must invalidate cached search windows"


def test_a_fresh_database_has_the_column_and_the_current_trigger(isolated_metadata_db: Path) -> None:
    with closing(_connect_read()) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
        trigger = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'trg_search_generation_assets_update'"
        ).fetchone()[0]
    assert "animated" in columns
    assert "animated" in trigger
