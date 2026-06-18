#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Deterministic Test Suite"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ---- Lint / Format checks ----
echo ""
echo "--- Backend Ruff lint (changed files) ---"
"$SCRIPT_DIR/lint_backend.sh"

echo ""
echo "--- Backend Ruff format check (changed files) ---"
"$SCRIPT_DIR/format_backend_check.sh"

echo ""
echo "--- Frontend ESLint ---"
cd "$REPO_ROOT/frontend"
corepack pnpm run lint

echo ""
echo "--- Frontend Prettier check (changed files) ---"
corepack pnpm run format:check

# ---- Backend pytest ----
echo ""
echo "--- Backend pytest ---"
cd "$REPO_ROOT/backend"
python -m pytest --cov=backend --cov-report=term-missing --cov-report=xml -q "$@"

# ---- Frontend build ----
echo ""
echo "--- Frontend build ---"
cd "$REPO_ROOT/frontend"
corepack pnpm run build

# ---- Frontend Playwright contract tests ----
echo ""
echo "--- Frontend Playwright contract tests ---"
corepack pnpm exec playwright test \
    tests/lightbox-loading-policy.spec.ts \
    tests/gallery-no-reload.spec.ts \
    tests/gallery-cache-revisit.spec.ts \
    tests/mobile-lightbox-sheet.spec.ts \
    tests/search-fielded-ui.spec.ts \
    tests/responsive-breakpoints.spec.ts \
    "$@"

echo ""
echo "=========================================="
echo "  All deterministic tests complete"
echo "=========================================="
echo ""
echo "  NOTE: Perf smoke tests are separate and require a running app."
echo "  Run: bash scripts/test_perf_smoke.sh"
