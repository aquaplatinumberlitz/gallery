#!/usr/bin/env python3
"""Check test and debug files for standard purpose headers."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REQUIRED_FIELDS = ("Purpose:", "Guarantees:", "Run when:")
SCAN_PATTERNS = (
    "frontend/tests/**/*.spec.ts",
    "backend/tests/test_*.py",
    "backend/debug/**/*.py",
    "frontend/src/debug/**/*.ts",
)
IGNORED_PARTS = {
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    ".venv_linux",
    "test-results",
    "coverage",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_ignored(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)


def scanned_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in SCAN_PATTERNS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(path for path in files if not is_ignored(path.relative_to(root)))


def read_header(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:80])


def missing_fields(path: Path) -> list[str]:
    header = read_header(path)
    return [field for field in REQUIRED_FIELDS if field not in header]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="list files that are checked")
    parser.add_argument("--verbose", action="store_true", help="print OK lines for files with headers")
    args = parser.parse_args(argv)

    root = repo_root()
    files = scanned_files(root)

    if args.list:
        for path in files:
            print(path.relative_to(root))
        return 0

    failures: list[tuple[Path, list[str]]] = []
    for path in files:
        missing = missing_fields(path)
        if missing:
            failures.append((path, missing))
            print(
                f"WARN {path.relative_to(root)} missing header fields: {', '.join(missing)}",
                file=sys.stderr,
            )
        elif args.verbose:
            print(f"OK   {path.relative_to(root)}")

    if failures:
        print(
            "\nStandard header required in scanned test/debug files:\n  Purpose:\n  Guarantees:\n  Run when:",
            file=sys.stderr,
        )
        return 1

    print(f"check_test_docs: {len(files)} files OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
