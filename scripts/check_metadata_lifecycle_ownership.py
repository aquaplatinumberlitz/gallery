#!/usr/bin/env python3
"""Static check: ensure no production code imports private metadata lifecycle helpers directly.

Only indexer.py and tests/ may import lifecycle-owned helpers (``_persist_metadata_index_jobs``,
``complete_metadata_job``, ``mark_metadata_job_stale``, etc.) from ``metadata_store``.

Catches:
- Absolute imports: ``from backend.metadata_store import _persist_metadata_index_jobs``
- Relative imports: ``from .metadata_store import _persist_metadata_index_jobs``
- Old public name: ``queue_metadata_index_paths`` (removed, now private)
- Direct usage of lifecycle-owned symbols outside lifecycle owner
"""

import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"

# Symbols owned by the metadata lifecycle owner (indexer.py)
# Only indexer.py and tests/ should import these directly.
LIFECYCLE_SYMBOLS = (
    "_persist_metadata_index_jobs",
    "complete_metadata_job",
    "mark_metadata_job_stale",
    "claim_next_metadata_job",
    "fail_metadata_job",
    "list_recoverable_metadata_jobs",
    "reset_running_jobs_to_queued",
    "repair_inconsistent_asset_states",
)

# Old public names that must NOT be imported (removed/alised in Phase 5)
BANNED_SYMBOLS = ("queue_metadata_index_paths",)

# Legacy runtime-queue symbols that must NOT exist in production code
BANNED_LEGACY_SYMBOLS = (
    "_job_queue",
    "_process_batch",
    "_enqueue_metadata_jobs_from_result",
)


def check_file(filepath: Path, rel: Path) -> list[str]:
    """Run all checks against one file, returning any errors found."""
    errors: list[str] = []
    text = filepath.read_text()

    line_num = 1
    for line in text.split("\n"):
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            line_num += 1
            continue

        # Check for banned legacy symbols as direct attribute access
        for sym in BANNED_LEGACY_SYMBOLS:
            if (
                f".{sym}" in stripped
                or stripped.startswith(f"{sym} ")
                or re.match(rf"def\s+{re.escape(sym)}\s*\(", stripped)
                or re.match(rf"{re.escape(sym)}\s*[:=]", stripped)
            ):
                errors.append(f"{rel}:{line_num} references banned legacy symbol '{sym}'")

        line_num += 1

    # Check imports with regex (both absolute and relative)
    for sym in LIFECYCLE_SYMBOLS:
        # from backend.metadata_store import ..., sym, ...
        if re.search(rf"from\s+backend\.metadata_store\s+import\s+[^)]*\b{re.escape(sym)}\b", text):
            errors.append(f"{rel}: imports lifecycle-owned '{sym}'")

        # from .metadata_store import ..., sym, ...
        if re.search(rf"from\s+\.metadata_store\s+import\s+[^)]*\b{re.escape(sym)}\b", text):
            errors.append(f"{rel}: imports lifecycle-owned '{sym}' (relative)")

        # Direct metadata_store.{sym} usage
        for match in re.finditer(rf"metadata_store\.{re.escape(sym)}\b", text):
            err_line = text[: match.start()].count("\n") + 1
            errors.append(f"{rel}:{err_line} uses 'metadata_store.{sym}' directly")

    # Check for banned old public names
    for sym in BANNED_SYMBOLS:
        if re.search(rf"from\s+(backend|\.)metadata_store\s+import\s+[^)]*\b{re.escape(sym)}\b", text):
            errors.append(f"{rel}: imports banned old public name '{sym}'")

        # Direct metadata_store.{banned_symbol} usage
        for match in re.finditer(rf"metadata_store\.{re.escape(sym)}\b", text):
            err_line = text[: match.start()].count("\n") + 1
            errors.append(f"{rel}:{err_line} uses banned old public name 'metadata_store.{sym}'")

    return errors


def main() -> int:
    errors: list[str] = []
    excluded_dirs = {"tests", "__pycache__"}
    excluded_files = {"__init__.py"}

    for pyfile in sorted(BACKEND.rglob("*.py")):
        rel = pyfile.relative_to(BACKEND)

        if any(p in excluded_dirs for p in rel.parts):
            continue
        if rel.name in excluded_files:
            continue
        if "indexer" in str(rel):
            continue  # lifecycle owner is exempt

        errors.extend(check_file(pyfile, rel))

    if errors:
        print("ERROR: Metadata lifecycle ownership violations detected:\n")
        for e in sorted(set(errors)):
            print(f"  - {e}")
        print("\nOnly indexer.py and tests/ may import lifecycle-owned symbols.")
        return 1
    else:
        print("OK: No metadata lifecycle ownership violations found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
