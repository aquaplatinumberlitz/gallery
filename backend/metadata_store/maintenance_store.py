"""Persistence for integrity check runs."""

from __future__ import annotations

import json
import sqlite3


def insert_run(conn: sqlite3.Connection, summary: dict) -> int:
    """Insert a run summary row and return the new run_id.

    summary format:
    {
        "trigger": "manual" | "daemon",
        "started_at": float_epoch,
        "finished_at": float_epoch,
        "status": "ok" | "error",
        "error": str | None,
        "issues": {5 keys: int},
        "repairs": {4 keys: int}
    }
    """
    conn.execute(
        """INSERT INTO integrity_check_runs
           (trigger, started_at, finished_at, status, error, issues_json, repairs_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            summary["trigger"],
            summary["started_at"],
            summary["finished_at"],
            summary["status"],
            summary["error"],
            json.dumps(summary["issues"]),
            json.dumps(summary["repairs"]),
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_latest_run(conn: sqlite3.Connection) -> dict | None:
    """Return the most recent run summary row as a dict, or None."""
    row = conn.execute(
        """SELECT id, trigger, started_at, finished_at, status, error, issues_json, repairs_json
           FROM integrity_check_runs
           ORDER BY finished_at DESC, id DESC
           LIMIT 1"""
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "trigger": row["trigger"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "status": row["status"],
        "error": row["error"],
        "issues": json.loads(row["issues_json"]),
        "repairs": json.loads(row["repairs_json"]),
    }
