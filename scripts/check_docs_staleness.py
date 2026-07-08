"""Check docs for stale patterns after refactoring."""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Patterns that should NOT appear in non-archived docs (string match)
BAD_STRINGS: dict[str, str] = {
    "metadata_store.py": "metadata_store is now a package (backend/metadata_store/), not a single file",
    "Backend modules live flat in `backend`": "backend now has domain packages (metadata_store/)",
    "Backend modules live flat in backend/": "backend now has domain packages (metadata_store/)",
}

# Regex patterns that should NOT appear in non-archived README docs
BAD_README_REGEX: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\d+ tests across \d+ files"), "test counts are generated; point to test-gap-report.md instead"),
    (
        re.compile(r"\d+ Vitest tests across \d+ files"),
        "test counts are generated; point to test-gap-report.md instead",
    ),
]

DOC_FILES = [
    p
    for p in REPO_ROOT.rglob("*.md")
    if "node_modules" not in p.parts and ".venv" not in p.parts and ".hermes" not in p.parts
]


def check_plans_staleness(doc: Path) -> list[str]:
    """Check docs/plans/ files for archive/migration-complete banners."""
    rel = doc.relative_to(REPO_ROOT)
    parts = doc.parts
    if "plans" not in parts or "archived" in parts:
        return []
    # Only check files under docs/plans/
    if "docs" not in parts or not any(p == "plans" for p in parts):
        return []
    errors: list[str] = []
    text = doc.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if "Archived —" in stripped or stripped.startswith("Archived —"):
            errors.append(
                f"STALE [{rel}]: docs/plans/ file contains 'Archived —' — completed plans belong in docs/archived/"
            )
        if "Migration complete" in stripped:
            errors.append(
                f"STALE [{rel}]: docs/plans/ file contains 'Migration complete' — "
                "completed plans belong in docs/archived/"
            )
        if "Status: Completed" in stripped:
            errors.append(
                f"STALE [{rel}]: docs/plans/ file has 'Status: Completed' — completed plans belong in docs/archived/"
            )
        if stripped.lower().startswith("status:") and "completed" in stripped.lower():
            errors.append(
                f"STALE [{rel}]: docs/plans/ file has completed status — completed plans belong in docs/archived/"
            )
    return errors


def check_vue_sonner_in_thirparty() -> list[str]:
    """Check that THIRD_PARTY_LIBRARIES.md mentions vue-sonner if package.json has it."""
    pkg_json = REPO_ROOT / "frontend" / "package.json"
    if not pkg_json.exists():
        return []
    pkg_text = pkg_json.read_text(encoding="utf-8")
    if '"vue-sonner"' not in pkg_text:
        return []
    thirparty = REPO_ROOT / "docs" / "THIRD_PARTY_LIBRARIES.md"
    if not thirparty.exists():
        return ["STALE: vue-sonner is in frontend/package.json but docs/THIRD_PARTY_LIBRARIES.md is missing"]
    thirparty_text = thirparty.read_text(encoding="utf-8")
    if "vue-sonner" not in thirparty_text:
        return [
            "STALE [docs/THIRD_PARTY_LIBRARIES.md]: vue-sonner is in frontend/package.json "
            "but not documented in THIRD_PARTY_LIBRARIES.md"
        ]
    return []


def check_agents_handoff() -> list[str]:
    """Check that root AGENTS.md keeps the AI handoff guardrails discoverable."""
    agents = REPO_ROOT / "AGENTS.md"
    if not agents.exists():
        return ["STALE: root AGENTS.md is missing; AI agent handoff guardrails must stay discoverable"]

    text = agents.read_text(encoding="utf-8")
    normalized_text = " ".join(text.split())
    required_patterns: list[tuple[str, str]] = [
        ("## Reading Order", "must define a reading order"),
        ("docs/archived/", "must warn that archived docs are historical"),
        ("docs/research/", "must warn that research docs are historical/contextual"),
        ("./test.sh docs", "must include the docs validation command"),
        ("./test.sh lint", "must include the lint validation command"),
        ("Never revert user changes", "must protect unrelated user work"),
        ("Backend is FastAPI with SQLite", "must state backend/runtime ownership"),
        ("Frontend server state belongs in TanStack Query", "must state frontend state ownership"),
        ("Pinia owns UI/navigation state", "must state frontend UI state ownership"),
    ]
    errors: list[str] = []
    for pattern, reason in required_patterns:
        if pattern not in normalized_text:
            errors.append(f"STALE [AGENTS.md]: missing {pattern!r} - {reason}")
    return errors


def main() -> int:
    """Scan docs for stale patterns and report violations."""
    failed = False

    for doc in sorted(DOC_FILES):
        if "archived" in doc.parts:
            continue
        try:
            text = doc.read_text(encoding="utf-8")
        except Exception:
            continue

        rel = doc.relative_to(REPO_ROOT)

        # Check string patterns
        for pattern, reason in BAD_STRINGS.items():
            if pattern in text:
                print(f"STALE [{rel}]: found {pattern!r} — {reason}")
                failed = True

        # Check regex patterns in README files
        if doc.name.lower() == "readme.md":
            for regex, reason in BAD_README_REGEX:
                if regex.search(text):
                    print(f"STALE [{rel}]: matched {regex.pattern!r} — {reason}")
                    failed = True

    # Check docs/plans/ files (even if archived/)
    for doc in sorted(DOC_FILES):
        errors = check_plans_staleness(doc)
        for err in errors:
            print(err)
            failed = True

    # Check vue-sonner presence in THIRD_PARTY_LIBRARIES.md
    for err in check_vue_sonner_in_thirparty():
        print(err)
        failed = True

    # Check root AI-agent handoff guardrails.
    for err in check_agents_handoff():
        print(err)
        failed = True

    if failed:
        print("\nFix the stale patterns above before marking docs as reviewed.")
        return 1
    print("Docs staleness check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
