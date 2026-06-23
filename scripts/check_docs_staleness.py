"""Check docs for stale patterns after refactoring."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Patterns that should NOT appear in non-archived docs
BAD_PATTERNS: dict[str, str] = {
    "metadata_store.py": (
        "metadata_store is now a package (backend/metadata_store/), "
        "not a single file"
    ),
    "Backend modules live flat in `backend/`": (
        "backend now has domain packages (metadata_store/)"
    ),
    "Backend modules live flat in backend/": (
        "backend now has domain packages (metadata_store/)"
    ),
}

DOC_FILES = [
    p
    for p in REPO_ROOT.rglob("*.md")
    if "archived" not in p.parts
    and "node_modules" not in p.parts
    and ".venv" not in p.parts
    and ".hermes" not in p.parts
]


def main() -> int:
    """Scan non-archived docs for stale patterns and report violations."""
    failed = False
    for doc in sorted(DOC_FILES):
        try:
            text = doc.read_text(encoding="utf-8")
        except Exception:
            continue
        for pattern, reason in BAD_PATTERNS.items():
            if pattern in text:
                rel = doc.relative_to(REPO_ROOT)
                print(f"STALE [{rel}]: found {pattern!r} — {reason}")
                failed = True

    if failed:
        print("\nFix the stale patterns above before marking docs as reviewed.")
        return 1
    print("Docs staleness check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
