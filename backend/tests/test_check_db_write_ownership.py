"""Phase 3 regression: the static database write ownership check.

Purpose:
Pin ``scripts/check_db_write_ownership.py``, the lint rule that keeps every SQLite write behind the database
writer after ``_DB_LOCK`` was retired: production code outside the writer module and the schema/migration
modules must not open writable connections, begin or end transactions, or run write SQL outside a function
that was handed a connection.

Guarantees:
The real ``backend/`` tree passes; planted violations are flagged (writable connection helpers,
``sqlite3.connect``, ``from sqlite3 import connect``, ``.commit()``/``.rollback()``, ``BEGIN IMMEDIATE`` and bare
transaction statements, ``executescript``, write SQL in plain strings, f-strings and ``+`` concatenations, DDL);
allowed shapes pass (write SQL inside an op that takes a connection, read SQL anywhere, docstrings that mention
SQL, an upper-case dictionary key named like a statement, the allowlisted modules); the command line exits 1
with the offending ``file:line`` for a violating tree and 0 for a clean one, and ``./test.sh lint`` runs it.

Run when:
Changing ``scripts/check_db_write_ownership.py``, its allowlist, or the way production code reaches SQLite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_db_write_ownership.py"


@pytest.fixture(scope="module")
def ownership():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import check_db_write_ownership as module
    finally:
        sys.path.pop(0)
    return module


def _flags(ownership, source: str, rel: str = "feature.py") -> list[str]:
    return ownership.check_source(source, rel)


# ---------------------------------------------------------------------------
# The real tree
# ---------------------------------------------------------------------------


def test_the_production_tree_passes_the_check(ownership) -> None:
    assert ownership.check_tree(REPO_ROOT / "backend") == []


def test_the_check_is_part_of_the_lint_command() -> None:
    script = (REPO_ROOT / "test.sh").read_text(encoding="utf-8")
    start = script.index("run_lint()")
    lint = script[start : script.index("\n}\n", start)]
    assert "scripts/check_db_write_ownership.py" in lint


# ---------------------------------------------------------------------------
# Positive fixtures: planted violations are flagged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "source"),
    [
        (
            "writable connection helper",
            "from .metadata_store import _connect\n\ndef f():\n    with _connect() as conn:\n        conn.execute('SELECT 1')\n",
        ),
        ("sqlite3.connect", "import sqlite3\n\ndef f():\n    return sqlite3.connect('x.db')\n"),
        ("from sqlite3 import connect", "from sqlite3 import connect\n"),
        ("opening the writer's connection", "def f():\n    return _open_default_connection()\n"),
        ("commit", "def f(conn):\n    conn.execute('SELECT 1')\n    conn.commit()\n"),
        ("rollback", "def f(conn):\n    conn.rollback()\n"),
        ("BEGIN IMMEDIATE", "def f(conn):\n    conn.execute('BEGIN IMMEDIATE')\n"),
        ("lower-case begin immediate", "def f(conn):\n    conn.execute('begin immediate')\n"),
        ("bare BEGIN", "def f(conn):\n    conn.execute('BEGIN')\n"),
        ("bare COMMIT statement", "def f(conn):\n    conn.execute('COMMIT')\n"),
        ("executescript", "def f(conn):\n    conn.executescript('SELECT 1;')\n"),
        ("insert outside an op", "def f():\n    return 'INSERT INTO assets (path) VALUES (?)'\n"),
        ("update outside an op", "SQL = 'UPDATE assets SET offline = 1 WHERE id = ?'\n"),
        ("delete outside an op", "def f():\n    return 'DELETE FROM assets WHERE id = ?'\n"),
        ("replace into", "def f():\n    return 'REPLACE INTO assets (path) VALUES (?)'\n"),
        ("insert or ignore", "def f():\n    return 'INSERT OR IGNORE INTO assets (path) VALUES (?)'\n"),
        ("ddl", "def f():\n    return 'CREATE INDEX idx_x ON assets (path)'\n"),
        ("f-string insert", "def f(table):\n    return f'INSERT INTO {table} (a) VALUES (?)'\n"),
        ("f-string update", "def f(table):\n    return f'UPDATE {table} SET a = ?'\n"),
        ("concatenated delete", "def f(table):\n    return 'DELETE ' + 'FROM ' + table\n"),
        (
            "concatenated insert with a dynamic table",
            "def f(table):\n    return 'INSERT INTO ' + table + ' (a) VALUES (?)'\n",
        ),
        (
            "write sql in a function without a connection",
            "def helper(path):\n    return 'UPDATE assets SET offline = 1 WHERE path = ?'\n",
        ),
    ],
)
def test_planted_violations_are_flagged(ownership, label: str, source: str) -> None:
    errors = _flags(ownership, source)
    assert errors, f"{label}: nothing was flagged"
    assert all(error.startswith("feature.py:") for error in errors), errors


def test_a_violation_names_file_and_line(ownership) -> None:
    errors = _flags(ownership, "x = 1\n\n\ndef f():\n    return sqlite3.connect('x')\n", rel="pkg/mod.py")
    assert errors == ["pkg/mod.py:5 opens a writable connection (connect); read with _connect_read()"]


# ---------------------------------------------------------------------------
# Negative fixtures: allowed shapes pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("write sql inside an op", "def op(conn):\n    conn.execute('INSERT INTO assets (path) VALUES (?)', ('a',))\n"),
        (
            "write sql inside a nested op closure",
            "def store(path):\n    def op(conn):\n        conn.execute('DELETE FROM assets WHERE path = ?', (path,))\n    return run_write(op)\n",
        ),
        (
            "write sql through a cursor parameter",
            "def op(cur):\n    cur.execute('UPDATE assets SET offline = 1 WHERE id = ?', (1,))\n",
        ),
        (
            "f-string write sql inside an op",
            "def op(conn, table):\n    conn.execute(f'DELETE FROM {table} WHERE id = ?', (1,))\n",
        ),
        ("write sql in a lambda op", "OP = lambda conn: conn.execute('DELETE FROM assets')\n"),
        (
            "read through the read connection",
            "def f():\n    with _connect_read() as conn:\n        return conn.execute('SELECT * FROM assets').fetchall()\n",
        ),
        (
            "read through a snapshot",
            "def f():\n    with _read_snapshot() as snap:\n        return snap.execute('SELECT 1').fetchone()\n",
        ),
        (
            "docstring mentioning sql",
            'def f():\n    """Runs INSERT INTO assets and BEGIN IMMEDIATE for the caller."""\n    return 1\n',
        ),
        ("module docstring mentioning sql", '"""DELETE FROM assets is forbidden here."""\n'),
        ("dictionary key named like a statement", "def f():\n    return {'commit': 'abc', 'end': 1}\n"),
        ("savepoint inside an op", "def op(conn):\n    conn.execute('SAVEPOINT x')\n    conn.execute('RELEASE x')\n"),
        ("a method named connect on another object", "def f(client):\n    return client.connect()\n"),
    ],
)
def test_allowed_shapes_pass(ownership, label: str, source: str) -> None:
    assert _flags(ownership, source) == [], label


@pytest.mark.parametrize(
    "rel",
    [
        "metadata_store/db_writer.py",
        "metadata_store/_db.py",
        "metadata_store/_schema.py",
        "metadata_store/_schema_ddl.py",
        "metadata_store/_schema_ensure.py",
        "metadata_store/_migrations.py",
    ],
)
def test_the_allowlisted_modules_may_own_transactions(ownership, rel: str) -> None:
    source = "def f():\n    conn = sqlite3.connect('x')\n    conn.execute('BEGIN IMMEDIATE')\n    conn.commit()\n"
    assert _flags(ownership, source, rel=rel) == []
    assert ownership.check_source(source, "metadata_store/other.py")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_command_exits_one_with_file_and_line_for_a_violating_tree(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "bad.py").write_text("import sqlite3\n\n\ndef f():\n    return sqlite3.connect('x')\n", encoding="utf-8")
    (package / "good.py").write_text("def op(conn):\n    conn.execute('DELETE FROM assets')\n", encoding="utf-8")
    tests_dir = package / "tests"
    tests_dir.mkdir()
    (tests_dir / "ignored.py").write_text("import sqlite3\nsqlite3.connect('x').commit()\n", encoding="utf-8")

    result = _run(package)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "bad.py:5" in result.stdout
    assert "good.py" not in result.stdout and "ignored.py" not in result.stdout
    assert "FAIL: 1 database write ownership violation" in result.stdout


def test_the_command_exits_zero_for_a_clean_tree_and_for_the_repository() -> None:
    assert _run(REPO_ROOT / "backend").returncode == 0
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("OK:")
