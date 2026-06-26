#!/usr/bin/env python3
"""Audit collected tests against the documented test matrix.

Purpose:
Identify which backend, frontend, and perf tests exist, which documented test
files are missing, and where coverage/report artifacts show weak spots.

Guarantees:
* collects pytest, Playwright, and vitest test ids without running the tests
* compares important test files with docs/testing/TEST_CATALOG.md
* writes Markdown and JSON reports for repeatable test-gap review

Run when:
* auditing test coverage before release or major refactors
* updating docs/testing after adding or removing important tests
* deciding which missing tests to prioritize next
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CATALOG_PATH = Path("docs/testing/TEST_CATALOG.md")
DEFAULT_MARKDOWN_OUTPUT = Path("docs/testing/test-gap-report.md")
DEFAULT_JSON_OUTPUT = Path("docs/testing/test-gap-report.json")

SUPPORT_TEST_FILES = {
    "backend/tests/__init__.py",
    "backend/tests/conftest.py",
    "frontend/tests/e2e/helpers/monitorErrors.ts",
    "frontend/tests/e2e/perf/perf-utils.ts",
    "frontend/src/test/setup.ts",
    "frontend/src/test/withSetup.ts",
}

FEATURE_MATRIX: list[dict[str, Any]] = [
    {
        "feature": "Library Inspector",
        "backend": ["backend/tests/test_library_inspector.py"],
        "frontend": ["frontend/tests/e2e/library-inspector.spec.ts"],
        "perf": ["frontend/tests/e2e/metadata-performance.spec.ts", "scripts/perf_library_inspector.py"],
    },
    {
        "feature": "Index Status and rebuild flow",
        "backend": [
            "backend/tests/test_catalog_status_contract.py",
            "backend/tests/test_catalog_status_endpoints.py",
            "backend/tests/test_catalog_status_ready_assets.py",
            "backend/tests/test_indexer_staging.py",
        ],
        "frontend": ["frontend/tests/e2e/index-status-panel.spec.ts", "frontend/tests/e2e/index-rebuild-flow.spec.ts"],
        "perf": [],
    },
    {
        "feature": "Browse API and catalog jobs",
        "backend": ["backend/tests/test_browse_api.py", "backend/tests/test_catalog_trigger_routing.py"],
        "frontend": ["frontend/tests/e2e/gallery-cache-revisit.spec.ts"],
        "perf": [],
    },
    {
        "feature": "Warm listing and folder counts",
        "backend": ["backend/tests/test_warm_folder_listing.py", "backend/tests/test_scan_folder_counts.py"],
        "frontend": [],
        "perf": ["scripts/perf_warm_listing.py"],
    },
    {
        "feature": "Scheduled refresh",
        "backend": ["backend/tests/test_scheduled_refresh.py"],
        "frontend": [],
        "perf": [],
    },
    {
        "feature": "File watcher",
        "backend": ["backend/tests/test_watcher.py"],
        "frontend": [],
        "perf": [],
    },
    {
        "feature": "Metadata, fielded search, and facets",
        "backend": [
            "backend/tests/test_api_integration_metadata_search_facets.py",
            "backend/tests/test_fielded_search_parser.py",
            "backend/tests/test_facets.py",
            "backend/tests/test_metadata_binary_sanitizer.py",
            "backend/tests/test_app.py",
        ],
        "frontend": [
            "frontend/tests/e2e/search-fielded-ui.spec.ts",
            "frontend/tests/e2e/advanced-search-drawer.spec.ts",
        ],
        "perf": [],
    },
    {
        "feature": "Image derivatives and lightbox",
        "backend": ["backend/tests/test_derivatives.py", "backend/tests/test_api_integration_derivatives.py"],
        "frontend": [
            "frontend/tests/e2e/lightbox-loading-policy.spec.ts",
            "frontend/tests/e2e/lightbox-visual-layer.spec.ts",
            "frontend/tests/e2e/mobile-lightbox-sheet.spec.ts",
        ],
        "perf": ["frontend/tests/e2e/perf/lightbox.perf.spec.ts"],
    },
    {
        "feature": "Health and path safety",
        "backend": ["backend/tests/test_api_integration_health_and_safety.py"],
        "frontend": [],
        "perf": [],
    },
    {
        "feature": "SPA navigation and query cache",
        "backend": [],
        "frontend": [
            "frontend/tests/e2e/gallery-no-reload.spec.ts",
            "frontend/tests/e2e/gallery-no-reload-real-backend.spec.ts",
            "frontend/tests/e2e/gallery-cache-revisit.spec.ts",
        ],
        "perf": ["frontend/tests/e2e/perf/album-open.perf.spec.ts"],
    },
    {
        "feature": "Responsive layout and sidebar",
        "backend": [],
        "frontend": [
            "frontend/tests/e2e/responsive-breakpoints.spec.ts",
            "frontend/tests/e2e/sidebar-trigger.spec.ts",
            "frontend/tests/e2e/mobile-lightbox-sheet.spec.ts",
        ],
        "perf": [],
    },
    {
        "feature": "Settings and preferences",
        "backend": [],
        "frontend": ["frontend/tests/e2e/settings-modal.spec.ts"],
        "perf": [],
    },
    {
        "feature": "Breadcrumb routing",
        "backend": [],
        "frontend": ["frontend/tests/e2e/breadcrumb.spec.ts"],
        "perf": [],
    },
    {
        "feature": "Fault tolerance",
        "backend": [],
        "frontend": ["frontend/tests/e2e/fault-injection.spec.ts"],
        "perf": [],
    },
    {
        "feature": "Tailwind and global styling",
        "backend": [],
        "frontend": ["frontend/tests/e2e/tailwind-phase0.spec.ts", "frontend/tests/e2e/tailwind-preflight.spec.ts"],
        "perf": [],
    },
    {
        "feature": "Performance fixtures and reporting",
        "backend": [],
        "frontend": [],
        "perf": [
            "scripts/create_perf_fixture.py",
            "scripts/summarize_perf_reports.py",
            "scripts/internal/perf-smoke.sh",
        ],
    },
]


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def run_command(command: list[str], cwd: Path) -> CommandResult:
    try:
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        return CommandResult(command, rel(cwd, repo_root()), 127, "", str(exc))
    return CommandResult(command, rel(cwd, repo_root()), completed.returncode, completed.stdout, completed.stderr)


def read_catalog(root: Path) -> dict[str, dict[str, str]]:
    catalog_file = root / CATALOG_PATH
    entries: dict[str, dict[str, str]] = {}
    if not catalog_file.exists():
        return entries

    for line in catalog_file.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        match = re.search(r"`([^`]+)`", cells[0])
        if not match:
            continue
        path = match.group(1)
        entries[path] = {
            "type": cells[1],
            "purpose": cells[2],
            "guarantees": cells[3],
            "run_when": cells[4],
            "feature": cells[5],
        }
    return entries


def important_test_files(root: Path) -> list[str]:
    patterns = [
        "backend/tests/test_*.py",
        "frontend/tests/e2e/**/*.spec.ts",
        "frontend/src/**/__tests__/**/*.test.ts",
        "frontend/src/test/**/*.ts",
        "scripts/perf_*.py",
        "scripts/create_perf_fixture.py",
        "scripts/summarize_perf_reports.py",
        "scripts/audit_test_matrix.py",
        "scripts/internal/perf-smoke.sh",
    ]
    files: set[str] = set()
    for pattern in patterns:
        files.update(rel(path, root) for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def normalize_backend_test_file(raw: str) -> str:
    path = raw.split("::", 1)[0]
    if path.startswith("backend/"):
        return path
    if path.startswith("tests/"):
        return f"backend/{path}"
    return path


def collect_backend_tests(root: Path, python: str | None) -> tuple[CommandResult, list[str], set[str]]:
    backend_dir = root / "backend"
    python_cmd = python
    if python_cmd is None:
        venv_python = root / "backend/.venv_linux/bin/python"
        python_cmd = str(venv_python) if venv_python.exists() else sys.executable
    result = run_command([python_cmd, "-m", "pytest", "--collect-only", "-q"], backend_dir)

    tests: list[str] = []
    files: set[str] = set()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if "::" not in stripped or " tests collected" in stripped:
            continue
        test_file = normalize_backend_test_file(stripped)
        if test_file.startswith("backend/tests/test_"):
            tests.append(stripped)
            files.add(test_file)
    return result, tests, files


PLAYWRIGHT_LINE_RE = re.compile(
    r"^\s*\[[^\]]+\]\s+›\s+(?P<path>[^:]+):(?P<line>\d+):(?P<column>\d+)\s+›\s+(?P<title>.+)$"
)

# vitest list output: "<relative_path> > <describe block> > <test name>"
VITEST_LINE_RE = re.compile(r"^(?P<path>src/[^\s].*?\.test\.ts)\s+>\s+(?P<title>.+)$")


def collect_frontend_tests(root: Path) -> tuple[CommandResult, list[str], set[str]]:
    frontend_dir = root / "frontend"
    result = run_command(
        ["corepack", "pnpm", "exec", "playwright", "test", "--list", "--project=chromium"], frontend_dir
    )

    tests: list[str] = []
    files: set[str] = set()
    for line in result.stdout.splitlines():
        match = PLAYWRIGHT_LINE_RE.match(line)
        if not match:
            continue
        path = (
            f"frontend/tests/e2e/{match.group('path')}"
            if not match.group("path").startswith("tests/")
            else f"frontend/{match.group('path')}"
        )
        tests.append(f"{path}:{match.group('line')} › {match.group('title')}")
        files.add(path)
    return result, tests, files


def collect_vitest_tests(root: Path) -> tuple[CommandResult, list[str], set[str]]:
    """Collect vitest unit tests without running them.

    Uses `vitest list` (vitest 4+) which prints one test per line in the form
    `src/<path>.test.ts > <describe> > <test name>`.
    """
    frontend_dir = root / "frontend"
    result = run_command(["corepack", "pnpm", "exec", "vitest", "list"], frontend_dir)

    tests: list[str] = []
    files: set[str] = set()
    for line in result.stdout.splitlines():
        match = VITEST_LINE_RE.match(line)
        if not match:
            continue
        path = f"frontend/{match.group('path')}"
        tests.append(f"{path} › {match.group('title')}")
        files.add(path)
    return result, tests, files


def load_backend_coverage(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def backend_coverage_rows(
    coverage: dict[str, Any] | None, threshold: float
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not coverage:
        return None, []
    totals = coverage.get("totals", {})
    rows: list[dict[str, Any]] = []
    for filename, data in coverage.get("files", {}).items():
        summary = data.get("summary", {})
        percent = float(summary.get("percent_covered", 0.0))
        rows.append(
            {
                "file": filename,
                "percent": percent,
                "missing_lines": int(summary.get("missing_lines", 0)),
                "statements": int(summary.get("num_statements", 0)),
                "below_threshold": percent < threshold,
            }
        )
    rows.sort(key=lambda row: (row["percent"], -row["missing_lines"], row["file"]))
    return totals, rows


def load_frontend_coverage_summary(root: Path) -> dict[str, Any] | None:
    candidates = [
        root / "frontend/coverage/vitest/coverage-summary.json",
        root / "frontend/coverage/coverage-summary.json",
        root / "frontend/coverage-summary.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def perf_report_files(root: Path) -> list[str]:
    results_dir = root / "frontend/test-results/perf"
    if not results_dir.exists():
        return []
    return sorted(rel(path, root) for path in results_dir.glob("*.json") if path.is_file())


def status_for_files(
    files: list[str], existing: set[str], collected: set[str], catalog: dict[str, dict[str, str]]
) -> tuple[str, list[str]]:
    if not files:
        return "N/A", []

    gaps: list[str] = []
    for file in files:
        if file not in existing:
            gaps.append(f"missing file: {file}")
            continue
        if (
            (file.startswith("backend/tests/") or file.startswith("frontend/tests/e2e/"))
            and collected
            and file not in collected
        ):
            gaps.append(f"not collected: {file}")
        if file not in catalog:
            gaps.append(f"not cataloged: {file}")

    return ("OK" if not gaps else "GAP"), gaps


def build_matrix_rows(
    existing: set[str],
    backend_collected: set[str],
    frontend_collected: set[str],
    catalog: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    collected = backend_collected | frontend_collected
    for entry in FEATURE_MATRIX:
        backend_status, backend_gaps = status_for_files(entry["backend"], existing, backend_collected, catalog)
        frontend_status, frontend_gaps = status_for_files(entry["frontend"], existing, frontend_collected, catalog)
        perf_status, perf_gaps = status_for_files(entry["perf"], existing, collected, catalog)
        rows.append(
            {
                "feature": entry["feature"],
                "backend": backend_status,
                "frontend": frontend_status,
                "perf": perf_status,
                "gaps": backend_gaps + frontend_gaps + perf_gaps,
            }
        )
    return rows


def markdown_list(items: list[str], empty: str = "None") -> str:
    if not items:
        return empty
    return "<br>".join(f"`{item}`" for item in items)


def command_line(result: CommandResult | None) -> str:
    if result is None:
        return "skipped"
    return f"(cd {result.cwd} && {' '.join(result.command)})"


def write_markdown(
    path: Path,
    *,
    generated_at: str,
    backend_result: CommandResult | None,
    frontend_result: CommandResult | None,
    vitest_result: CommandResult | None,
    backend_tests: list[str],
    frontend_tests: list[str],
    vitest_tests: list[str],
    existing_files: list[str],
    catalog: dict[str, dict[str, str]],
    matrix_rows: list[dict[str, Any]],
    missing_catalog_files: list[str],
    uncataloged_files: list[str],
    cataloged_uncollected_tests: list[str],
    backend_coverage_totals: dict[str, Any] | None,
    backend_coverage_rows_data: list[dict[str, Any]],
    frontend_coverage_summary: dict[str, Any] | None,
    perf_reports: list[str],
    coverage_threshold: float,
) -> None:
    backend_files = sorted({normalize_backend_test_file(test) for test in backend_tests})
    frontend_files = sorted({test.split(":", 1)[0] for test in frontend_tests})
    vitest_files = sorted({test.split(" › ", 1)[0] for test in vitest_tests})
    matrix_gaps = [gap for row in matrix_rows for gap in row["gaps"]]
    low_backend_modules = [row for row in backend_coverage_rows_data if row["below_threshold"]]

    lines = [
        "# Test Gap Report",
        "",
        f"Generated: {generated_at}",
        "",
        "This report is generated by `scripts/audit_test_matrix.py`. It collects test ids without running tests.",
        "",
        "## Summary",
        "",
        f"- Backend collected tests: {len(backend_tests)} tests in {len(backend_files)} files.",
        f"- Frontend Playwright tests: {len(frontend_tests)} tests in {len(frontend_files)} files.",
        f"- Frontend Vitest unit tests: {len(vitest_tests)} tests in {len(vitest_files)} files.",
        f"- Important test/catalog files on disk: {len(existing_files)}.",
        f"- Catalog entries: {len(catalog)}.",
        f"- Matrix gaps: {len(matrix_gaps)}.",
        f"- Uncataloged important files: {len(uncataloged_files)}.",
        f"- Catalog entries missing on disk: {len(missing_catalog_files)}.",
        f"- Perf JSON reports found: {len(perf_reports)}.",
    ]

    if backend_coverage_totals:
        lines.append(
            "- Backend coverage artifact: "
            f"{backend_coverage_totals.get('percent_covered', 0.0):.1f}% "
            f"({backend_coverage_totals.get('missing_lines', 0)} missing lines)."
        )
    else:
        lines.append("- Backend coverage artifact: missing.")

    if frontend_coverage_summary:
        total = frontend_coverage_summary.get("total", {})
        lines.append(f"- Frontend coverage artifact: lines {total.get('lines', {}).get('pct', 'unknown')}%.")
    else:
        lines.append("- Frontend coverage artifact: missing.")

    lines.extend(
        [
            "",
            "## Collection Commands",
            "",
            f"- Backend: `{command_line(backend_result)}`",
            f"- Backend collect status: `{backend_result.returncode if backend_result else 'skipped'}`",
            f"- Frontend Playwright: `{command_line(frontend_result)}`",
            f"- Frontend Playwright collect status: `{frontend_result.returncode if frontend_result else 'skipped'}`",
            f"- Frontend Vitest: `{command_line(vitest_result)}`",
            f"- Frontend Vitest collect status: `{vitest_result.returncode if vitest_result else 'skipped'}`",
            "",
            "## Feature Matrix",
            "",
            "| Feature | Backend | Frontend | Perf/diagnostic | Gaps |",
            "| --- | --- | --- | --- | --- |",
        ]
    )

    for row in matrix_rows:
        gaps = "<br>".join(row["gaps"]) if row["gaps"] else "None"
        lines.append(f"| {row['feature']} | {row['backend']} | {row['frontend']} | {row['perf']} | {gaps} |")

    lines.extend(
        [
            "",
            "## Catalog Alignment",
            "",
            "| Check | Result |",
            "| --- | --- |",
            f"| Catalog entries missing on disk | {markdown_list(missing_catalog_files)} |",
            f"| Important files missing from catalog | {markdown_list(uncataloged_files)} |",
            f"| Cataloged test files not collected | {markdown_list(cataloged_uncollected_tests)} |",
            "",
            "## Backend Coverage Gaps",
            "",
        ]
    )

    if backend_coverage_totals:
        lines.extend(
            [
                f"Threshold for this table: modules below {coverage_threshold:.0f}% line coverage.",
                "",
                "| Module | Coverage | Missing lines | Statements |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for row in low_backend_modules[:20]:
            lines.append(f"| `{row['file']}` | {row['percent']:.1f}% | {row['missing_lines']} | {row['statements']} |")
        if not low_backend_modules:
            lines.append("| None |  |  |  |")
    else:
        lines.append("No backend coverage JSON found. Run backend coverage first.")

    lines.extend(
        [
            "",
            "## Frontend Coverage",
            "",
        ]
    )
    if frontend_coverage_summary:
        total = frontend_coverage_summary.get("total", {})
        lines.extend(
            [
                "| Metric | Percent | Covered | Total |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for metric in ("lines", "statements", "functions", "branches"):
            data = total.get(metric, {})
            lines.append(
                f"| {metric} | {data.get('pct', 'unknown')} | {data.get('covered', '')} | {data.get('total', '')} |"
            )
    else:
        lines.append(
            "No frontend coverage summary found at `frontend/coverage/coverage-summary.json`. "
            "This usually means the Playwright/Istanbul coverage pipeline did not emit `.nyc_output`."
        )

    lines.extend(
        [
            "",
            "## Perf Reports",
            "",
            markdown_list(perf_reports),
            "",
            "## Recommendations",
            "",
        ]
    )

    recommendations: list[str] = []
    if matrix_gaps:
        recommendations.append(
            "Fix matrix gaps first because they represent expected test surfaces without a concrete file/catalog/collection proof."
        )
    if uncataloged_files:
        recommendations.append(
            "Add uncataloged important files to `docs/testing/TEST_CATALOG.md` or mark them as support-only in the audit script."
        )
    if low_backend_modules:
        recommendations.append(
            "Prioritize focused backend tests for the lowest-covered modules, especially modules with high missing-line counts."
        )
    if not frontend_coverage_summary:
        recommendations.append(
            "Fix frontend coverage artifact generation before using this report for combined repository coverage."
        )
    if not perf_reports:
        recommendations.append(
            "Run perf smoke or metadata perf diagnostics to produce JSON reports before perf trend review."
        )
    if not recommendations:
        recommendations.append(
            "No immediate matrix/catalog gaps found. Use coverage rows to decide deeper edge-case tests."
        )

    lines.extend(f"- {recommendation}" for recommendation in recommendations)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT, help="Markdown report path")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT, help="JSON report path")
    parser.add_argument("--backend-python", help="Python executable for backend pytest collection")
    parser.add_argument("--skip-backend-collect", action="store_true", help="skip pytest collection")
    parser.add_argument("--skip-frontend-collect", action="store_true", help="skip Playwright collection")
    parser.add_argument("--skip-vitest-collect", action="store_true", help="skip vitest unit test collection")
    parser.add_argument(
        "--coverage-json", type=Path, default=Path("backend/coverage.json"), help="backend coverage JSON path"
    )
    parser.add_argument(
        "--coverage-threshold", type=float, default=70.0, help="coverage percent threshold for module gaps"
    )
    parser.add_argument(
        "--fail-on-gaps", action="store_true", help="return non-zero when matrix/catalog gaps are found"
    )
    args = parser.parse_args(argv)

    root = repo_root()
    existing_files = important_test_files(root)
    existing = set(existing_files)
    catalog = read_catalog(root)

    backend_result: CommandResult | None = None
    backend_tests: list[str] = []
    backend_collected: set[str] = set()
    if not args.skip_backend_collect:
        backend_result, backend_tests, backend_collected = collect_backend_tests(root, args.backend_python)

    frontend_result: CommandResult | None = None
    frontend_tests: list[str] = []
    frontend_collected: set[str] = set()
    if not args.skip_frontend_collect:
        frontend_result, frontend_tests, frontend_collected = collect_frontend_tests(root)

    vitest_result: CommandResult | None = None
    vitest_tests: list[str] = []
    vitest_collected: set[str] = set()
    if not args.skip_vitest_collect:
        vitest_result, vitest_tests, vitest_collected = collect_vitest_tests(root)

    matrix_rows = build_matrix_rows(existing, backend_collected, frontend_collected, catalog)
    catalog_files = set(catalog)
    missing_catalog_files = sorted(file for file in catalog_files if not (root / file).exists())
    uncataloged_files = sorted(file for file in existing if file not in catalog and file not in SUPPORT_TEST_FILES)

    cataloged_test_files = {
        file
        for file in catalog_files
        if file.startswith("backend/tests/test_")
        or (file.startswith("frontend/tests/e2e/") and file.endswith(".spec.ts"))
        or (file.startswith("frontend/src/") and file.endswith(".test.ts"))
    }

    # Flag a cataloged test file as "not collected" only when the collector
    # responsible for its suite actually ran. This prevents false positives
    # when one or more collectors are skipped via --skip-*-collect.
    def _was_collected(file: str) -> bool:
        if file.startswith("backend/tests/test_"):
            if backend_result is None:
                return True
            return file in backend_collected
        if file.startswith("frontend/tests/e2e/") and file.endswith(".spec.ts"):
            if frontend_result is None:
                return True
            return file in frontend_collected
        if file.startswith("frontend/src/") and file.endswith(".test.ts"):
            if vitest_result is None:
                return True
            return file in vitest_collected
        return True

    cataloged_uncollected_tests = sorted(file for file in cataloged_test_files if not _was_collected(file))

    backend_coverage = load_backend_coverage(root / args.coverage_json)
    backend_coverage_totals, backend_rows = backend_coverage_rows(backend_coverage, args.coverage_threshold)
    frontend_coverage_summary = load_frontend_coverage_summary(root)
    perf_reports = perf_report_files(root)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    payload = {
        "generated_at": generated_at,
        "commands": {
            "backend": None
            if backend_result is None
            else {
                "command": backend_result.command,
                "cwd": backend_result.cwd,
                "returncode": backend_result.returncode,
            },
            "frontend": None
            if frontend_result is None
            else {
                "command": frontend_result.command,
                "cwd": frontend_result.cwd,
                "returncode": frontend_result.returncode,
            },
            "vitest": None
            if vitest_result is None
            else {
                "command": vitest_result.command,
                "cwd": vitest_result.cwd,
                "returncode": vitest_result.returncode,
            },
        },
        "counts": {
            "backend_tests": len(backend_tests),
            "backend_test_files": len(backend_collected),
            "frontend_tests": len(frontend_tests),
            "frontend_test_files": len(frontend_collected),
            "vitest_tests": len(vitest_tests),
            "vitest_test_files": len(vitest_collected),
            "important_files": len(existing_files),
            "catalog_entries": len(catalog),
            "perf_reports": len(perf_reports),
        },
        "matrix": matrix_rows,
        "catalog_alignment": {
            "missing_catalog_files": missing_catalog_files,
            "uncataloged_files": uncataloged_files,
            "cataloged_uncollected_tests": cataloged_uncollected_tests,
        },
        "coverage": {
            "backend_totals": backend_coverage_totals,
            "backend_modules_below_threshold": [row for row in backend_rows if row["below_threshold"]],
            "frontend_summary_found": frontend_coverage_summary is not None,
        },
        "perf_reports": perf_reports,
    }

    output = root / args.output
    json_output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(
        output,
        generated_at=generated_at,
        backend_result=backend_result,
        frontend_result=frontend_result,
        vitest_result=vitest_result,
        backend_tests=backend_tests,
        frontend_tests=frontend_tests,
        vitest_tests=vitest_tests,
        existing_files=existing_files,
        catalog=catalog,
        matrix_rows=matrix_rows,
        missing_catalog_files=missing_catalog_files,
        uncataloged_files=uncataloged_files,
        cataloged_uncollected_tests=cataloged_uncollected_tests,
        backend_coverage_totals=backend_coverage_totals,
        backend_coverage_rows_data=backend_rows,
        frontend_coverage_summary=frontend_coverage_summary,
        perf_reports=perf_reports,
        coverage_threshold=args.coverage_threshold,
    )
    write_json(json_output, payload)

    print(f"Wrote {args.output}")
    print(f"Wrote {args.json_output}")

    matrix_gaps = [gap for row in matrix_rows for gap in row["gaps"]]
    if args.fail_on_gaps and (matrix_gaps or missing_catalog_files or uncataloged_files):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
