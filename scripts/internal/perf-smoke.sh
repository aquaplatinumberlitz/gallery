#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Perf Smoke Tests"
echo "=========================================="
echo "  NOTE: Requires a running gallery app and real album data"
echo "  Set env: GALLERY_BASE_URL, GALLERY_PERF_ALBUM_NAME, GALLERY_PERF_ALBUM_PATH"
echo "  Optional: GALLERY_PERF_USE_FIXTURE=1 GALLERY_PERF_START_BACKEND=1"
echo "=========================================="

INTERNAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(dirname "$INTERNAL_DIR")"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$REPO_ROOT/frontend/test-results/perf"
mkdir -p "$RESULTS_DIR"

BACKEND_PORT="${GALLERY_PERF_BACKEND_PORT:-4180}"
export GALLERY_API_BASE_URL="${GALLERY_API_BASE_URL:-http://127.0.0.1:$BACKEND_PORT}"
export VITE_API_URL="${VITE_API_URL:-$GALLERY_API_BASE_URL}"
export GALLERY_BASE_URL="${GALLERY_BASE_URL:-http://localhost:5173}"
export GALLERY_PERF_E2E=1
if [[ -n "${GALLERY_PERF_PYTHON:-}" ]]; then
    PERF_PYTHON="$GALLERY_PERF_PYTHON"
elif [[ -x "$REPO_ROOT/backend/.venv_linux/bin/python" ]]; then
    PERF_PYTHON="$REPO_ROOT/backend/.venv_linux/bin/python"
else
    PERF_PYTHON="python3"
fi

if [[ "${GALLERY_PERF_USE_FIXTURE:-0}" == "1" ]]; then
    echo ""
    echo ">>> Creating deterministic perf fixture..."
    FIXTURE_ENV_FILE="$RESULTS_DIR/perf-fixture.env"
    FIXTURE_ARGS=(--env-file "$FIXTURE_ENV_FILE")
    if [[ -n "${GALLERY_PERF_FIXTURE_ROOT:-}" ]]; then
        FIXTURE_ARGS+=(--root "$GALLERY_PERF_FIXTURE_ROOT")
    fi
    if [[ -n "${GALLERY_PERF_FIXTURE_IMAGES:-}" ]]; then
        FIXTURE_ARGS+=(--images "$GALLERY_PERF_FIXTURE_IMAGES")
    fi
    SEARCH_ROWS="${GALLERY_PERF_SEARCH_ROWS:-5000}"
    if [[ "${GALLERY_PERF_SEARCH_PROFILE:-ci}" == "scheduled" ]]; then
        SEARCH_ROWS="${GALLERY_PERF_SEARCH_ROWS:-25000}"
    fi
    FIXTURE_ARGS+=(--search-rows "$SEARCH_ROWS")
    "$PERF_PYTHON" "$SCRIPT_DIR/create_perf_fixture.py" \
        "${FIXTURE_ARGS[@]}" \
        ${GALLERY_PERF_FIXTURE_CLEAN:+--clean}
    # shellcheck disable=SC1090
    source "$FIXTURE_ENV_FILE"
    export PATH_SAFETY_ROOT PATH_SAFETY_ROOT_PATH GALLERY_METADATA_DB GALLERY_THUMBNAIL_CACHE_DIR
    export GALLERY_PERF_ALBUM_NAME GALLERY_PERF_ALBUM_PATH GALLERY_PERF_SCAN_PATH
    export GALLERY_PERF_INSPECTOR_SCOPE
    export GALLERY_PERF_SEARCH_ROWS="$SEARCH_ROWS"
fi

BACKEND_PID=""
cleanup() {
    if [[ -n "$BACKEND_PID" ]]; then
        echo ""
        echo ">>> Stopping perf backend..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

if [[ "${GALLERY_PERF_START_BACKEND:-0}" == "1" ]]; then
    echo ""
    echo ">>> Starting backend for perf smoke tests..."
    if curl -sf "$GALLERY_API_BASE_URL/api/health" >/dev/null; then
        if [[ "${GALLERY_PERF_REUSE_BACKEND:-0}" == "1" ]]; then
            echo ">>> Reusing existing backend at $GALLERY_API_BASE_URL"
        else
            echo "Backend already responds at $GALLERY_API_BASE_URL." >&2
            echo "Set GALLERY_PERF_BACKEND_PORT to a free port, or set GALLERY_PERF_REUSE_BACKEND=1." >&2
            exit 1
        fi
    else
        (
            cd "$REPO_ROOT"
            PATH_SAFETY_ROOT="${PATH_SAFETY_ROOT:-/}" \
            GALLERY_METADATA_DB="${GALLERY_METADATA_DB:-}" \
            GALLERY_THUMBNAIL_CACHE_DIR="${GALLERY_THUMBNAIL_CACHE_DIR:-}" \
            GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=false \
            ENABLE_WARM_INDEXED_LISTING="${ENABLE_WARM_INDEXED_LISTING:-true}" \
            GALLERY_METADATA_INDEXER_ENABLED="${GALLERY_METADATA_INDEXER_ENABLED:-true}" \
            ENABLE_METRICS="${ENABLE_METRICS:-false}" \
            SCAN_PERF_LOGS="${SCAN_PERF_LOGS:-false}" \
            "$PERF_PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
        ) &
        BACKEND_PID=$!
    fi
    for _ in {1..40}; do
        if curl -sf "$GALLERY_API_BASE_URL/api/health" >/dev/null; then
            break
        fi
        sleep 0.25
    done
    curl -sf "$GALLERY_API_BASE_URL/api/health" >/dev/null
fi

if [[ "${GALLERY_PERF_SKIP_BACKEND:-0}" != "1" ]]; then
    echo ""
    echo ">>> Running managed search class benchmarks..."
    "$PERF_PYTHON" "$SCRIPT_DIR/bench_search.py" | tee "$RESULTS_DIR/search-benchmark-report.json"

    echo ""
    echo ">>> Running backend Library Inspector p95 perf test..."
    "$PERF_PYTHON" "$SCRIPT_DIR/perf_library_inspector.py" | tee "$RESULTS_DIR/library-inspector-report.json"

    echo ""
    echo ">>> Running warm listing local perf test..."
    WARM_ARGS=(
        --images "${GALLERY_PERF_WARM_LISTING_IMAGES:-5000}"
        --path "${GALLERY_PERF_WARM_LISTING_PATH:-/tmp/perf_warm_test}"
        --budget-ms "${GALLERY_PERF_WARM_LISTING_BUDGET_MS:-500}"
        --output "$RESULTS_DIR/warm-listing-report.json"
    )
    "$PERF_PYTHON" "$SCRIPT_DIR/perf_warm_listing.py" "${WARM_ARGS[@]}"
fi

if [[ "${GALLERY_PERF_SKIP_FRONTEND:-0}" == "1" ]]; then
    echo ""
    echo ">>> Skipping frontend Playwright perf tests."
    echo ""
    echo ">>> Summarizing perf reports..."
    "$PERF_PYTHON" "$SCRIPT_DIR/summarize_perf_reports.py" --results-dir "$RESULTS_DIR"
    echo ""
    echo "=========================================="
    echo "  Perf smoke tests complete"
    echo "=========================================="
    exit 0
fi

cd "$REPO_ROOT/frontend"

echo ""
echo ">>> Running album open perf test..."
corepack pnpm exec playwright test tests/e2e/perf/album-open.perf.spec.ts --project=chromium "$@"

echo ""
echo ">>> Running lightbox perf tests..."
corepack pnpm exec playwright test tests/e2e/perf/lightbox.perf.spec.ts --project=chromium "$@"

echo ""
echo "Perf JSON results written directly to $RESULTS_DIR/"
ls -la "$RESULTS_DIR/"*.json 2>/dev/null || echo "(no JSON reports found)"

echo ""
echo ">>> Summarizing perf reports..."
"$PERF_PYTHON" "$SCRIPT_DIR/summarize_perf_reports.py" --results-dir "$RESULTS_DIR"

echo ""
echo "=========================================="
echo "  Perf smoke tests complete"
echo "=========================================="
