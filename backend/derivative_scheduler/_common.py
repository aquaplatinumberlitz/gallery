"""Shared constants and helpers for the derivative scheduler modules."""

from __future__ import annotations

import logging
import sqlite3

from ..config import DERIVATIVE_JOB_LEASE_SECONDS, DERIVATIVE_VARIANTS
from ..metadata_store import _connect, initialize_database

# Keep the historical logger name so existing log filters and caplog targets keep matching.
logger = logging.getLogger("backend.derivative_scheduler")
_SUPERVISOR_INTERVAL_SECONDS = 30
_MAX_ATTEMPTS = 3
_CAPACITY_DEFERRED_AUTOMATIC_REASONS = frozenset({"periodic", "catalog_scan", "catalog_rebuild", "metadata_completion"})


def _lease_days() -> float:
    """Return the configured job lease duration expressed in Julian days."""
    return float(DERIVATIVE_JOB_LEASE_SECONDS) / 86400.0


def _ensure_database() -> None:
    """Initialize only when the derivative schema is not already present."""
    try:
        with _connect() as conn:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'derivative_jobs'"
            ).fetchone()
        if version >= 5 and table is not None:
            return
    except sqlite3.Error:
        pass
    initialize_database()


def derivative_variant(kind: str, max_long_edge: int, quality: int, format: str) -> str:
    """Return a stable variant name for derivative rendering settings."""
    for variant in DERIVATIVE_VARIANTS.get(kind, []):
        if format == "webp" and variant["max_long_edge"] == max_long_edge and variant["quality"] == quality:
            return str(variant["name"])
    return f"edge-{max_long_edge}-q-{quality}-{format}"
