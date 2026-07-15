#!/usr/bin/env python3
"""Validate canonical perf budgets, workload reachability, and browser mirrors."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from perf_lib import load_budgets  # noqa: E402
from perf_manifest import VALID_SUITES, load_perf_manifest  # noqa: E402

JSON_MIRROR_SECTIONS: dict[str, list[str]] = {
    "album_open": ["scan_p95_ms", "first_thumbnail_ms", "warm_batch_complete_ms"],
    "lightbox": ["open_ms", "transition_ms", "visual_ready_ms"],
    "metadata_nav": [
        "api_ms",
        "nav_ms",
        "render_ms",
        "rendered_rows_max",
        "sort_ms",
        "search_debounce_ms",
        "search_requests_max",
        "state_restore_ms",
    ],
}

PERF_BUDGETS_TOML = REPO_ROOT / "scripts" / "perf_budgets.toml"
PERF_BUDGETS_JSON = REPO_ROOT / "frontend" / "tests" / "e2e" / "perf" / "perf-budgets.json"
ENV_VAR_RE = re.compile(r"GALLERY_PERF_[A-Z0-9_]+(?:_MS|_MAX|_PCT|_MIB|_ROWS)?")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _check_manifest(toml: dict[str, dict[str, Any]]) -> tuple[list[str], int]:
    errors: list[str] = []
    workloads = load_perf_manifest()
    covered_sections: set[str] = set()
    registered_env_vars: set[str] = set()
    consumer_paths: set[Path] = set()
    report_owners: dict[tuple[str, str], str] = {}

    for name, workload in workloads.items():
        suite = workload.get("suite")
        if suite not in VALID_SUITES:
            errors.append(f"workload '{name}' has invalid suite {suite!r}")

        sections = workload.get("budget_sections")
        consumers = workload.get("consumers")
        tokens = workload.get("budget_tokens")
        reports = workload.get("reports")
        if not isinstance(sections, list) or not sections:
            errors.append(f"workload '{name}' must declare budget_sections")
            sections = []
        if not isinstance(consumers, list) or not consumers:
            errors.append(f"workload '{name}' must declare consumers")
            consumers = []
        if not isinstance(tokens, list) or not tokens:
            errors.append(f"workload '{name}' must declare budget_tokens")
            tokens = []
        if not isinstance(reports, list) or not reports:
            errors.append(f"workload '{name}' must declare reports")
            reports = []

        for section in sections:
            covered_sections.add(str(section))
            if section not in toml:
                errors.append(f"workload '{name}' references unknown budget section '{section}'")

        texts: list[str] = []
        for relative in consumers:
            path = REPO_ROOT / str(relative)
            consumer_paths.add(path)
            text = _read(path)
            if not text:
                errors.append(f"workload '{name}' consumer is missing or unreadable: {relative}")
            texts.append(text)
        for token in tokens:
            token = str(token)
            if token.startswith("GALLERY_PERF_"):
                registered_env_vars.add(token)
            if not any(token in text for text in texts):
                errors.append(f"workload '{name}' consumer does not reference required token {token!r}")

        for report in reports:
            report = str(report)
            if Path(report).name != report or not report.endswith(".json"):
                errors.append(f"workload '{name}' has invalid report filename: {report}")
                continue
            key = (str(suite), report)
            if key in report_owners:
                errors.append(
                    f"report '{report}' is declared twice in suite '{suite}': {report_owners[key]} and {name}"
                )
            report_owners[key] = name

    for section in toml:
        if section not in covered_sections:
            errors.append(f"TOML section '{section}' is not reachable from any perf workload")

    for path in consumer_paths:
        if path.suffix not in {".ts", ".py"}:
            continue
        found = set(ENV_VAR_RE.findall(_read(path)))
        orphan = sorted(variable for variable in found if "BUDGET" in variable and variable not in registered_env_vars)
        if orphan:
            errors.append(f"{path.relative_to(REPO_ROOT)} references unregistered perf budget env vars: {orphan}")
    return errors, len(workloads)


def _check_json_mirror(toml: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if not PERF_BUDGETS_JSON.exists():
        return [f"perf-budgets.json missing at {PERF_BUDGETS_JSON.relative_to(REPO_ROOT)}"]
    try:
        data = json.loads(PERF_BUDGETS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"perf-budgets.json is invalid JSON: {exc}"]
    for section, fields in JSON_MIRROR_SECTIONS.items():
        if section not in data:
            errors.append(f"perf-budgets.json missing section '{section}'")
            continue
        for field in fields:
            json_value = data[section].get(field)
            toml_value = toml.get(section, {}).get(field)
            if json_value != toml_value:
                errors.append(
                    f"perf-budgets.json[{section}].{field} = {json_value!r} does not match TOML value {toml_value!r}"
                )
    return errors


def main() -> int:
    """Validate the canonical budgets, workload manifest, and browser mirror."""
    toml = load_budgets(PERF_BUDGETS_TOML)
    manifest_errors, workload_count = _check_manifest(toml)
    errors = [*manifest_errors, *_check_json_mirror(toml)]
    if errors:
        print("perf budget coverage check FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"perf budget coverage OK: {len(toml)} sections, {workload_count} workloads, "
        f"{len(JSON_MIRROR_SECTIONS)} browser mirrors"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
