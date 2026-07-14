"""Tests for the shared identity matching helper.

Purpose:
Validate the SQL fragments and tolerance constants that define metadata
identity matching across lifecycle, status, browse, and integrity paths.

Guarantees:
Identity helper fragments keep exact nanosecond matching, legacy
seconds bridge, alias substitution, and exported tolerance constants stable.

Run when:
Changing metadata identity predicates, mtime tolerance policy, or SQL joins that
match assets, image metadata, and metadata jobs.
"""

from __future__ import annotations

import ntpath
import sqlite3

from backend.metadata_store import identity, path_utils
from backend.metadata_store.identity import (
    _NANOS_PER_SEC,
    MTIME_NS_TOLERANCE,
    MTIME_SEC_TOLERANCE,
    asset_matches_image_metadata_sql,
    asset_matches_metadata_job_sql,
    job_matches_image_metadata_sql,
)

# ── constants ──────────────────────────────────────────────────────────


def test_constants_are_exported() -> None:
    assert MTIME_NS_TOLERANCE == 0
    assert MTIME_SEC_TOLERANCE == 1e-3


def test_windows_canonical_path_rejects_mixed_separator_traversal(monkeypatch) -> None:
    monkeypatch.setattr(identity.os, "sep", "\\")
    predicate = identity.catalog_path_is_canonical_sql(path_sql=":path")
    with sqlite3.connect(":memory:") as conn:
        valid = conn.execute(f"SELECT {predicate}", {"path": r"C:\root\safe\image.png"}).fetchone()[0]
        traversal = conn.execute(
            f"SELECT {predicate}",
            {"path": r"C:\root\safe/../secret.png"},
        ).fetchone()[0]

    assert valid == 1
    assert traversal == 0


def test_windows_drive_and_unc_roots_are_canonical_and_own_children(monkeypatch) -> None:
    monkeypatch.setattr(identity.os, "sep", "\\")
    canonical = identity.catalog_path_is_canonical_sql(path_sql=":path")
    direct = identity.catalog_direct_child_sql(parent_path_sql=":parent", path_sql=":path")
    ownership = identity.catalog_import_path_owns_sql(library_id_sql=":library_id", path_sql=":path")

    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE library_import_paths(library_id INTEGER, path TEXT)")
        for root, child in (
            ("C:\\", "C:\\image.png"),
            ("C:\\root", "C:\\root\\image.png"),
            ("\\\\server\\share", "\\\\server\\share\\image.png"),
            ("\\\\server\\share\\", "\\\\server\\share\\image.png"),
        ):
            assert conn.execute(f"SELECT {canonical}", {"path": root}).fetchone()[0] == 1
            assert conn.execute(f"SELECT {canonical}", {"path": child}).fetchone()[0] == 1
            assert conn.execute(f"SELECT {direct}", {"parent": root, "path": child}).fetchone()[0] == 1
            conn.execute("DELETE FROM library_import_paths")
            conn.execute("INSERT INTO library_import_paths VALUES (1, ?)", (root,))
            assert (
                conn.execute(
                    f"SELECT {ownership}",
                    {"library_id": 1, "path": child},
                ).fetchone()[0]
                == 1
            )

        assert conn.execute(f"SELECT {canonical}", {"path": "\\"}).fetchone()[0] == 0
        conn.execute("DELETE FROM library_import_paths")
        conn.execute("INSERT INTO library_import_paths VALUES (1, ?)", ("\\",))
        assert (
            conn.execute(
                f"SELECT {ownership}",
                {"library_id": 1, "path": "\\\\server\\share\\image.png"},
            ).fetchone()[0]
            == 0
        )


def test_posix_canonical_paths_require_absolute_roots() -> None:
    canonical = identity.catalog_path_is_canonical_sql(path_sql=":path")
    ownership = identity.catalog_import_path_owns_sql(library_id_sql=":library_id", path_sql=":path")

    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE library_import_paths(library_id INTEGER, path TEXT)")
        conn.execute("INSERT INTO library_import_paths VALUES (1, 'relative/root')")

        assert conn.execute(f"SELECT {canonical}", {"path": "relative/root/image.png"}).fetchone()[0] == 0
        assert (
            conn.execute(
                f"SELECT {ownership}",
                {"library_id": 1, "path": "relative/root/image.png"},
            ).fetchone()[0]
            == 0
        )


def test_windows_catalog_normalization_preserves_drive_and_unc_roots(monkeypatch) -> None:
    monkeypatch.setattr(path_utils.os, "name", "nt")
    monkeypatch.setattr(path_utils.os, "sep", "\\")
    monkeypatch.setattr(path_utils.os, "path", ntpath)

    assert path_utils.canonicalize_catalog_path("C:\\") == "c:\\"
    assert path_utils.canonicalize_catalog_path("\\\\Server\\Share") == "\\\\server\\share"
    assert path_utils.canonicalize_catalog_path("\\\\Server\\Share\\") == "\\\\server\\share\\"


# ── SQL fragment structure ─────────────────────────────────────────────


def test_each_fragment_is_wrapped_in_parentheses() -> None:
    for fn in (asset_matches_image_metadata_sql, asset_matches_metadata_job_sql, job_matches_image_metadata_sql):
        sql = fn()
        assert sql.startswith("((") and sql.endswith("))"), f"{fn.__name__} lacks outer wrapper"


class TestAssetMatchesImageMetadataSql:
    def test_contains_both_aliases(self) -> None:
        sql = asset_matches_image_metadata_sql()
        assert "im.mtime_ns" in sql
        assert "a.mtime_ns" in sql
        assert "im.mtime" in sql

    def test_custom_aliases(self) -> None:
        sql = asset_matches_image_metadata_sql(asset_alias="ast", im_alias="meta")
        assert "meta.mtime_ns" in sql
        assert "ast.mtime_ns" in sql
        assert "meta.mtime" in sql

    def test_has_two_branches(self) -> None:
        sql = asset_matches_image_metadata_sql()
        assert sql.count("OR") == 1
        assert sql.count("AND") == 4  # 2 branches × 2 AND per branch

    def test_includes_exact_match_and_seconds_tolerance(self) -> None:
        sql = asset_matches_image_metadata_sql()
        assert "im.mtime_ns = a.mtime_ns" in sql
        assert str(MTIME_SEC_TOLERANCE) in sql

    def test_includes_nanos_per_sec(self) -> None:
        sql = asset_matches_image_metadata_sql()
        assert str(int(_NANOS_PER_SEC)) in sql

    def test_default_and_custom_produce_same_pattern(self) -> None:
        default = asset_matches_image_metadata_sql()
        custom = asset_matches_image_metadata_sql(asset_alias="x", im_alias="y")
        assert "a." not in custom
        assert "im." not in custom
        assert default != custom


class TestAssetMatchesMetadataJobSql:
    def test_contains_both_aliases(self) -> None:
        sql = asset_matches_metadata_job_sql()
        assert "mj.mtime_ns" in sql
        assert "a.mtime_ns" in sql
        assert "mj.mtime" in sql

    def test_custom_aliases(self) -> None:
        sql = asset_matches_metadata_job_sql(asset_alias="ast", job_alias="j")
        assert "j.mtime_ns" in sql
        assert "ast.mtime_ns" in sql

    def test_has_two_branches(self) -> None:
        sql = asset_matches_metadata_job_sql()
        assert sql.count("OR") == 1

    def test_includes_exact_match_and_seconds_tolerance(self) -> None:
        sql = asset_matches_metadata_job_sql()
        assert "mj.mtime_ns = a.mtime_ns" in sql
        assert str(MTIME_SEC_TOLERANCE) in sql


class TestJobMatchesImageMetadataSql:
    def test_contains_both_aliases(self) -> None:
        sql = job_matches_image_metadata_sql()
        assert "mj.mtime_ns" in sql
        assert "im.mtime_ns" in sql
        assert "mj.mtime" in sql
        assert "im.mtime" in sql

    def test_custom_aliases(self) -> None:
        sql = job_matches_image_metadata_sql(job_alias="j", im_alias="meta")
        assert "j.mtime_ns" in sql
        assert "meta.mtime_ns" in sql

    def test_has_three_branches(self) -> None:
        sql = job_matches_image_metadata_sql()
        assert sql.count("OR") == 2

    def test_includes_exact_match_and_seconds_tolerance(self) -> None:
        sql = job_matches_image_metadata_sql()
        assert "im.mtime_ns = mj.mtime_ns" in sql
        assert str(MTIME_SEC_TOLERANCE) in sql
