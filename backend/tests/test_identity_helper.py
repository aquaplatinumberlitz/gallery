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
