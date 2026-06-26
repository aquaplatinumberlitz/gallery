"""Shared identity matching helpers for tolerant mtime_ns comparison.

Gallery's identity rule for matching a file across tables is:

    path + size + tolerant mtime_ns

The tolerance accounts for filesystem timestamp aliasing / precision loss
across reads. For rows that store mtime in seconds only (legacy), a seconds
bridge falls back to mtime comparison with 1 ms tolerance.

All functions return a self-contained SQL boolean expression wrapped in
parentheses (no trailing ``AND``) that can be embedded in ``JOIN … ON
<expr>``, ``WHERE EXISTS (… WHERE <expr>)``, etc.  :data:`path` and
:data:`size` equality is **not** included — callers add those as needed.

Notes
-----
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

MTIME_NS_TOLERANCE = 1000
"""Nanosecond tolerance for mtime_ns comparison (1000 ns = 1 µs)."""

MTIME_SEC_TOLERANCE = 1e-3
"""Second tolerance for legacy mtime comparison (0.001 s = 1 ms)."""
_NANOS_PER_SEC: float = 1_000_000_000.0


def asset_matches_image_metadata_sql(*, asset_alias: str = "a", im_alias: str = "im") -> str:
    """Return SQL fragment matching an asset row to an image_metadata row.

    Two branches (assets has no ``mtime`` column):

    1. both sides have ``mtime_ns`` → ns tolerance match.
    2. ``image_metadata.mtime_ns`` is NULL → convert ``assets.mtime_ns`` to
       seconds and compare with ``image_metadata.mtime``.
    """
    return (
        f"(({im_alias}.mtime_ns IS NOT NULL AND {asset_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({im_alias}.mtime_ns - {asset_alias}.mtime_ns) < {MTIME_NS_TOLERANCE})"
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
        f"AND ABS({job_alias}.mtime_ns - {asset_alias}.mtime_ns) < {MTIME_NS_TOLERANCE})"
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
        f"(? IS NOT NULL AND mtime_ns IS NOT NULL AND ABS(mtime_ns - ?) < {MTIME_NS_TOLERANCE})"
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
        f"(? IS NOT NULL AND mtime_ns IS NOT NULL AND ABS(mtime_ns - ?) < {MTIME_NS_TOLERANCE})"
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
        f"AND ABS({im_alias}.mtime_ns - {job_alias}.mtime_ns) < {MTIME_NS_TOLERANCE})"
        f" OR ({job_alias}.mtime_ns IS NULL AND {im_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({im_alias}.mtime_ns / {_NANOS_PER_SEC} - {job_alias}.mtime) < {MTIME_SEC_TOLERANCE})"
        f" OR ({im_alias}.mtime_ns IS NULL AND {job_alias}.mtime_ns IS NOT NULL "
        f"AND ABS({job_alias}.mtime_ns / {_NANOS_PER_SEC} - {im_alias}.mtime) < {MTIME_SEC_TOLERANCE}))"
    )
