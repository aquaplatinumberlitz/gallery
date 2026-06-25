#!/usr/bin/env python3
"""Static check: ensure no production code imports private metadata lifecycle helpers directly.

Only indexer.py and tests/ may import _persist_metadata_index_jobs,
complete_metadata_job, and related DB-only helpers from metadata_store.
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def check_import(filepath: Path, pattern: str, name: str) -> list[str]:
    errors = []
    text = filepath.read_text()
    for match in re.finditer(pattern, text, re.MULTILINE):
        errors.append(f"{filepath.relative_to(BACKEND.parent)}: imports {name} at line {text[:match.start()].count(chr(10)) + 1}")
    return errors


def main() -> int:
    errors: list[str] = []

    imports_pattern = r"from\s+backend\.metadata_store\s+import\s+[^)]*_persist_metadata_index_jobs[^)]*"

    for pyfile in sorted(BACKEND.rglob("*.py")):
        rel = pyfile.relative_to(BACKEND)
        if "tests" in rel.parts:
            continue
        if rel.name in ("__init__.py",):
            continue
        if "indexer" in str(rel):
            continue
        errors.extend(check_import(pyfile, imports_pattern, "_persist_metadata_index_jobs"))

    if errors:
        print("ERROR: Metadata lifecycle ownership violation detected:")
        for e in errors:
            print(f"  {e}")
        print("\nOnly indexer.py and tests/ may import _persist_metadata_index_jobs directly.")
        return 1
    else:
        print("OK: No metadata lifecycle ownership violations found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
