"""Shared identity matching helpers for exact nanosecond comparison.

Gallery's identity rule for matching a file across tables is:

    path + size + exact mtime_ns

The tolerance accounts for filesystem timestamp aliasing / precision loss
across reads. For rows that store mtime in seconds only (legacy), a seconds
bridge falls back to mtime comparison with 1 ms tolerance.

All functions return a self-contained SQL boolean expression wrapped in
parentheses (no trailing ``AND``) that can be embedded in ``JOIN … ON
<expr>``, ``WHERE EXISTS (… WHERE <expr>)``, etc.  :data:`path` and
:data:`size` equality is **not** included — callers add those as needed.

Notes:
------
- The ``assets`` table has **only** ``mtime_ns`` (no ``mtime`` column).
  Therefore the seconds bridge for ``asset_*`` helpers only goes in one
  direction: when the **other** table has NULL ``mtime_ns``, convert
  ``assets.mtime_ns`` to seconds and compare with the other table's
  ``mtime`` column.
- The ``metadata_index_jobs`` and ``image_metadata`` tables have **both**
  ``mtime`` and ``mtime_ns``, so the full two-direction seconds bridge is
  available for ``job_matches_image_metadata_sql``.
"""

from __future__ import annotations

import os

MTIME_NS_TOLERANCE = 0
"""Nanosecond identities are exact whenever both sides provide them."""

MTIME_SEC_TOLERANCE = 1e-3
"""Second tolerance for legacy mtime comparison (0.001 s = 1 ms)."""
_NANOS_PER_SEC: float = 1_000_000_000.0


def asset_matches_image_metadata_sql(*, asset_alias: str = "a", im_alias: str = "im") -> str:
    """Return SQL fragment matching an asset row to an image_metadata row.

    Two branches (assets has no ``mtime`` column):

    1. both sides have ``mtime_ns`` → exact match.
    2. ``image_metadata.mtime_ns`` is NULL → convert ``assets.mtime_ns`` to
       seconds and compare with ``image_metadata.mtime``.
    """
    return (
        f"(({im_alias}.mtime_ns IS NOT NULL AND {asset_alias}.mtime_ns IS NOT NULL "
        f"AND {im_alias}.mtime_ns = {asset_alias}.mtime_ns)"
        f" OR ({im_alias}.mtime_ns IS NULL AND {asset_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({asset_alias}.mtime_ns / {_NANOS_PER_SEC} - {im_alias}.mtime) < {MTIME_SEC_TOLERANCE}))"
    )


def asset_matches_metadata_job_sql(*, asset_alias: str = "a", job_alias: str = "mj") -> str:
    """Return SQL fragment matching an asset row to a metadata_index_jobs row.

    Two branches (assets has no ``mtime`` column):

    1. both sides have ``mtime_ns`` → ns tolerance match.
    2. ``metadata_index_jobs.mtime_ns`` is NULL → convert ``assets.mtime_ns``
       to seconds and compare with ``metadata_index_jobs.mtime``.
    """
    return (
        f"(({job_alias}.mtime_ns IS NOT NULL AND {asset_alias}.mtime_ns IS NOT NULL "
        f"AND {job_alias}.mtime_ns = {asset_alias}.mtime_ns)"
        f" OR ({job_alias}.mtime_ns IS NULL AND {asset_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({asset_alias}.mtime_ns / {_NANOS_PER_SEC} - {job_alias}.mtime) < {MTIME_SEC_TOLERANCE}))"
    )


def image_metadata_params_match_sql() -> str:
    """Return SQL for 3-branch identity match with ``?`` placeholders.

    The returned fragment compares ``image_metadata`` columns (``mtime_ns``,
    ``mtime``) against bound ``?`` parameters.  Callers embed this in
    ``WHERE`` after ``path=?`` and before ``AND size=?``.

    Parameter order (6 ``?`` placeholders): ``mtime_ns x5``, ``mtime x1``.
    """
    return (
        "(? IS NOT NULL AND mtime_ns IS NOT NULL AND mtime_ns = ?)"
        f" OR (? IS NOT NULL AND mtime_ns IS NULL AND ABS(? / {_NANOS_PER_SEC} - mtime) < {MTIME_SEC_TOLERANCE})"
        f" OR (? IS NULL AND mtime_ns IS NOT NULL AND ABS(mtime_ns / {_NANOS_PER_SEC} - ?) < {MTIME_SEC_TOLERANCE})"
    )


def asset_params_match_sql() -> str:
    """Return SQL for 2-branch identity match with ``?`` placeholders.

    The returned fragment compares ``assets`` columns (``mtime_ns``) against
    bound ``?`` parameters.  Assets has no ``mtime`` column, so the seconds
    bridge only goes one direction.

    Parameter order (4 ``?`` placeholders): ``mtime_ns x3``, ``mtime x1``.
    """
    return (
        "(? IS NOT NULL AND mtime_ns IS NOT NULL AND mtime_ns = ?)"
        f" OR (? IS NULL AND mtime_ns IS NOT NULL AND ABS(mtime_ns / {_NANOS_PER_SEC} - ?) < {MTIME_SEC_TOLERANCE})"
    )


def job_matches_image_metadata_sql(*, job_alias: str = "mj", im_alias: str = "im") -> str:
    """Return SQL fragment matching a metadata_index_jobs row to image_metadata.

    Three branches (both tables have ``mtime`` and ``mtime_ns``):

    1. both sides have ``mtime_ns`` → ns tolerance match.
    2. ``metadata_index_jobs.mtime_ns`` is NULL → convert
       ``image_metadata.mtime_ns`` to seconds and compare with
       ``metadata_index_jobs.mtime``.
    3. ``image_metadata.mtime_ns`` is NULL → convert
       ``metadata_index_jobs.mtime_ns`` to seconds and compare with
       ``image_metadata.mtime``.
    """
    return (
        f"(({job_alias}.mtime_ns IS NOT NULL AND {im_alias}.mtime_ns IS NOT NULL "
        f"AND {im_alias}.mtime_ns = {job_alias}.mtime_ns)"
        f" OR ({job_alias}.mtime_ns IS NULL AND {im_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({im_alias}.mtime_ns / {_NANOS_PER_SEC} - {job_alias}.mtime) < {MTIME_SEC_TOLERANCE})"
        f" OR ({im_alias}.mtime_ns IS NULL AND {job_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({job_alias}.mtime_ns / {_NANOS_PER_SEC} - {im_alias}.mtime) < {MTIME_SEC_TOLERANCE}))"
    )


def file_index_matches_image_metadata_sql(*, fi_alias: str = "fi", im_alias: str = "im") -> str:
    """Return an exact current-file identity predicate for metadata rows."""
    return (
        f"(({fi_alias}.size = {im_alias}.size OR ({fi_alias}.size IS NULL AND {im_alias}.size IS NULL)) AND ("
        f"({fi_alias}.mtime_ns IS NOT NULL AND {im_alias}.mtime_ns IS NOT NULL "
        f"AND {fi_alias}.mtime_ns = {im_alias}.mtime_ns)"
        f" OR ({fi_alias}.mtime_ns IS NULL AND {im_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({im_alias}.mtime_ns / {_NANOS_PER_SEC} - {fi_alias}.mtime) < {MTIME_SEC_TOLERANCE})"
        f" OR ({im_alias}.mtime_ns IS NULL AND {fi_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({fi_alias}.mtime_ns / {_NANOS_PER_SEC} - {im_alias}.mtime) < {MTIME_SEC_TOLERANCE})"
        f" OR ({fi_alias}.mtime_ns IS NULL AND {im_alias}.mtime_ns IS NULL "
        f"AND ABS({fi_alias}.mtime - {im_alias}.mtime) < {MTIME_SEC_TOLERANCE})))"
    )


def asset_owns_file_index_sql(*, asset_alias: str = "a", fi_alias: str = "fi") -> str:
    """Return the active registered-asset ownership predicate for a file row."""
    return (
        f"({asset_alias}.path = {fi_alias}.path "
        f"AND {asset_alias}.offline = 0 AND {asset_alias}.deleted_at IS NULL "
        f"AND {asset_alias}.mtime_ns IS NOT NULL AND ("
        f"({fi_alias}.mtime_ns IS NOT NULL AND {asset_alias}.mtime_ns = {fi_alias}.mtime_ns) "
        f"OR ({fi_alias}.mtime_ns IS NULL "
        f"AND ABS({asset_alias}.mtime_ns / {_NANOS_PER_SEC} - {fi_alias}.mtime) < {MTIME_SEC_TOLERANCE})) "
        f"AND ({asset_alias}.size = {fi_alias}.size "
        f"OR ({asset_alias}.size IS NULL AND {fi_alias}.size IS NULL)) "
        f"AND (({asset_alias}.type = 'image' AND {fi_alias}.type IN ('image', 'photo')) "
        f"OR ({asset_alias}.type = 'video' AND {fi_alias}.type = 'video')) "
        f"AND EXISTS (SELECT 1 FROM libraries AS owner_library "
        f"WHERE owner_library.id = {asset_alias}.library_id))"
    )


def active_catalog_file_sql(*, fi_alias: str = "fi") -> str:
    """Return an EXISTS predicate requiring a current active catalog asset."""
    ownership = asset_owns_file_index_sql(asset_alias="catalog_asset", fi_alias=fi_alias)
    return f"EXISTS (SELECT 1 FROM assets AS catalog_asset WHERE {ownership})"


def catalog_folder_has_active_asset_sql(*, fi_alias: str = "fi") -> str:
    """Require a registered folder row that contains at least one active asset."""
    separator = os.sep.replace("'", "''")
    return (
        f"({fi_alias}.library_id IS NOT NULL "
        f"AND EXISTS (SELECT 1 FROM libraries AS folder_library "
        f"WHERE folder_library.id = {fi_alias}.library_id) "
        f"AND EXISTS (SELECT 1 FROM assets AS folder_asset "
        f"JOIN libraries AS folder_asset_library ON folder_asset_library.id = folder_asset.library_id "
        f"WHERE folder_asset.library_id = {fi_alias}.library_id "
        f"AND folder_asset.offline = 0 AND folder_asset.deleted_at IS NULL "
        f"AND ({fi_alias}.path = '{separator}' OR folder_asset.parent_path = {fi_alias}.path "
        f"OR substr(folder_asset.path, 1, length({fi_alias}.path) + 1) = "
        f"{fi_alias}.path || '{separator}')))"
    )


def current_file_metadata_sql(*, fi_alias: str = "fi", im_alias: str = "im") -> str:
    """Return a predicate excluding stale metadata and inactive catalog assets."""
    identity = file_index_matches_image_metadata_sql(fi_alias=fi_alias, im_alias=im_alias)
    return f"({identity} AND {active_catalog_file_sql(fi_alias=fi_alias)})"
