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
npx playwright test tests/perf/album-open.perf.spec.ts --project=chromium "$@" 2>&1 | tee "$RESULTS_DIR/album-open-perf.log"

echo ""
echo ">>> Running lightbox perf tests..."
npx playwright test tests/perf/lightbox.perf.spec.ts --project=chromium "$@" 2>&1 | tee "$RESULTS_DIR/lightbox-perf.log"

# Extract JSON reports from logs
echo ""
echo ">>> Extracting JSON perf reports..."
grep -A100 '"albumName"' "$RESULTS_DIR/album-open-perf.log" | head -50 > "$RESULTS_DIR/album-open-report.json" 2>/dev/null || true
grep -A100 '"albumName"' "$RESULTS_DIR/lightbox-perf.log" | head -50 > "$RESULTS_DIR/lightbox-open-report.json" 2>/dev/null || true

echo ""
echo "Perf results written to $RESULTS_DIR/"
echo "=========================================="
echo "  Perf smoke tests complete"
echo "=========================================="
