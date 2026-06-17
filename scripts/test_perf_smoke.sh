#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Perf Smoke Tests"
echo "=========================================="
echo "  NOTE: Requires a running gallery app and real album data"
echo "  Set env: GALLERY_BASE_URL, GALLERY_PERF_ALBUM_NAME, GALLERY_PERF_ALBUM_PATH"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT/frontend"

RESULTS_DIR="$REPO_ROOT/frontend/test-results/perf"
mkdir -p "$RESULTS_DIR"

echo ""
echo ">>> Running album open perf test..."
corepack pnpm exec playwright test tests/perf/album-open.perf.spec.ts --project=chromium "$@"

echo ""
echo ">>> Running lightbox perf tests..."
corepack pnpm exec playwright test tests/perf/lightbox.perf.spec.ts --project=chromium "$@"

echo ""
echo "Perf JSON results written directly to $RESULTS_DIR/"
ls -la "$RESULTS_DIR/"*.json 2>/dev/null || echo "(no JSON reports found)"

echo ""
echo "=========================================="
echo "  Perf smoke tests complete"
echo "=========================================="
