#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTERNAL_DIR="$REPO_ROOT/scripts/internal"

if [[ -x "$REPO_ROOT/backend/venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/backend/venv/bin/python"
elif [[ -x "$REPO_ROOT/backend/.venv_linux/bin/python" ]]; then
    PYTHON="$REPO_ROOT/backend/.venv_linux/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

usage() {
    cat <<'EOF'
Usage: ./test.sh <command> [test arguments]

Primary commands:
  fast         Full lint/format, unit coverage, and frontend build
  full         CI-equivalent: fast + functional E2E + performance tests

Focused commands:
  lint         Full-repository lint and format checks
  unit         Backend and frontend unit tests with coverage, then build
  docs         Docs staleness, test headers, and matrix catalog audit
  e2e          Managed functional Playwright suite
  perf         Managed Playwright performance suite
  backend-api  Backend API integration subset
  perf-smoke   Extended backend and browser performance diagnostics
EOF
}

run_lint() {
    cd "$REPO_ROOT"
    echo "==> Backend Ruff lint"
    "$PYTHON" -m ruff check backend scripts start.py
    echo "==> Backend Ruff format check"
    "$PYTHON" -m ruff format --check backend scripts start.py

    cd "$REPO_ROOT/frontend"
    echo "==> Frontend ESLint (source)"
    corepack pnpm run lint
    echo "==> Frontend ESLint (tests)"
    corepack pnpm run lint:tests
    echo "==> Frontend Prettier check"
    corepack pnpm run format:check
}

run_unit() {
    cd "$REPO_ROOT"
    echo "==> Backend pytest"
    "$PYTHON" -m pytest backend/tests/ -x -q \
        --cov=backend \
        --cov-report=term-missing \
        --cov-report=xml \
        --cov-fail-under=85 \
        "$@"

    cd "$REPO_ROOT/frontend"
    echo "==> Frontend Vitest with coverage"
    corepack pnpm run test:unit:coverage
    echo "==> Frontend build"
    corepack pnpm run build
}

run_docs() {
    cd "$REPO_ROOT"
    echo "==> Docs staleness check"
    "$PYTHON" scripts/check_docs_staleness.py
    echo "==> Test/debug header check"
    "$PYTHON" scripts/check_test_docs.py
    echo "==> Test matrix catalog audit"
    "$PYTHON" scripts/audit_test_matrix.py --fail-on-gaps
}

COMMAND="${1:-help}"
if [[ $# -gt 0 ]]; then
    shift
fi

case "$COMMAND" in
    help|-h|--help)
        usage
        ;;
    lint)
        run_lint
        ;;
    unit)
        run_unit "$@"
        ;;
    docs)
        run_docs
        ;;
    fast)
        run_lint
        run_unit "$@"
        ;;
    e2e)
        exec "$INTERNAL_DIR/test-playwright.sh" functional "$@"
        ;;
    perf)
        exec "$INTERNAL_DIR/test-playwright.sh" perf "$@"
        ;;
    full)
        export PLAYWRIGHT_RETRIES="${PLAYWRIGHT_RETRIES:-1}"
        run_lint
        run_unit
        export GALLERY_TEST_SKIP_BUILD=1
        "$INTERNAL_DIR/test-playwright.sh" functional
        "$INTERNAL_DIR/test-playwright.sh" perf
        ;;
    backend-api)
        cd "$REPO_ROOT"
        exec "$PYTHON" -m pytest \
            backend/tests/test_api_integration_health_and_safety.py \
            backend/tests/test_api_integration_scan.py \
            backend/tests/test_api_integration_derivatives.py \
            backend/tests/test_api_integration_metadata_search_facets.py \
            backend/tests/test_api_integration_index_status.py \
            -v "$@"
        ;;
    perf-smoke)
        exec "$INTERNAL_DIR/perf-smoke.sh" "$@"
        ;;
    *)
        echo "Unknown test command: $COMMAND" >&2
        usage >&2
        exit 2
        ;;
esac
