"""Result-pinning and oracle tests for scoped and fielded search (SC-01).

Purpose:
Pin the exact result sets, orders, album suggestions and counts of folder-scoped, library-scoped and
field-filtered searches over a deterministic corpus, so the scoped page plan (tier-ordered sources with the
scope and field predicates applied inside the bounded preselects) can never change what a scoped query returns.
The corpus is built to break shortcuts: paths that share a prefix (`a1111`, `a11112`, `a1111_x`, `A1111`),
LIKE wildcards in folder names, a second library with a same-named folder, an import path that overlaps another
library's root, offline and deleted assets that outrank everything, orphan file rows, size-mismatched assets and
an asset outside every import path.

Guarantees:
* every pinned (query, scope) pair returns the same ordered media list across all keyset pages (sha256 pinned),
  the same first-page album suggestions and the same count
* the planned page equals the exact single-statement page (the pre-SC-01 scoped plan) page by page, including
  the cross-source shadowing the bounded unscoped plan does not guarantee
* a bound too small for the match set, a lossy preselect and a too-selective scope fall back to the exact plan
  instead of dropping or repeating rows
* `search_index_count` equals the distinct paged total below the count cap

Run when:
* changing `ranked_search.py` (scope predicates, preselects, the page plan), `path_utils.py` scope SQL, the
  album-suggestion query, or the fielded parser's conditions

The pinned digests were recorded against the pre-optimisation planner (`c93b50a`, scoped and fielded queries on
the exact single-statement plan); never re-record them to make a change pass.
"""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from backend.metadata_store import (
    _connect,
    register_library,
    search_index,
    search_index_count,
    search_index_fielded,
)
from backend.metadata_store.search_text_index import rebuild_search_text_index

pytestmark = pytest.mark.usefixtures("isolated_metadata_db")

BASE_MTIME_NS = 1_760_000_000_000_000_000
PAGE_LIMIT = 40
NOW = 1_760_000_000.0

_PROMPT_WORDS = (
    "cat",
    "castle",
    "cinematic",
    "mountain",
    "misty",
    "art",
    "ancient",
    "city",
    "cozy",
    "moon",
    "ocean",
    "garden",
    "portrait",
    "neon",
    "amber",
    "river",
)
_NEGATIVE = ("blurry, ugly", "cartoon, mutated hands", "low quality", "", "cropped, watermark")
_MODELS = ("model-a", "cobalt-xl", "mix-v2", "perf-model-3", "")
_SAMPLERS = ("euler a", "dpm++ 2m", "ddim", "")
_NAME_STEMS = ("alpha", "mango", "cedar", "river", "silver", "image", "ink", "oasis", "plum", "stone")

# (folder relative to the gallery root, owning library, online image rows)
FOLDERS = (
    ("lib1/a1111", 1, 200),
    ("lib1/a1111/nested", 1, 60),
    ("lib1/a1111/nested/deep", 1, 30),
    ("lib1/a11112", 1, 40),
    ("lib1/a1111_x", 1, 30),
    ("lib1/A1111", 1, 20),
    ("lib1/per%cent", 1, 15),
    ("lib1/under_score", 1, 15),
    ("lib1/ünï cödé", 1, 15),
    ("lib1/plain", 1, 80),
    ("lib1/shared", 2, 30),  # library 2 rows inside library 1's root: the second library's import path overlaps it
    ("lib2/b2222", 2, 70),
    ("lib2/a1111", 2, 40),
)
_VIDEO_FOLDERS = {"lib1/a1111": 12, "lib2/b2222": 6}


def _prompt(rng: random.Random, index: int) -> str:
    words = [rng.choice(_PROMPT_WORDS) for _ in range(rng.randint(1, 7))]
    if index % 11 == 0:
        words.append(words[0])
    return ", ".join(words)


class _Builder:
    def __init__(self, conn: sqlite3.Connection, root: Path, library_ids: dict[int, int]) -> None:
        self.conn = conn
        self.root = root.resolve()
        self.library_ids = library_ids
        self.rng = random.Random(20261109)
        self.index = 0

    def folder_row(self, folder: Path, library: int) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, indexed_at, "
            "library_id) VALUES (?, ?, ?, 'folder', ?, ?, NULL, ?, ?)",
            (str(folder), folder.name, str(folder.parent), NOW, int(NOW * 1e9), NOW, self.library_ids[library]),
        )
        self.conn.execute(
            "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'folder', ?)",
            (folder.name, str(folder), str(folder.parent)),
        )

    def image(
        self,
        folder: Path,
        library: int,
        *,
        video: bool = False,
        asset: bool = True,
        offline: bool = False,
        deleted: bool = False,
        size_mismatch: bool = False,
        asset_library: int | None = None,
        mtime_ns: int | None = None,
    ) -> str:
        index = self.index
        self.index += 1
        stem = _NAME_STEMS[index % len(_NAME_STEMS)]
        name = f"{stem}_{index:04d}.{'mp4' if video else 'png'}"
        path = str(folder / name)
        slot = (index * 7919) % 1009
        if mtime_ns is None:
            mtime_ns = BASE_MTIME_NS + (slot // 5 if index % 37 == 0 else slot) * 1_000
        size = 4096 + index % 97
        kind = "video" if video else "image"
        library_id = self.library_ids[library]
        if asset:
            self.conn.execute(
                "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, "
                "indexed_at, metadata_state, offline, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, 64, 64, ?, 'ready', ?, ?)",
                (
                    self.library_ids[asset_library or library],
                    path,
                    str(folder),
                    name,
                    kind,
                    mtime_ns,
                    size + (1 if size_mismatch else 0),
                    NOW,
                    int(offline),
                    NOW if deleted else None,
                ),
            )
        self.conn.execute(
            "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
            "indexed_at, library_id) VALUES (?, ?, ?, ?, ?, ?, ?, 64, 64, ?, ?)",
            (path, name, str(folder), kind, mtime_ns / 1e9, mtime_ns, size, NOW, library_id),
        )
        self.conn.execute(
            "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, ?, ?)",
            (name, path, kind, str(folder)),
        )
        if not video:
            self.conn.execute(
                "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, format, mode, "
                "has_alpha, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, raw_metadata_text, "
                "metadata_json, updated_at, indexed_at) VALUES (?, ?, ?, ?, ?, 64, 64, 'PNG', 'RGB', 0, ?, ?, ?, ?, "
                "?, ?, 7.0, '', '', ?, ?)",
                (
                    path,
                    name,
                    mtime_ns / 1e9,
                    mtime_ns,
                    size,
                    _prompt(self.rng, index),
                    self.rng.choice(_NEGATIVE),
                    self.rng.choice(_MODELS),
                    self.rng.choice(_SAMPLERS),
                    str(1000 + index),
                    10 + index % 30,
                    NOW,
                    NOW,
                ),
            )
        return path


def _build_corpus(root: Path) -> dict[int, int]:
    """Two libraries over one tree, with the edge cases listed in the module docstring; returns library ids."""
    resolved = root.resolve()
    (resolved / "lib1").mkdir()
    (resolved / "lib2").mkdir()
    library_ids = {
        1: int(register_library(resolved / "lib1", name="Scoped one")["id"]),
        2: int(register_library(resolved / "lib2", name="Scoped two")["id"]),
    }
    with closing(_connect()) as conn:
        # Library 2's import path overlaps library 1's root: `lib1/shared` is inside both.
        conn.execute(
            "INSERT INTO library_import_paths (library_id, path, position, created_at, updated_at) "
            "VALUES (?, ?, 1, ?, ?)",
            (library_ids[2], str(resolved / "lib1" / "shared"), NOW, NOW),
        )
        builder = _Builder(conn, resolved, library_ids)
        for relative, library, count in FOLDERS:
            folder = resolved / relative
            # Every ancestor below the gallery root is a folder row of the owning library (as a scan writes them).
            parent = folder
            ancestors: list[Path] = []
            while parent != resolved:
                ancestors.append(parent)
                parent = parent.parent
            for ancestor in reversed(ancestors):
                builder.folder_row(ancestor, library)
            for _ in range(count):
                builder.image(folder, library)
            for _ in range(_VIDEO_FOLDERS.get(relative, 0)):
                builder.image(folder, library, video=True)
        a1111 = resolved / "lib1" / "a1111"
        newest = BASE_MTIME_NS + 10_000_000
        for offset in range(25):  # offline assets that outrank every online row of equal text
            builder.image(a1111, 1, offline=True, mtime_ns=newest + offset)
        for offset in range(10):
            builder.image(a1111, 1, deleted=True, mtime_ns=newest + 100 + offset)
        for offset in range(10):
            builder.image(a1111, 1, asset=False, mtime_ns=newest + 200 + offset)
        for offset in range(10):
            builder.image(a1111, 1, size_mismatch=True, mtime_ns=newest + 300 + offset)
        outside = resolved / "lib1_outside"  # shares the `lib1` text prefix but is under no import path
        builder.folder_row(outside, 1)
        for offset in range(10):
            builder.image(outside, 1, mtime_ns=newest + 400 + offset)
        rebuild_search_text_index(conn)
        conn.commit()
    return library_ids


# scope name -> (scope kind, folder relative to the gallery root, library number or None)
SCOPES: dict[str, tuple[str, str | None, int | None]] = {
    "library1": ("library", None, 1),
    "library2": ("library", None, 2),
    "root1": ("folder", "lib1", 1),
    "a1111": ("folder", "lib1/a1111", 1),
    "nested": ("folder", "lib1/a1111/nested", 1),
    "deep": ("folder", "lib1/a1111/nested/deep", 1),
    "a11112": ("folder", "lib1/a11112", 1),
    "a1111_x": ("folder", "lib1/a1111_x", 1),
    "A1111": ("folder", "lib1/A1111", 1),
    "percent": ("folder", "lib1/per%cent", 1),
    "underscore": ("folder", "lib1/under_score", 1),
    "unicode": ("folder", "lib1/ünï cödé", 1),
    "shared_lib2": ("folder", "lib1/shared", 2),
    "shared_lib1": ("folder", "lib1/shared", 1),
    "lib2_a1111": ("folder", "lib2/a1111", 2),
    "a1111_nolib": ("folder", "lib1/a1111", None),
}

QUERIES = (
    "a",
    "m",
    "c",
    "ca",
    "mi",
    "alph",
    "lph",
    "cedar png",
    "prompt:c",
    "name:a",
    "model:m",
    "a model:m",
    "c sampler:e",
    "mi name:r",
    "cat steps:>=20",
)


def _scope_arguments(root: Path, library_ids: dict[int, int], scope_name: str) -> tuple[str, str | None, int | None]:
    kind, relative, library = SCOPES[scope_name]
    folder = str(root.resolve() / relative) if relative is not None else None
    return kind, folder, library_ids[library] if library is not None else None


def _search(
    root: Path,
    library_ids: dict[int, int],
    scope_name: str,
    query: str,
    cursor: str | None = None,
    limit: int = PAGE_LIMIT,
) -> dict:
    kind, folder, library_id = _scope_arguments(root, library_ids, scope_name)
    fn = search_index_fielded if ":" in query else search_index
    return fn(query, kind, folder, limit, cursor, library_id=library_id)


def _walk(root: Path, library_ids: dict[int, int], scope_name: str, query: str, limit: int = PAGE_LIMIT):
    first = _search(root, library_ids, scope_name, query, None, limit)
    rows = list(first["media"])
    page = first
    seen: set[str] = set()
    while page["next_cursor"]:
        assert page["next_cursor"] not in seen, "cursor repeated"
        seen.add(page["next_cursor"])
        page = _search(root, library_ids, scope_name, query, page["next_cursor"], limit)
        assert page["albums"] == [], "albums belong to the first page only"
        rows.extend(page["media"])
    return rows, first


def _digest(rows: list[dict]) -> str:
    text = "\n".join(f"{row['name']}|{row['match_type']}|{row['type']}" for row in rows)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _album_digest(first: dict) -> str:
    albums = [
        {
            "name": album["name"],
            "path": Path(album["path"]).name,
            "library_id": album["library_id"],
            "match_type": album["match_type"],
            "image_count": album["image_count"],
            "has_children": album["has_children"],
            "covers": [Path(cover).name for cover in album["cover_images"]],
        }
        for album in first["albums"]
    ]
    return hashlib.sha256(json.dumps(albums, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _record(root: Path, library_ids: dict[int, int], scope_name: str, query: str) -> tuple[int, str, str, int]:
    rows, first = _walk(root, library_ids, scope_name, query)
    kind, folder, library_id = _scope_arguments(root, library_ids, scope_name)
    count = search_index_count(query, kind, folder, library_id=library_id)
    return len(rows), _digest(rows), _album_digest(first), count


@pytest.fixture
def corpus(isolated_gallery_root: Path) -> tuple[Path, dict[int, int]]:
    return isolated_gallery_root, _build_corpus(isolated_gallery_root)


# (query, scope) -> (media rows over all pages, media digest, first-page album digest, count)
PINNED: dict[tuple[str, str], tuple[int, str, str, int]] = {
    ("a", "library1"): (383, "90e63caf491503b4", "681e55bbcb123058", 383),
    ("m", "library1"): (434, "5acace64f9e11a23", "4f53cda18c2baa0c", 434),
    ("c", "library1"): (440, "b87d72aa8b9ee6c2", "1ae671e33d307937", 440),
    ("ca", "library1"): (257, "8759c87d395b7ffb", "4f53cda18c2baa0c", 257),
    ("mi", "library1"): (189, "743ca96873aa1146", "4f53cda18c2baa0c", 189),
    ("alph", "library1"): (52, "e3cba9604b52fa67", "4f53cda18c2baa0c", 52),
    ("lph", "library1"): (52, "8332c0e260f02cdc", "4f53cda18c2baa0c", 52),
    ("cedar png", "library1"): (51, "2eaa15e9a8ddb806", "4f53cda18c2baa0c", 51),
    ("prompt:c", "library1"): (419, "22be0138615da9df", "4f53cda18c2baa0c", 419),
    ("name:a", "library1"): (252, "b09ded49c5af2190", "4f53cda18c2baa0c", 252),
    ("model:m", "library1"): (288, "1776355c041504c5", "4f53cda18c2baa0c", 288),
    ("a model:m", "library1"): (221, "a177e1e05ead6d50", "681e55bbcb123058", 221),
    ("c sampler:e", "library1"): (105, "565d16f5531ae507", "1ae671e33d307937", 105),
    ("mi name:r", "library1"): (60, "ae9ebc16e3b9c333", "4f53cda18c2baa0c", 60),
    ("cat steps:>=20", "library1"): (80, "c7e7adc176a713cd", "4f53cda18c2baa0c", 80),
    ("a", "library2"): (107, "a6211fd5b8bde1e1", "291b561372e18074", 107),
    ("m", "library2"): (126, "7062ea5839773431", "4f53cda18c2baa0c", 126),
    ("c", "library2"): (122, "7a081e043a5724ab", "4f53cda18c2baa0c", 122),
    ("ca", "library2"): (75, "7fae59d8334a0f48", "4f53cda18c2baa0c", 75),
    ("mi", "library2"): (55, "96fdcccb714fa2a3", "4f53cda18c2baa0c", 55),
    ("alph", "library2"): (15, "a3c6518df6b3628f", "4f53cda18c2baa0c", 15),
    ("lph", "library2"): (15, "17f1345a07de841b", "4f53cda18c2baa0c", 15),
    ("cedar png", "library2"): (14, "7f6414999571c009", "4f53cda18c2baa0c", 14),
    ("prompt:c", "library2"): (111, "f3284838e47c0ea3", "4f53cda18c2baa0c", 111),
    ("name:a", "library2"): (70, "bce8216bb74b25c2", "4f53cda18c2baa0c", 70),
    ("model:m", "library2"): (84, "0a6bb61695654362", "4f53cda18c2baa0c", 84),
    ("a model:m", "library2"): (72, "3e920d18914c0913", "291b561372e18074", 72),
    ("c sampler:e", "library2"): (24, "8e40dfcd82e8bda7", "4f53cda18c2baa0c", 24),
    ("mi name:r", "library2"): (19, "2e5ff2948e5303ef", "4f53cda18c2baa0c", 19),
    ("cat steps:>=20", "library2"): (18, "823fafe3279d9b93", "4f53cda18c2baa0c", 18),
    ("a", "root1"): (383, "90e63caf491503b4", "681e55bbcb123058", 383),
    ("m", "root1"): (434, "5acace64f9e11a23", "4f53cda18c2baa0c", 434),
    ("c", "root1"): (440, "b87d72aa8b9ee6c2", "1ae671e33d307937", 440),
    ("ca", "root1"): (257, "8759c87d395b7ffb", "4f53cda18c2baa0c", 257),
    ("mi", "root1"): (189, "743ca96873aa1146", "4f53cda18c2baa0c", 189),
    ("alph", "root1"): (52, "e3cba9604b52fa67", "4f53cda18c2baa0c", 52),
    ("lph", "root1"): (52, "8332c0e260f02cdc", "4f53cda18c2baa0c", 52),
    ("cedar png", "root1"): (51, "2eaa15e9a8ddb806", "4f53cda18c2baa0c", 51),
    ("prompt:c", "root1"): (419, "22be0138615da9df", "4f53cda18c2baa0c", 419),
    ("name:a", "root1"): (252, "b09ded49c5af2190", "4f53cda18c2baa0c", 252),
    ("model:m", "root1"): (288, "1776355c041504c5", "4f53cda18c2baa0c", 288),
    ("a model:m", "root1"): (221, "a177e1e05ead6d50", "681e55bbcb123058", 221),
    ("c sampler:e", "root1"): (105, "565d16f5531ae507", "1ae671e33d307937", 105),
    ("mi name:r", "root1"): (60, "ae9ebc16e3b9c333", "4f53cda18c2baa0c", 60),
    ("cat steps:>=20", "root1"): (80, "c7e7adc176a713cd", "4f53cda18c2baa0c", 80),
    ("a", "a1111"): (220, "7227a2e4c05c3e9f", "cd74f2c8250db611", 220),
    ("m", "a1111"): (252, "f0881560f435411f", "4f53cda18c2baa0c", 252),
    ("c", "a1111"): (255, "f99bdf24201f5e4a", "4f53cda18c2baa0c", 255),
    ("ca", "a1111"): (156, "54e8ee49e4564296", "4f53cda18c2baa0c", 156),
    ("mi", "a1111"): (112, "93ac788435bf4762", "4f53cda18c2baa0c", 112),
    ("alph", "a1111"): (31, "9b563e5ff5cbedc9", "4f53cda18c2baa0c", 31),
    ("lph", "a1111"): (31, "d41dca566404c21a", "4f53cda18c2baa0c", 31),
    ("cedar png", "a1111"): (29, "6407e0f4f4e12866", "4f53cda18c2baa0c", 29),
    ("prompt:c", "a1111"): (246, "2197f48219249cba", "4f53cda18c2baa0c", 246),
    ("name:a", "a1111"): (145, "bf7753643686246e", "4f53cda18c2baa0c", 145),
    ("model:m", "a1111"): (163, "ebe9828f0b741bdc", "4f53cda18c2baa0c", 163),
    ("a model:m", "a1111"): (122, "b0e3709a41a61bf6", "cd74f2c8250db611", 122),
    ("c sampler:e", "a1111"): (64, "2208123f6d7add4e", "4f53cda18c2baa0c", 64),
    ("mi name:r", "a1111"): (34, "efbb6e61b9c7fc99", "4f53cda18c2baa0c", 34),
    ("cat steps:>=20", "a1111"): (47, "b9dfc7f833218b30", "4f53cda18c2baa0c", 47),
    ("a", "nested"): (73, "47bff77fd96bafb3", "4f53cda18c2baa0c", 73),
    ("m", "nested"): (72, "687a52922418795d", "4f53cda18c2baa0c", 72),
    ("c", "nested"): (77, "5766a1b87c65a0b5", "4f53cda18c2baa0c", 77),
    ("ca", "nested"): (46, "9bd1d28ebb180a7d", "4f53cda18c2baa0c", 46),
    ("mi", "nested"): (32, "12e9d42e15abf4e2", "4f53cda18c2baa0c", 32),
    ("alph", "nested"): (9, "33cb6337b8d9e104", "4f53cda18c2baa0c", 9),
    ("lph", "nested"): (9, "61c919ebbd764511", "4f53cda18c2baa0c", 9),
    ("cedar png", "nested"): (9, "cfbe2799d6932932", "4f53cda18c2baa0c", 9),
    ("prompt:c", "nested"): (76, "f47532e05cde73bc", "4f53cda18c2baa0c", 76),
    ("name:a", "nested"): (45, "64f4a743c935c4a2", "4f53cda18c2baa0c", 45),
    ("model:m", "nested"): (45, "33d808aa143efad9", "4f53cda18c2baa0c", 45),
    ("a model:m", "nested"): (35, "0b5d4d1591e62cbd", "4f53cda18c2baa0c", 35),
    ("c sampler:e", "nested"): (19, "33d9ad8d5c829dac", "4f53cda18c2baa0c", 19),
    ("mi name:r", "nested"): (9, "3defe0609580c315", "4f53cda18c2baa0c", 9),
    ("cat steps:>=20", "nested"): (9, "fc153f3ab7db4693", "4f53cda18c2baa0c", 9),
    ("a", "deep"): (27, "5d2d8ca79dd0d104", "4f53cda18c2baa0c", 27),
    ("m", "deep"): (24, "d240e4a4024c9fa0", "4f53cda18c2baa0c", 24),
    ("c", "deep"): (27, "d17deed0512aa633", "4f53cda18c2baa0c", 27),
    ("ca", "deep"): (18, "5649d98fb05131fc", "4f53cda18c2baa0c", 18),
    ("mi", "deep"): (12, "25eed7ffdfc8b899", "4f53cda18c2baa0c", 12),
    ("alph", "deep"): (3, "73c16711aa09d96b", "4f53cda18c2baa0c", 3),
    ("lph", "deep"): (3, "532d500fda8cd2da", "4f53cda18c2baa0c", 3),
    ("cedar png", "deep"): (3, "cbea53964f352153", "4f53cda18c2baa0c", 3),
    ("prompt:c", "deep"): (28, "ac40b33a2329e478", "4f53cda18c2baa0c", 28),
    ("name:a", "deep"): (15, "6008d1248602e3bb", "4f53cda18c2baa0c", 15),
    ("model:m", "deep"): (14, "df0a0ce004c0d046", "4f53cda18c2baa0c", 14),
    ("a model:m", "deep"): (12, "3def0935e4eb702c", "4f53cda18c2baa0c", 12),
    ("c sampler:e", "deep"): (8, "c780d9d03584ecdc", "4f53cda18c2baa0c", 8),
    ("mi name:r", "deep"): (5, "a1094b53f6bbe67b", "4f53cda18c2baa0c", 5),
    ("cat steps:>=20", "deep"): (3, "a4a45ef74f0f0274", "4f53cda18c2baa0c", 3),
    ("a", "a11112"): (31, "d92b06474a0478c8", "bf3ac637a7429c12", 31),
    ("m", "a11112"): (33, "f51610a00781c139", "4f53cda18c2baa0c", 33),
    ("c", "a11112"): (32, "ecdbeb936db6d207", "4f53cda18c2baa0c", 32),
    ("ca", "a11112"): (21, "bbbb6d485fc71029", "4f53cda18c2baa0c", 21),
    ("mi", "a11112"): (13, "a9ad91ef2fd27166", "4f53cda18c2baa0c", 13),
    ("alph", "a11112"): (4, "d63f1fdf45ef3205", "4f53cda18c2baa0c", 4),
    ("lph", "a11112"): (4, "905862f44aa0a554", "4f53cda18c2baa0c", 4),
    ("cedar png", "a11112"): (4, "31d4a00e80a29ed6", "4f53cda18c2baa0c", 4),
    ("prompt:c", "a11112"): (29, "baf8e9abc860afe6", "4f53cda18c2baa0c", 29),
    ("name:a", "a11112"): (20, "ee26658e4e5bb6b7", "4f53cda18c2baa0c", 20),
    ("model:m", "a11112"): (24, "5584e70d0c8422b6", "4f53cda18c2baa0c", 24),
    ("a model:m", "a11112"): (18, "d3fddd2e2af941da", "bf3ac637a7429c12", 18),
    ("c sampler:e", "a11112"): (11, "92c679d456bea061", "4f53cda18c2baa0c", 11),
    ("mi name:r", "a11112"): (3, "7177d76f4975810b", "4f53cda18c2baa0c", 3),
    ("cat steps:>=20", "a11112"): (7, "bbe2155b8f74cff5", "4f53cda18c2baa0c", 7),
    ("a", "a1111_x"): (21, "7fefa14cf2e7ab2e", "7ad39a4fe8a2fcc1", 21),
    ("m", "a1111_x"): (22, "16f07bba73793cf7", "4f53cda18c2baa0c", 22),
    ("c", "a1111_x"): (29, "695eb5ab4f2a4aa7", "4f53cda18c2baa0c", 29),
    ("ca", "a1111_x"): (17, "c9faf042cbd6ed4c", "4f53cda18c2baa0c", 17),
    ("mi", "a1111_x"): (8, "d78a80e579168173", "4f53cda18c2baa0c", 8),
    ("alph", "a1111_x"): (3, "b4649dc0bbb63d4f", "4f53cda18c2baa0c", 3),
    ("lph", "a1111_x"): (3, "0f3595462b27588f", "4f53cda18c2baa0c", 3),
    ("cedar png", "a1111_x"): (3, "776327aaff6e02e8", "4f53cda18c2baa0c", 3),
    ("prompt:c", "a1111_x"): (27, "ade287c5136c5028", "4f53cda18c2baa0c", 27),
    ("name:a", "a1111_x"): (15, "48c1cc1a02b1c3cb", "4f53cda18c2baa0c", 15),
    ("model:m", "a1111_x"): (16, "e4caeb8adc71311c", "4f53cda18c2baa0c", 16),
    ("a model:m", "a1111_x"): (12, "fe6d1d8c6cc9d515", "7ad39a4fe8a2fcc1", 12),
    ("c sampler:e", "a1111_x"): (5, "a8553daa14e5cf81", "4f53cda18c2baa0c", 5),
    ("mi name:r", "a1111_x"): (4, "8717b49f39d1426b", "4f53cda18c2baa0c", 4),
    ("cat steps:>=20", "a1111_x"): (5, "1f2fceaa94cf3e97", "4f53cda18c2baa0c", 5),
    ("a", "A1111"): (17, "134dac0296baf2ae", "5b27a0fb9d74734f", 17),
    ("m", "A1111"): (18, "db1b6e5032d14185", "4f53cda18c2baa0c", 18),
    ("c", "A1111"): (19, "3fa82fd624a47091", "4f53cda18c2baa0c", 19),
    ("ca", "A1111"): (8, "88903649de979343", "4f53cda18c2baa0c", 8),
    ("mi", "A1111"): (8, "3bbc21f4e9ca08cb", "4f53cda18c2baa0c", 8),
    ("alph", "A1111"): (2, "4a17188a6afcecba", "4f53cda18c2baa0c", 2),
    ("lph", "A1111"): (2, "d40dc0be572c441a", "4f53cda18c2baa0c", 2),
    ("cedar png", "A1111"): (2, "e941f06246acac17", "4f53cda18c2baa0c", 2),
    ("prompt:c", "A1111"): (16, "f153dd6c4915d30a", "4f53cda18c2baa0c", 16),
    ("name:a", "A1111"): (10, "0060a031553851b4", "4f53cda18c2baa0c", 10),
    ("model:m", "A1111"): (12, "e4c54c5d0854df28", "4f53cda18c2baa0c", 12),
    ("a model:m", "A1111"): (11, "77b43a8f7553d7c8", "5b27a0fb9d74734f", 11),
    ("c sampler:e", "A1111"): (4, "134a94e77b0b490e", "4f53cda18c2baa0c", 4),
    ("mi name:r", "A1111"): (2, "9ee60675dd290193", "4f53cda18c2baa0c", 2),
    ("cat steps:>=20", "A1111"): (2, "4f2e32a6693117bb", "4f53cda18c2baa0c", 2),
    ("a", "percent"): (12, "6ebe7479cba4e153", "4f53cda18c2baa0c", 12),
    ("m", "percent"): (15, "b719c89127afec0c", "4f53cda18c2baa0c", 15),
    ("c", "percent"): (15, "89eb11c298f925a9", "abe72f7f21ca6e8e", 15),
    ("ca", "percent"): (7, "11aabbb7cf80377e", "4f53cda18c2baa0c", 7),
    ("mi", "percent"): (5, "59edc7df7416d48d", "4f53cda18c2baa0c", 5),
    ("alph", "percent"): (1, "fc763fe41e757746", "4f53cda18c2baa0c", 1),
    ("lph", "percent"): (1, "3cba3fff43cbe521", "4f53cda18c2baa0c", 1),
    ("cedar png", "percent"): (2, "03229498ee23b305", "4f53cda18c2baa0c", 2),
    ("prompt:c", "percent"): (15, "478c29ae0e08aa5c", "4f53cda18c2baa0c", 15),
    ("name:a", "percent"): (7, "97401de60ff5b515", "4f53cda18c2baa0c", 7),
    ("model:m", "percent"): (12, "7ee0b41e7b70933b", "4f53cda18c2baa0c", 12),
    ("a model:m", "percent"): (10, "114eda10d4ece7cd", "4f53cda18c2baa0c", 10),
    ("c sampler:e", "percent"): (5, "07e7e45cb2506d90", "abe72f7f21ca6e8e", 5),
    ("mi name:r", "percent"): (1, "84462caea0996320", "4f53cda18c2baa0c", 1),
    ("cat steps:>=20", "percent"): (3, "256dac345fedda0c", "4f53cda18c2baa0c", 3),
    ("a", "underscore"): (10, "b1b29f5988d7710b", "4f53cda18c2baa0c", 10),
    ("m", "underscore"): (15, "3d46b596a227b79f", "4f53cda18c2baa0c", 15),
    ("c", "underscore"): (9, "bcfce73b29c0cb6d", "05f8e8bee425c152", 9),
    ("ca", "underscore"): (4, "b5dab755b98b66cc", "4f53cda18c2baa0c", 4),
    ("mi", "underscore"): (8, "8653c130eec5f661", "4f53cda18c2baa0c", 8),
    ("alph", "underscore"): (2, "10595e88c9620234", "4f53cda18c2baa0c", 2),
    ("lph", "underscore"): (2, "2887830c85fe3b1a", "4f53cda18c2baa0c", 2),
    ("cedar png", "underscore"): (1, "7a26b06c754a9840", "4f53cda18c2baa0c", 1),
    ("prompt:c", "underscore"): (9, "0f01edb608bd74d9", "4f53cda18c2baa0c", 9),
    ("name:a", "underscore"): (8, "27568eae2952a0d2", "4f53cda18c2baa0c", 8),
    ("model:m", "underscore"): (10, "b0a13fbf4cd9daa3", "4f53cda18c2baa0c", 10),
    ("a model:m", "underscore"): (8, "695e3f7c3bd3dafc", "4f53cda18c2baa0c", 8),
    ("c sampler:e", "underscore"): (2, "41327dd682fcbc8f", "05f8e8bee425c152", 2),
    ("mi name:r", "underscore"): (1, "24aff44604caa362", "4f53cda18c2baa0c", 1),
    ("cat steps:>=20", "underscore"): (1, "9863fc7c8733c7c3", "4f53cda18c2baa0c", 1),
    ("a", "unicode"): (11, "78cba26c59ae6777", "4f53cda18c2baa0c", 11),
    ("m", "unicode"): (10, "99e099db47cafe42", "4f53cda18c2baa0c", 10),
    ("c", "unicode"): (13, "4b5cdde72503974e", "d04b67675fe53c0a", 13),
    ("ca", "unicode"): (5, "59bdcee41f7c2179", "4f53cda18c2baa0c", 5),
    ("mi", "unicode"): (2, "f95a31dfd2bb0d47", "4f53cda18c2baa0c", 2),
    ("alph", "unicode"): (1, "df1b03fc331efe54", "4f53cda18c2baa0c", 1),
    ("lph", "unicode"): (1, "47ea39d3cb4dba86", "4f53cda18c2baa0c", 1),
    ("cedar png", "unicode"): (2, "b3796cb4ff47bb2d", "4f53cda18c2baa0c", 2),
    ("prompt:c", "unicode"): (11, "df4a5f262cef1d19", "4f53cda18c2baa0c", 11),
    ("name:a", "unicode"): (7, "166b99a4f7d2d5c7", "4f53cda18c2baa0c", 7),
    ("model:m", "unicode"): (7, "042ca8d40f696b66", "4f53cda18c2baa0c", 7),
    ("a model:m", "unicode"): (5, "05463bb7221232ae", "4f53cda18c2baa0c", 5),
    ("c sampler:e", "unicode"): (2, "fa258a39b89aaae4", "d04b67675fe53c0a", 2),
    ("mi name:r", "unicode"): (1, "d49f0a34d9c8c481", "4f53cda18c2baa0c", 1),
    ("cat steps:>=20", "unicode"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("a", "shared_lib2"): (21, "90cccc20ee2ebbce", "9a0c1b343c2fd631", 21),
    ("m", "shared_lib2"): (24, "0df27c85d4154f04", "4f53cda18c2baa0c", 24),
    ("c", "shared_lib2"): (25, "a3cc1f8299fab15f", "4f53cda18c2baa0c", 25),
    ("ca", "shared_lib2"): (14, "e8dbf76fabdf05b7", "4f53cda18c2baa0c", 14),
    ("mi", "shared_lib2"): (12, "f80ebeb338adac46", "4f53cda18c2baa0c", 12),
    ("alph", "shared_lib2"): (3, "5e8b7e9de657b7b5", "4f53cda18c2baa0c", 3),
    ("lph", "shared_lib2"): (3, "affa4243d220139a", "4f53cda18c2baa0c", 3),
    ("cedar png", "shared_lib2"): (3, "f67f50a3152ce9f8", "4f53cda18c2baa0c", 3),
    ("prompt:c", "shared_lib2"): (23, "0ca0f500dd62d5cd", "4f53cda18c2baa0c", 23),
    ("name:a", "shared_lib2"): (15, "5baf1c8722e89acc", "4f53cda18c2baa0c", 15),
    ("model:m", "shared_lib2"): (16, "1aa27f3db516f1e3", "4f53cda18c2baa0c", 16),
    ("a model:m", "shared_lib2"): (14, "7d4d523447fad1b8", "9a0c1b343c2fd631", 14),
    ("c sampler:e", "shared_lib2"): (7, "3df099328240dba2", "4f53cda18c2baa0c", 7),
    ("mi name:r", "shared_lib2"): (5, "5609d911f8d1ced4", "4f53cda18c2baa0c", 5),
    ("cat steps:>=20", "shared_lib2"): (4, "e4f3ca28e2cc3d18", "4f53cda18c2baa0c", 4),
    ("a", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("m", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("c", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("ca", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("mi", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("alph", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("lph", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("cedar png", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("prompt:c", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("name:a", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("model:m", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("a model:m", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("c sampler:e", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("mi name:r", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("cat steps:>=20", "shared_lib1"): (0, "e3b0c44298fc1c14", "4f53cda18c2baa0c", 0),
    ("a", "lib2_a1111"): (35, "9a18c416b870a789", "28dbc8cfb0890287", 35),
    ("m", "lib2_a1111"): (33, "7fe6fa76c3983742", "4f53cda18c2baa0c", 33),
    ("c", "lib2_a1111"): (36, "73c696e3fd12b96a", "4f53cda18c2baa0c", 36),
    ("ca", "lib2_a1111"): (19, "b7ea7c1bbed418d7", "4f53cda18c2baa0c", 19),
    ("mi", "lib2_a1111"): (16, "d4ad0f522cf855a8", "4f53cda18c2baa0c", 16),
    ("alph", "lib2_a1111"): (4, "68920f33df4fa710", "4f53cda18c2baa0c", 4),
    ("lph", "lib2_a1111"): (4, "63b7a25a63da1472", "4f53cda18c2baa0c", 4),
    ("cedar png", "lib2_a1111"): (4, "6707e540ed28670c", "4f53cda18c2baa0c", 4),
    ("prompt:c", "lib2_a1111"): (33, "3bff7ef673c9fef1", "4f53cda18c2baa0c", 33),
    ("name:a", "lib2_a1111"): (20, "7a0a6ecafe3bfbc9", "4f53cda18c2baa0c", 20),
    ("model:m", "lib2_a1111"): (22, "e6a900714ab03c49", "4f53cda18c2baa0c", 22),
    ("a model:m", "lib2_a1111"): (19, "927b5ba533d58289", "28dbc8cfb0890287", 19),
    ("c sampler:e", "lib2_a1111"): (8, "63dd28f38d03955e", "4f53cda18c2baa0c", 8),
    ("mi name:r", "lib2_a1111"): (4, "7e537eeeb52353e8", "4f53cda18c2baa0c", 4),
    ("cat steps:>=20", "lib2_a1111"): (3, "8aa26409f3f5404b", "4f53cda18c2baa0c", 3),
    ("a", "a1111_nolib"): (220, "7227a2e4c05c3e9f", "cd74f2c8250db611", 220),
    ("m", "a1111_nolib"): (252, "f0881560f435411f", "4f53cda18c2baa0c", 252),
    ("c", "a1111_nolib"): (255, "f99bdf24201f5e4a", "4f53cda18c2baa0c", 255),
    ("ca", "a1111_nolib"): (156, "54e8ee49e4564296", "4f53cda18c2baa0c", 156),
    ("mi", "a1111_nolib"): (112, "93ac788435bf4762", "4f53cda18c2baa0c", 112),
    ("alph", "a1111_nolib"): (31, "9b563e5ff5cbedc9", "4f53cda18c2baa0c", 31),
    ("lph", "a1111_nolib"): (31, "d41dca566404c21a", "4f53cda18c2baa0c", 31),
    ("cedar png", "a1111_nolib"): (29, "6407e0f4f4e12866", "4f53cda18c2baa0c", 29),
    ("prompt:c", "a1111_nolib"): (246, "2197f48219249cba", "4f53cda18c2baa0c", 246),
    ("name:a", "a1111_nolib"): (145, "bf7753643686246e", "4f53cda18c2baa0c", 145),
    ("model:m", "a1111_nolib"): (163, "ebe9828f0b741bdc", "4f53cda18c2baa0c", 163),
    ("a model:m", "a1111_nolib"): (122, "b0e3709a41a61bf6", "cd74f2c8250db611", 122),
    ("c sampler:e", "a1111_nolib"): (64, "2208123f6d7add4e", "4f53cda18c2baa0c", 64),
    ("mi name:r", "a1111_nolib"): (34, "efbb6e61b9c7fc99", "4f53cda18c2baa0c", 34),
    ("cat steps:>=20", "a1111_nolib"): (47, "b9dfc7f833218b30", "4f53cda18c2baa0c", 47),
}


def test_scoped_results_are_pinned(corpus: tuple[Path, dict[int, int]]) -> None:
    root, library_ids = corpus
    mismatches = []
    for scope_name in SCOPES:
        for query in QUERIES:
            actual = _record(root, library_ids, scope_name, query)
            if PINNED.get((query, scope_name)) != actual:
                mismatches.append(((query, scope_name), actual, PINNED.get((query, scope_name))))
    assert not mismatches, "\n".join(
        f"{key}: got {actual!r} expected {expected!r}" for key, actual, expected in mismatches
    )


def _exact_page(conn: sqlite3.Connection, query: str, scope_args: tuple, limit: int, cursor: dict | None):
    """One page of the pre-SC-01 scoped plan: the unbounded single UNION ALL statement (the oracle)."""
    from backend.fielded_search_parser import parse_fielded_query
    from backend.metadata_store import ranked_search as rs

    kind, folder, library_id = scope_args
    scope_sql, scope_params = rs._scope_clause(kind, folder, library_id)
    parsed = parse_fielded_query(query)
    field_where, field_params = ("", {})
    residual = query.strip()
    if parsed.fields:
        field_where, field_params = rs._field_conditions(parsed, None, None)
        residual = parsed.residual_text.strip()
    params = {"page_limit": limit + 1, **rs._text_match_params(residual), **scope_params, **field_params}
    if cursor is not None:
        params.update(
            cursor_tier=cursor["tier"],
            cursor_rank=cursor["rank"],
            cursor_mtime_ns=cursor["mtime_ns"],
            cursor_asset_id=cursor["asset_id"],
        )
    selects = rs._candidate_selects(
        residual,
        scope_sql,
        include_fts=True,
        field_where=field_where,
        include_videos=not parsed.fields,
        has_cursor=cursor is not None,
    )
    sql = rs.build_candidate_page_query(selects, has_cursor=cursor is not None, legacy_offset=False)
    return list(conn.execute(sql, params))


ORACLE_QUERIES = ("a", "m", "c", "lph", "a model:m", "c sampler:e", "mi name:r")
ORACLE_SCOPES = ("library1", "root1", "a1111", "nested", "a11112", "a1111_x", "shared_lib2", "a1111_nolib")


def _row_identity(row: sqlite3.Row) -> tuple:
    return (row["asset_id"], row["relevance_tier"], row["rank"], row["mtime_ns"])


@pytest.mark.parametrize("tight", (False, True), ids=("default-bound", "tiny-bound-forces-fallbacks"))
def test_planned_pages_equal_the_exact_statement_page_by_page(
    corpus: tuple[Path, dict[int, int]], monkeypatch: pytest.MonkeyPatch, tight: bool
) -> None:
    """Every keyset page of the scoped plan equals the exact statement's page, also with a bound too small."""
    from backend.fielded_search_parser import parse_fielded_query
    from backend.metadata_store import _connect_read
    from backend.metadata_store import ranked_search as rs

    root, library_ids = corpus
    if tight:
        monkeypatch.setattr(rs, "FTS_CANDIDATE_FLOOR", 8)
        monkeypatch.setattr(rs, "FILE_SOURCE_SMALL_LIMIT", 3)
    limit = 5 if tight else 30
    with closing(_connect_read()) as conn:
        for scope_name in ORACLE_SCOPES:
            scope_args = _scope_arguments(root, library_ids, scope_name)
            for query in ORACLE_QUERIES:
                parsed = parse_fielded_query(query)
                fingerprint = rs.request_fingerprint(
                    query, scope_args[0], scope_args[1], fielded=bool(parsed.fields), library_id=scope_args[2]
                )
                cursor = None
                for page_number in range(80):
                    oracle = _exact_page(conn, query, scope_args, limit, cursor)
                    encoded = (
                        None
                        if cursor is None
                        else rs.encode_search_cursor(
                            {
                                "asset_id": cursor["asset_id"],
                                "mtime_ns": cursor["mtime_ns"],
                                "rank": cursor["rank"],
                                "relevance_tier": cursor["tier"],
                            },  # type: ignore[arg-type]
                            fingerprint,
                        )
                    )
                    planned, _more, _fp = rs.search_ranked_media_page(
                        conn,
                        query,
                        scope_args[0],
                        scope_args[1],
                        limit,
                        encoded,
                        parsed=parsed if parsed.fields else None,
                        library_id=scope_args[2],
                    )
                    context = (scope_name, query, page_number, tight)
                    assert [_row_identity(r) for r in planned] == [_row_identity(r) for r in oracle[:limit]], context
                    if len(oracle) <= limit:
                        break
                    last = oracle[limit - 1]
                    cursor = {
                        "tier": int(last["relevance_tier"]),
                        "rank": float(last["rank"]),
                        "mtime_ns": int(last["mtime_ns"]),
                        "asset_id": int(last["asset_id"]),
                    }


def test_scope_filter_matches_whole_path_components_only() -> None:
    from backend.metadata_store.ranked_search import _scope_filter

    scope = _scope_filter("folder", "/g/lib1/a1111", 1)
    assert scope is not None
    sql = scope.sql("p", "l")
    with closing(sqlite3.connect(":memory:")) as conn:
        for path, library, expected in (
            ("/g/lib1/a1111", 1, True),
            ("/g/lib1/a1111/x.png", 1, True),
            ("/g/lib1/a1111/nested/y.png", 1, True),
            ("/g/lib1/a11112/x.png", 1, False),
            ("/g/lib1/a1111_x/x.png", 1, False),
            ("/g/lib1/A1111/x.png", 1, False),
            ("/g/lib1/a1111/x.png", 2, False),
        ):
            query = f"SELECT 1 FROM (SELECT :path AS p, :lib AS l) WHERE 1 = 1 {sql}"
            found = conn.execute(query, {**scope.params, "path": path, "lib": library}).fetchone()
            assert (found is not None) is expected, (path, library)


def test_page_plan_serves_scoped_queries_without_the_exact_fallback(
    corpus: tuple[Path, dict[int, int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.metadata_store import ranked_search as rs

    root, library_ids = corpus
    fallbacks: list[int] = []
    original = rs._run_page_plan

    def recording(*args: object, **kwargs: object):
        result = original(*args, **kwargs)  # type: ignore[arg-type]
        if result is None:
            fallbacks.append(1)
        return result

    monkeypatch.setattr(rs, "_run_page_plan", recording)
    for query in ("a", "m", "c", "a model:m"):
        # Clean folders: the anomalous rows (size-mismatched, unowned) live in a1111 and the library scopes, where a
        # cut-short preselect that loses rows to the strict joins correctly falls back to the exact statement.
        _walk(root, library_ids, "nested", query)
        _walk(root, library_ids, "a11112", query)
    assert not fallbacks


@pytest.mark.parametrize("query", ("cat", "c", "ca", "cat model:m"))
def test_cut_short_preselect_keeps_page_order_when_rows_tie_on_rank_and_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    """Rows tied on tier, rank and mtime past the bound: the plan still equals the exact statement page by page.

    A preselect breaks such ties by its own row id (metadata id or file rowid) while the page orders them by asset
    id. Here the metadata rows are written in the reverse order of the assets, so the two orders disagree and a
    cut-short preselect keeps a different subset of the tie group than the page needs: the plan must not treat
    that tie group as covered.
    """
    from backend.fielded_search_parser import parse_fielded_query
    from backend.metadata_store import _connect_read
    from backend.metadata_store import ranked_search as rs

    root = tmp_path.resolve()
    (root / "lib").mkdir()
    library_id = int(register_library(root / "lib", name="Ties")["id"])
    folder = root / "lib" / "batch"
    paths = [str(folder / f"img_{index:03d}.png") for index in range(60)]
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, indexed_at, library_id) "
            "VALUES (?, 'batch', ?, 'folder', ?, ?, NULL, ?, ?)",
            (str(folder), str(folder.parent), NOW, BASE_MTIME_NS, NOW, library_id),
        )
        for path in paths:
            name = Path(path).name
            conn.execute(
                "INSERT INTO assets (library_id, path, parent_path, name, type, mtime_ns, size, width, height, "
                "indexed_at, metadata_state, offline, deleted_at) "
                "VALUES (?, ?, ?, ?, 'image', ?, 100, 64, 64, ?, 'ready', 0, NULL)",
                (library_id, path, str(folder), name, BASE_MTIME_NS, NOW),
            )
            conn.execute(
                "INSERT INTO file_index (path, name, parent_path, type, mtime, mtime_ns, size, width, height, "
                "indexed_at, library_id) VALUES (?, ?, ?, 'image', ?, ?, 100, 64, 64, ?, ?)",
                (path, name, str(folder), BASE_MTIME_NS / 1e9, BASE_MTIME_NS, NOW, library_id),
            )
            conn.execute(
                "INSERT INTO file_index_fts (name, path, type, parent_path) VALUES (?, ?, 'image', ?)",
                (name, path, str(folder)),
            )
        for path in reversed(paths):  # metadata ids run against asset ids
            conn.execute(
                "INSERT INTO image_metadata (path, name, mtime, mtime_ns, size, width, height, format, mode, "
                "has_alpha, prompt, negative_prompt, model, sampler, seed, steps, cfg_scale, raw_metadata_text, "
                "metadata_json, updated_at, indexed_at) VALUES (?, ?, ?, ?, 100, 64, 64, 'PNG', 'RGB', 0, "
                "'cat castle', '', 'model-a', 'euler a', '1', 20, 7.0, '', '', ?, ?)",
                (path, Path(path).name, BASE_MTIME_NS / 1e9, BASE_MTIME_NS, NOW, NOW),
            )
        rebuild_search_text_index(conn)
        conn.commit()
    monkeypatch.setattr(rs, "FTS_CANDIDATE_FLOOR", 8)  # with limit 5 the bound is 24 rows: the tie group is cut
    limit = 5
    scope_args = ("folder", str(folder), library_id)
    parsed = parse_fielded_query(query)
    fingerprint = rs.request_fingerprint(
        query, "folder", str(folder), fielded=bool(parsed.fields), library_id=library_id
    )
    with closing(_connect_read()) as conn:
        cursor = None
        for page_number in range(20):
            oracle = _exact_page(conn, query, scope_args, limit, cursor)
            encoded = (
                None
                if cursor is None
                else rs.encode_search_cursor(
                    {
                        "asset_id": cursor["asset_id"],
                        "mtime_ns": cursor["mtime_ns"],
                        "rank": cursor["rank"],
                        "relevance_tier": cursor["tier"],
                    },  # type: ignore[arg-type]
                    fingerprint,
                )
            )
            planned, _more, _fp = rs.search_ranked_media_page(
                conn,
                query,
                "folder",
                str(folder),
                limit,
                encoded,
                parsed=parsed if parsed.fields else None,
                library_id=library_id,
            )
            assert [_row_identity(r) for r in planned] == [_row_identity(r) for r in oracle[:limit]], page_number
            if len(oracle) <= limit:
                break
            last = oracle[limit - 1]
            cursor = {
                "tier": int(last["relevance_tier"]),
                "rank": float(last["rank"]),
                "mtime_ns": int(last["mtime_ns"]),
                "asset_id": int(last["asset_id"]),
            }
