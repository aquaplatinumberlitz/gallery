#!/usr/bin/env python3
"""Load and validate the managed performance workload manifest."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).resolve().with_name("perf_manifest.toml")
VALID_SUITES = {"ci", "extended", "diagnostic"}


def load_perf_manifest(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Return workload entries from the canonical performance manifest."""
    manifest_path = Path(path) if path is not None else MANIFEST_PATH
    with manifest_path.open("rb") as handle:
        data = tomllib.load(handle)
    workloads = data.get("workloads")
    if not isinstance(workloads, dict):
        raise ValueError("perf manifest must define a [workloads] table")
    return workloads


def expected_reports(suite: str, path: str | Path | None = None) -> list[str]:
    """Return the stable report filenames required by one managed suite."""
    reports: list[str] = []
    for workload in load_perf_manifest(path).values():
        if workload.get("suite") == suite:
            reports.extend(str(report) for report in workload.get("reports", []))
    return sorted(reports)
