"""Runtime counters: O(1) status counts maintained by SQLite triggers.

The status builds used to count ``metadata_index_jobs`` states and sum ``asset_derivatives.byte_size`` with
full aggregate queries on every poll. ``runtime_counters`` (``name``, ``value``) holds those numbers instead:

* ``metadata_jobs.<state>`` for the six metadata job states, and
* ``derivative_ready_bytes``: the sum of ``byte_size`` over ``ready`` derivatives.

Maintenance is done by triggers (see ``_schema_ddl.RUNTIME_COUNTERS_STATEMENTS``) rather than by the writer
ops that change the counted states. The counted rows are changed from dozens of places (the writer ops, the
flag-off direct transactions, recovery, the integrity checker, destructive maintenance, migrations, tests'
raw SQL), and a trigger is part of the very statement that changes the row, so it is correct for all of them
and rolls back with them. A counter can only drift through something that bypasses triggers (for example
``INSERT OR REPLACE`` with recursive triggers off, or a database written by an older release), so
``verify_runtime_counters`` recomputes them from the source tables; the integrity pass repairs any drift and
the additive schema ensure backfills a database that predates the table.

Readers use ``metadata_job_state_counts`` and ``derivative_ready_bytes``. They fall back to the aggregate
query when a counter is missing or negative, so a damaged table can never make a status response wrong.
"""

from __future__ import annotations

import sqlite3

from ._schema_ddl import RUNTIME_COUNTER_METADATA_STATES, RUNTIME_COUNTER_NAMES

METADATA_STATES = RUNTIME_COUNTER_METADATA_STATES
COUNTER_NAMES = RUNTIME_COUNTER_NAMES
READY_BYTES_COUNTER = "derivative_ready_bytes"


def metadata_counter_name(state: str) -> str:
    """Return the counter name of one metadata job state."""
    return f"metadata_jobs.{state}"


def read_counters(conn: sqlite3.Connection) -> dict[str, int]:
    """Return every stored counter (empty when the table does not exist yet)."""
    try:
        return {str(row[0]): int(row[1]) for row in conn.execute("SELECT name, value FROM runtime_counters")}
    except sqlite3.OperationalError:
        return {}


def compute_counters(conn: sqlite3.Connection) -> dict[str, int]:
    """Return the counters recomputed from the source tables (the definition of a correct value)."""
    states = dict.fromkeys(METADATA_STATES, 0)
    for state, count in conn.execute("SELECT state, count(*) FROM metadata_index_jobs GROUP BY state"):
        if state in states:
            states[str(state)] = int(count)
    ready_bytes = conn.execute(
        "SELECT COALESCE(sum(byte_size), 0) FROM asset_derivatives WHERE status = 'ready'"
    ).fetchone()[0]
    return {
        **{metadata_counter_name(state): count for state, count in states.items()},
        READY_BYTES_COUNTER: int(ready_bytes),
    }


def metadata_job_state_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return the number of metadata jobs per state (all six states), from the counters when they are usable."""
    stored = read_counters(conn)
    names = [metadata_counter_name(state) for state in METADATA_STATES]
    if all(stored.get(name, -1) >= 0 for name in names):
        return {state: stored[metadata_counter_name(state)] for state in METADATA_STATES}
    computed = compute_counters(conn)
    return {state: computed[metadata_counter_name(state)] for state in METADATA_STATES}


def derivative_ready_bytes(conn: sqlite3.Connection) -> int:
    """Return the bytes held by ``ready`` derivatives, from the counter when it is usable."""
    stored = read_counters(conn).get(READY_BYTES_COUNTER, -1)
    if stored >= 0:
        return stored
    return compute_counters(conn)[READY_BYTES_COUNTER]


def verify_runtime_counters(conn: sqlite3.Connection, *, repair: bool = False) -> dict[str, tuple[int | None, int]]:
    """Compare stored counters with their recomputed values; return ``{name: (stored, actual)}`` for each drift.

    A missing counter row is a drift (``stored`` is ``None``). With ``repair`` the correct values are written;
    the caller must then own a write transaction so no writer can change the counted rows between the
    recomputation and the repair.
    """
    actual = compute_counters(conn)
    stored = read_counters(conn)
    drift = {name: (stored.get(name), value) for name, value in actual.items() if stored.get(name) != value}
    if repair and drift:
        conn.executemany(
            "INSERT INTO runtime_counters(name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            [(name, value) for name, (_stored, value) in drift.items()],
        )
    return drift
