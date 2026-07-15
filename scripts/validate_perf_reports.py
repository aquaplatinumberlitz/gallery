#!/usr/bin/env python3
"""Fail unless every report declared for a managed perf suite exists and is valid JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from perf_manifest import expected_reports


def validate_reports(results_dir: Path, suite: str) -> list[str]:
    """Return report contract errors for one results directory and suite."""
    errors: list[str] = []
    for report_name in expected_reports(suite):
        path = results_dir / report_name
        if not path.is_file():
            errors.append(f"missing expected {suite} report: {report_name}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid report {report_name}: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"report root must be an object: {report_name}")
    return errors


def main() -> int:
    """Validate command-line report inputs against the managed manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--suite", default="ci")
    args = parser.parse_args()

    errors = validate_reports(Path(args.results_dir).resolve(), args.suite)
    if errors:
        print("perf report contract failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"perf report contract OK: {len(expected_reports(args.suite))} {args.suite} reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
