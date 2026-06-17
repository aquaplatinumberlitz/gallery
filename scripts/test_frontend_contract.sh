#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Frontend Contract Tests (Playwright)"
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
echo ">>> Running Playwright contract tests..."
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
echo "  Frontend contract tests complete"
echo "=========================================="
