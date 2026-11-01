#!/usr/bin/env python3
"""Static check: only the database writer module opens writable SQLite connections or controls transactions.

Phase 3 of the worker lifecycle hardening plan retired the process-global ``_DB_LOCK``. Every catalog
write is now a function of a connection (an *op*) that ``backend/metadata_store/db_writer.py`` runs on
its single write connection (``run_write``) or, when no writer is active (``init_db``, migrations,
scripts, plain unit tests), in one direct ``BEGIN IMMEDIATE`` transaction that lives in the same module.

The check is heuristic (it reads the syntax tree, not the program) and enforces three rules for every
module under ``backend/`` except tests and the allowlist below:

1. **Writable connections.** No call to ``_connect(...)``, ``sqlite3.connect(...)`` or
   ``_open_default_connection(...)``. Production code reads through ``_connect_read()`` /
   ``_read_snapshot()`` (``query_only``) and writes inside ops handed a connection by the writer.
2. **Write SQL needs a connection in hand.** A string literal (plain, f-string, or ``+`` concatenation)
   containing ``INSERT INTO``, ``REPLACE INTO``, ``UPDATE <table> SET``, ``DELETE FROM``, DDL, or
   ``executescript`` may only appear inside a function that takes a connection parameter (``conn``,
   ``connection``, ``cur``, ``cursor``) - an op body or an op helper. ``BEGIN IMMEDIATE`` is transaction
   control and may not appear at all outside the allowlist.
3. **Transactions.** No ``.commit()`` / ``.rollback()`` calls outside the allowlist.

Allowlist: the writer module (which owns the no-active-writer path), ``_db.py`` (connection factories),
and the schema / migration modules that run before any writer exists.

Usage: ``python scripts/check_db_write_ownership.py [--root DIR] [--list]`` (exit 1 on violations).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWLIST = frozenset(
    {
        "metadata_store/db_writer.py",
        "metadata_store/_db.py",
        "metadata_store/_schema.py",
        "metadata_store/_schema_ddl.py",
        "metadata_store/_schema_ensure.py",
        "metadata_store/_migrations.py",
    }
)
EXCLUDED_PARTS = frozenset({"tests", "__pycache__", "node_modules"})
CONNECTION_PARAMS = frozenset({"conn", "connection", "cur", "cursor"})
CONNECT_CALLS = frozenset({"_connect", "_open_default_connection"})
TRANSACTION_CALLS = frozenset({"commit", "rollback"})

_WRITE_SQL = re.compile(
    r"\b(?:INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE\s+\S+\s+SET|DELETE\s+FROM|"
    r"ALTER\s+TABLE|DROP\s+(?:TABLE|INDEX|TRIGGER|VIEW)|CREATE\s+(?:VIRTUAL\s+)?(?:TABLE|INDEX|TRIGGER))\b"
)
_BEGIN_IMMEDIATE = re.compile(r"\bBEGIN\s+IMMEDIATE\b")


def _production_files(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_PARTS or any(part.startswith(".venv") or part == "venv" for part in parts):
            continue
        yield path


def _string_value(node: ast.AST) -> str | None:
    """Return the static text of a string expression (placeholders for dynamic parts), else ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else "{}"
            for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _string_value(node.left), _string_value(node.right)
        if left is None and right is None:
            return None
        return (left if left is not None else "{}") + (right if right is not None else "{}")
    return None


def _docstring_nodes(tree: ast.AST) -> set[int]:
    docs: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    return docs


def _call_name(node: ast.Call) -> tuple[str | None, str | None]:
    """Return ``(owner, name)`` of a call: ``sqlite3.connect`` -> ``("sqlite3", "connect")``."""
    func = node.func
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        owner = func.value.id if isinstance(func.value, ast.Name) else None
        return owner, func.attr
    return None, None


def check_source(source: str, rel: str) -> list[str]:
    """Return the violations of one module (``rel`` is its path relative to ``backend/``)."""
    if rel in ALLOWLIST:
        return []
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    errors: list[str] = []

    def has_connection(stack: list[ast.AST]) -> bool:
        for fn in stack:
            args = fn.args  # type: ignore[attr-defined]
            names = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
            if names & CONNECTION_PARAMS:
                return True
        return False

    def visit(node: ast.AST, stack: list[ast.AST], in_concat: bool) -> None:
        is_function = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        if is_function:
            stack = [*stack, node]
        if isinstance(node, ast.Call):
            owner, name = _call_name(node)
            if name in CONNECT_CALLS or (owner == "sqlite3" and name == "connect"):
                errors.append(f"{rel}:{node.lineno} opens a writable connection ({name}); read with _connect_read()")
            elif name in TRANSACTION_CALLS and isinstance(node.func, ast.Attribute):
                errors.append(f"{rel}:{node.lineno} controls a transaction (.{name}()) outside the database writer")
            elif name == "executescript":
                errors.append(f"{rel}:{node.lineno} runs executescript outside the schema modules")
        text = None
        is_string = isinstance(node, (ast.Constant, ast.JoinedStr)) or (
            isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
        )
        if is_string and not in_concat and id(node) not in docstrings:
            text = _string_value(node)
        if text is not None:
            if _BEGIN_IMMEDIATE.search(text):
                errors.append(f"{rel}:{node.lineno} contains BEGIN IMMEDIATE (transaction control belongs to the writer)")
            elif _WRITE_SQL.search(text) and not has_connection(stack):
                errors.append(f"{rel}:{node.lineno} contains write SQL outside a function that takes a connection")
        child_in_concat = in_concat or (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and text is not None)
        for child in ast.iter_child_nodes(node):
            visit(child, stack, child_in_concat or isinstance(node, ast.JoinedStr))

    visit(tree, [], False)
    return errors


def check_tree(root: Path) -> list[str]:
    errors: list[str] = []
    for path in _production_files(root):
        errors.extend(check_source(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix()))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT / "backend", help="package root to scan")
    args = parser.parse_args(argv)
    errors = check_tree(args.root)
    for error in errors:
        print(error)
    if errors:
        print(f"FAIL: {len(errors)} database write ownership violation(s)")
        return 1
    print("OK: no database write ownership violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
