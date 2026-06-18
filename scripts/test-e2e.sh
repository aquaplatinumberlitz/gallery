#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  E2E / Integration Tests (Playwright)"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT/frontend"

# Build if dist doesn't exist
if [ ! -d "dist" ]; then
    echo ""
    echo ">>> Building frontend..."
    corepack pnpm run build 2>&1 | tail -5
fi

echo ""
echo ">>> Running Playwright E2E tests..."

if [ $# -gt 0 ]; then
    # Specific files passed as args — run only those
    corepack pnpm exec playwright test "$@" \
        --project=chromium \
        --reporter=html
else
    # No args — run all E2E tests
    corepack pnpm exec playwright test tests/e2e/ \
        --project=chromium \
        --reporter=html
fi

echo ""
echo "=========================================="
echo "  E2E tests complete"
echo "=========================================="
