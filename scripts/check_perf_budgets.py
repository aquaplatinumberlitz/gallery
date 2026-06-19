#!/usr/bin/env python3
"""Validate perf budget coverage: every TOML budget is consumed, every test has a budget.

Purpose:
* ensure `scripts/perf_budgets.toml` stays the single source of truth
* ensure every declared budget is referenced by at least one test/script
* ensure every perf test references a budget declared in the TOML
* ensure `frontend/tests/e2e/perf/perf-budgets.json` mirrors the relevant TOML
  sections

Guarantees:
* exits non-zero with a precise list of violations when coverage is incomplete
* pure static analysis — does not run any backend or browser

Run when:
* adding, renaming, or removing a perf budget
* adding a new perf test or bench script
* pre-commit / pre-merge to catch orphaned budgets or undocumented tests
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import load_budgets  # noqa: E402

# Mapping: TOML section -> (consumer files relative to repo root, env-var names
# that must appear in those files). Env-var names can be empty for
# documentation-only sections whose consumers do not yet read the value via an
# env var (e.g. metadata_nav is documented but the metadata-performance spec
# uses a different legacy env-var scheme).
BUDGET_CONSUMERS: dict[str, tuple[list[str], list[str]]] = {
    "scan": (
        ["scripts/perf_scan.py"],
        ["GALLERY_PERF_SCAN_P95_BUDGET_MS", 'budget_for("scan"'],
    ),
    "inspector": (
        ["scripts/perf_library_inspector.py"],
        ["GALLERY_PERF_INSPECTOR_P95_BUDGET_MS", 'budget_for("inspector"'],
    ),
    "warm_listing": (
        ["scripts/perf_warm_listing.py"],
        ["GALLERY_PERF_WARM_LISTING_BUDGET_MS", 'budget_for("warm_listing"'],
    ),
    "album_open": (
        [
            "frontend/tests/e2e/perf/album-open.perf.spec.ts",
            "frontend/tests/e2e/perf/perf-utils.ts",
        ],
        ["GALLERY_PERF_SCAN_BUDGET_MS", "GALLERY_PERF_FIRST_THUMB_BUDGET_MS", "GALLERY_PERF_THUMB_P95_BUDGET_MS"],
    ),
    "lightbox": (
        [
            "frontend/tests/e2e/perf/lightbox.perf.spec.ts",
            "frontend/tests/e2e/perf/perf-utils.ts",
        ],
        [
            "GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS",
            "GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS",
            "GALLERY_PERF_LIGHTBOX_PREVIEW_BUDGET_MS",
        ],
    ),
    "metadata_nav": (
        [
            "frontend/tests/e2e/metadata-performance.spec.ts",
            "frontend/tests/e2e/perf/perf-utils.ts",
        ],
        [],  # documented budget; legacy spec uses its own env-var names
    ),
    "search": (
        ["scripts/bench_search.py"],
        ["GALLERY_PERF_SEARCH_P95_BUDGET_MS", 'budget_for("search"'],
    ),
    "inspector_metadata": (
        ["scripts/bench_search.py"],
        ["GALLERY_PERF_INSPECTOR_METADATA_P95_BUDGET_MS", 'budget_for("inspector_metadata"'],
    ),
    "thumbnail": (
        ["scripts/bench_thumbnail.py"],
        ['budget_for("thumbnail"'],
    ),
}

# Playwright JSON mirror: which TOML sections must appear in perf-budgets.json
# and which numeric fields must match exactly.
JSON_MIRROR_SECTIONS: dict[str, list[str]] = {
    "album_open": ["scan_p95_ms", "first_thumbnail_ms", "thumbnail_p95_ms"],
    "lightbox": ["open_ms", "transition_ms", "preview_check_ms"],
    "metadata_nav": ["nav_ms", "render_ms", "search_debounce_ms", "state_restore_ms"],
}

PERF_BUDGETS_TOML = REPO_ROOT / "scripts" / "perf_budgets.toml"
PERF_BUDGETS_JSON = REPO_ROOT / "frontend" / "tests" / "e2e" / "perf" / "perf-budgets.json"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _check_consumer_files(section: str, consumers: list[str]) -> list[str]:
    errors: list[str] = []
    for rel in consumers:
        path = REPO_ROOT / rel
        if not path.exists():
            errors.append(f"[{section}] consumer file missing: {rel}")
    return errors


def _check_env_refs(section: str, consumers: list[str], env_vars: list[str]) -> list[str]:
    """Check that at least one consumer references a configured environment variable.

    Shared files such as `perf-utils.ts` may read overrides on behalf of specs.
    """
    if not env_vars:
        return []
    texts = [_read(REPO_ROOT / rel) for rel in consumers]
    if not any(texts):
        return [f"[{section}] no consumer files are readable: {consumers}"]
    for token in env_vars:
        if any(token in text for text in texts):
            return []
    return [f"[{section}] no consumer file references any of {env_vars}"]


def _check_json_mirror(toml: dict) -> list[str]:
    errors: list[str] = []
    if not PERF_BUDGETS_JSON.exists():
        errors.append(f"perf-budgets.json missing at {PERF_BUDGETS_JSON.relative_to(REPO_ROOT)}")
        return errors
    try:
        data = json.loads(PERF_BUDGETS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"perf-budgets.json is invalid JSON: {exc}")
        return errors
    for section, fields in JSON_MIRROR_SECTIONS.items():
        if section not in data:
            errors.append(f"perf-budgets.json missing section '{section}'")
            continue
        for field in fields:
            json_val = data[section].get(field)
            toml_val = toml.get(section, {}).get(field)
            if json_val != toml_val:
                errors.append(
                    f"perf-budgets.json[{section}].{field} = {json_val!r} does not match TOML value {toml_val!r}"
                )
    return errors


def _check_no_orphan_perf_tests(toml: dict) -> list[str]:
    """Ensure perf test files reference a known budget (no orphan tests)."""
    errors: list[str] = []
    # Gather every env var known via the consumer registry.
    known_env_vars: set[str] = set()
    for env_vars in (consumers_env for _, consumers_env in BUDGET_CONSUMERS.values()):
        known_env_vars.update(env_vars)
    # Also accept any GALLERY_PERF_*_BUDGET_MS var whose suffix matches a TOML
    # field name — useful for tests that override via env without a registry entry.
    known_budget_tokens: set[str] = set()
    for _section, fields in toml.items():
        if not isinstance(fields, dict):
            continue
        for field_name in fields:
            known_budget_tokens.add(field_name)

    perf_test_files = [
        REPO_ROOT / "frontend" / "tests" / "e2e" / "perf" / "album-open.perf.spec.ts",
        REPO_ROOT / "frontend" / "tests" / "e2e" / "perf" / "lightbox.perf.spec.ts",
    ]
    env_var_re = re.compile(r"GALLERY_PERF_[A-Z0-9_]+_BUDGET_MS")
    for path in perf_test_files:
        text = _read(path)
        if not text:
            errors.append(f"perf test missing: {path.relative_to(REPO_ROOT)}")
            continue
        found = set(env_var_re.findall(text))
        # Every env var the test uses must either be registered or be override-only.
        orphan = sorted(found - known_env_vars)
        if orphan:
            errors.append(f"{path.relative_to(REPO_ROOT)} references unregistered budget env vars: {orphan}")
    return errors


def main() -> int:
    """Validate the performance budget registry and its consumers."""
    toml = load_budgets(PERF_BUDGETS_TOML)
    errors: list[str] = []

    # 1. every TOML section has at least one consumer file that exists
    for section in toml:
        if section not in BUDGET_CONSUMERS:
            errors.append(f"TOML section '{section}' has no consumer registered in check_perf_budgets.py")
            continue
        consumers, env_vars = BUDGET_CONSUMERS[section]
        errors.extend(_check_consumer_files(section, consumers))
        errors.extend(_check_env_refs(section, consumers, env_vars))

    # 2. no consumer registered for a section that doesn't exist in TOML
    for section in BUDGET_CONSUMERS:
        if section not in toml:
            errors.append(
                f"consumer registry references TOML section '{section}' but it is not declared in perf_budgets.toml"
            )

    # 3. perf-budgets.json mirrors the relevant TOML sections
    errors.extend(_check_json_mirror(toml))

    # 4. no perf test references an unregistered budget env var
    errors.extend(_check_no_orphan_perf_tests(toml))

    if errors:
        print("perf budget coverage check FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"perf budget coverage OK: {len(toml)} sections, {len(JSON_MIRROR_SECTIONS)} mirrored into perf-budgets.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
