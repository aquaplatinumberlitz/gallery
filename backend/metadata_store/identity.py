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


def _windows_drive_root_sql(path_sql: str) -> str:
    r"""Return a SQL predicate recognizing a normalized `C:\` drive root."""
    return f"(length({path_sql}) = 3 AND substr({path_sql}, 1, 1) GLOB '[A-Za-z]' AND substr({path_sql}, 2, 2) = ':\\')"


def _windows_unc_root_sql(path_sql: str) -> str:
    r"""Return a SQL predicate recognizing `\\server\share` with optional trailing slash."""
    separator = "\\"
    double_separator = separator * 2
    tail = f"substr({path_sql}, 3)"
    share = f"substr({tail}, instr({tail}, '{separator}') + 1)"
    return (
        f"(substr({path_sql}, 1, 2) = '{double_separator}' "
        f"AND instr({tail}, '{separator}') > 1 "
        f"AND {share} != '' AND ("
        f"instr({share}, '{separator}') = 0 OR ("
        f"substr({share}, -1, 1) = '{separator}' "
        f"AND length({share}) > 1 "
        f"AND instr(substr({share}, 1, length({share}) - 1), '{separator}') = 0)))"
    )


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
    direct_child = catalog_direct_child_sql(
        parent_path_sql=f"{fi_alias}.parent_path",
        path_sql=f"{fi_alias}.path",
    )
    return (
        f"({asset_alias}.library_id = {fi_alias}.library_id "
        f"AND {asset_alias}.path = {fi_alias}.path "
        f"AND {asset_alias}.parent_path = {fi_alias}.parent_path "
        f"AND {direct_child} "
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


def catalog_import_path_owns_sql(*, library_id_sql: str, path_sql: str) -> str:
    """Require lexical containment in one registered import path.

    This is intentionally catalog-only: it does not resolve or stat the path.
    Catalog writes normalize import paths and asset paths before persistence.
    """
    separator = os.sep.replace("'", "''")
    canonical_path = catalog_path_is_canonical_sql(path_sql=path_sql)
    canonical_root = catalog_path_is_canonical_sql(path_sql="catalog_import_path.path")
    windows_root_owns = ""
    if os.sep == "\\":
        trailing_root = (
            f"({_windows_drive_root_sql('catalog_import_path.path')} OR "
            f"({_windows_unc_root_sql('catalog_import_path.path')} "
            "AND substr(catalog_import_path.path, -1, 1) = '\\'))"
        )
        windows_root_owns = (
            f"({trailing_root} "
            f"AND substr({path_sql}, 1, length(catalog_import_path.path)) = catalog_import_path.path) "
            "OR "
        )
    return (
        "EXISTS (SELECT 1 FROM library_import_paths AS catalog_import_path "
        f"WHERE catalog_import_path.library_id = {library_id_sql} "
        f"AND {canonical_path} AND {canonical_root} AND ("
        f"{path_sql} = catalog_import_path.path OR "
        f"(catalog_import_path.path = '{separator}' AND substr({path_sql}, 1, 1) = '{separator}') OR "
        f"{windows_root_owns}"
        f"substr({path_sql}, 1, length(catalog_import_path.path) + 1) = "
        f"catalog_import_path.path || '{separator}'))"
    )


def catalog_path_is_canonical_sql(*, path_sql: str) -> str:
    """Reject persisted paths containing lexical traversal or duplicate separators."""
    separator = os.sep.replace("'", "''")
    if os.sep == "\\":
        double_separator = separator * 2
        drive_root = _windows_drive_root_sql(path_sql)
        unc_root = _windows_unc_root_sql(path_sql)
        drive_absolute = (
            f"(length({path_sql}) >= 3 "
            f"AND substr({path_sql}, 1, 1) GLOB '[A-Za-z]' "
            f"AND substr({path_sql}, 2, 2) = ':\\')"
        )
        unc_tail = f"substr({path_sql}, 3)"
        unc_path = (
            f"(substr({path_sql}, 1, 2) = '{double_separator}' "
            f"AND substr({path_sql}, 3, 1) != '{separator}' "
            f"AND instr({unc_tail}, '{separator}') > 1 "
            f"AND length({unc_tail}) > instr({unc_tail}, '{separator}'))"
        )
        duplicate_check_path = (
            f"(CASE WHEN substr({path_sql}, 1, 2) = '{double_separator}' "
            f"THEN substr({path_sql}, 3) ELSE {path_sql} END)"
        )
        return (
            f"({path_sql} IS NOT NULL AND {path_sql} != '' "
            f"AND ({drive_absolute} OR {unc_path}) "
            f"AND ({drive_root} OR {unc_root} OR substr({path_sql}, -1, 1) != '{separator}') "
            f"AND instr({duplicate_check_path}, '{double_separator}') = 0 "
            f"AND instr({path_sql}, '{separator}.{separator}') = 0 "
            f"AND instr({path_sql}, '{separator}..{separator}') = 0 "
            f"AND substr({path_sql}, -2) != '{separator}.' "
            f"AND substr({path_sql}, -3) != '{separator}..' "
            f"AND instr({path_sql}, '/') = 0)"
        )
    conditions = (
        f"({path_sql} IS NOT NULL AND {path_sql} != '' "
        f"AND substr({path_sql}, 1, 1) = '{separator}' "
        f"AND ({path_sql} = '{separator}' OR substr({path_sql}, -1, 1) != '{separator}') "
        f"AND instr({path_sql}, '{separator}{separator}') = 0 "
        f"AND instr({path_sql}, '{separator}.{separator}') = 0 "
        f"AND instr({path_sql}, '{separator}..{separator}') = 0 "
        f"AND substr({path_sql}, -2) != '{separator}.' "
        f"AND substr({path_sql}, -3) != '{separator}..')"
    )
    return conditions


def catalog_direct_child_sql(*, parent_path_sql: str, path_sql: str) -> str:
    """Require `path_sql` to be a canonical direct child of `parent_path_sql`."""
    separator = os.sep.replace("'", "''")
    canonical_path = catalog_path_is_canonical_sql(path_sql=path_sql)
    canonical_parent = catalog_path_is_canonical_sql(path_sql=parent_path_sql)
    windows_root_child = ""
    if os.sep == "\\":
        trailing_root = (
            f"({_windows_drive_root_sql(parent_path_sql)} OR "
            f"({_windows_unc_root_sql(parent_path_sql)} AND substr({parent_path_sql}, -1, 1) = '{separator}'))"
        )
        windows_root_child = (
            f"({trailing_root} "
            f"AND substr({path_sql}, 1, length({parent_path_sql})) = {parent_path_sql} "
            f"AND instr(substr({path_sql}, length({parent_path_sql}) + 1), '{separator}') = 0) OR "
        )
    return (
        f"({canonical_path} AND {canonical_parent} AND {path_sql} != {parent_path_sql} AND ("
        f"{windows_root_child}"
        f"({parent_path_sql} = '{separator}' "
        f"AND substr({path_sql}, 1, 1) = '{separator}' "
        f"AND instr(substr({path_sql}, 2), '{separator}') = 0) OR "
        f"(substr({path_sql}, 1, length({parent_path_sql}) + 1) = "
        f"{parent_path_sql} || '{separator}' "
        f"AND instr(substr({path_sql}, length({parent_path_sql}) + 2), '{separator}') = 0)))"
    )


def catalog_folder_has_active_asset_sql(*, fi_alias: str = "fi") -> str:
    """Require a registered folder row that contains at least one active asset."""
    separator = os.sep.replace("'", "''")
    folder_import_ownership = catalog_import_path_owns_sql(
        library_id_sql=f"{fi_alias}.library_id",
        path_sql=f"{fi_alias}.path",
    )
    asset_import_ownership = catalog_import_path_owns_sql(
        library_id_sql="folder_asset.library_id",
        path_sql="folder_asset.path",
    )
    windows_root_descendant = ""
    if os.sep == "\\":
        trailing_root = (
            f"({_windows_drive_root_sql(f'{fi_alias}.path')} OR "
            f"({_windows_unc_root_sql(f'{fi_alias}.path')} "
            f"AND substr({fi_alias}.path, -1, 1) = '{separator}'))"
        )
        windows_root_descendant = (
            f"({trailing_root} AND substr(folder_asset.path, 1, length({fi_alias}.path)) = {fi_alias}.path) OR "
        )
    return (
        f"({fi_alias}.library_id IS NOT NULL "
        f"AND EXISTS (SELECT 1 FROM libraries AS folder_library "
        f"WHERE folder_library.id = {fi_alias}.library_id) "
        f"AND {folder_import_ownership} "
        f"AND EXISTS (SELECT 1 FROM assets AS folder_asset "
        f"JOIN libraries AS folder_asset_library ON folder_asset_library.id = folder_asset.library_id "
        f"WHERE folder_asset.library_id = {fi_alias}.library_id "
        f"AND folder_asset.offline = 0 AND folder_asset.deleted_at IS NULL "
        f"AND {asset_import_ownership} "
        f"AND ({fi_alias}.path = '{separator}' OR "
        f"{windows_root_descendant}"
        f"substr(folder_asset.path, 1, length({fi_alias}.path) + 1) = "
        f"{fi_alias}.path || '{separator}')))"
    )


def current_file_metadata_sql(*, fi_alias: str = "fi", im_alias: str = "im") -> str:
    """Return a predicate excluding stale metadata and inactive catalog assets."""
    identity = file_index_matches_image_metadata_sql(fi_alias=fi_alias, im_alias=im_alias)
    import_ownership = catalog_import_path_owns_sql(
        library_id_sql=f"{fi_alias}.library_id",
        path_sql=f"{fi_alias}.path",
    )
    return f"({identity} AND {active_catalog_file_sql(fi_alias=fi_alias)} AND {import_ownership})"
