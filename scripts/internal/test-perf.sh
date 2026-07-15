#!/usr/bin/env bash
set -uo pipefail

INTERNAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(dirname "$INTERNAL_DIR")"
REPO_ROOT="$(dirname "$SCRIPTS_DIR")"

if [[ -x "$REPO_ROOT/backend/venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/backend/venv/bin/python"
elif [[ -x "$REPO_ROOT/backend/.venv_linux/bin/python" ]]; then
    PYTHON="$REPO_ROOT/backend/.venv_linux/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

free_port() {
    "$PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

BACKEND_PORT="${GALLERY_TEST_BACKEND_PORT:-$(free_port)}"
FRONTEND_PORT="${GALLERY_TEST_FRONTEND_PORT:-$(free_port)}"
BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
FRONTEND_URL="http://127.0.0.1:$FRONTEND_PORT"

MANAGED_TMP=0
if [[ -n "${GALLERY_TEST_TMPDIR:-}" ]]; then
    TEST_TMP="$GALLERY_TEST_TMPDIR"
    mkdir -p "$TEST_TMP"
else
    TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/gallery-perf-XXXXXX")"
    MANAGED_TMP=1
fi

FIXTURE_ROOT="$TEST_TMP/gallery-fixture"
METADATA_DB="$TEST_TMP/gallery.db"
THUMBNAIL_CACHE="$TEST_TMP/thumbnail-cache"
BACKEND_LOG="$TEST_TMP/backend.log"
PERF_RESULTS_DIR="$TEST_TMP/perf-reports"
PLAYWRIGHT_OUTPUT_DIR="$TEST_TMP/playwright-results"
PLAYWRIGHT_REPORT_DIR="$TEST_TMP/playwright-report"
BACKEND_PID=""
FAILURES=()

cleanup() {
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ "$MANAGED_TMP" == "1" && "${GALLERY_TEST_KEEP_TMP:-0}" != "1" ]]; then
        rm -rf "$TEST_TMP"
    else
        echo "Performance artifacts retained at $TEST_TMP"
    fi
}
trap cleanup EXIT

record_failure() {
    FAILURES+=("$1")
    echo "PERF FAILURE: $1" >&2
}

run_json_workload() {
    local label="$1"
    local report="$2"
    shift 2
    echo "==> Run $label"
    if "$@" | tee "$PERF_RESULTS_DIR/$report"; then
        return 0
    fi
    record_failure "$label"
    return 0
}

rm -rf "$PERF_RESULTS_DIR" "$PLAYWRIGHT_OUTPUT_DIR" "$PLAYWRIGHT_REPORT_DIR"
mkdir -p "$PERF_RESULTS_DIR" "$PLAYWRIGHT_OUTPUT_DIR" "$PLAYWRIGHT_REPORT_DIR"

SEARCH_PROFILE="${GALLERY_PERF_SEARCH_PROFILE:-ci}"
if [[ "$SEARCH_PROFILE" == "scheduled" ]]; then
    SEARCH_ROWS="${GALLERY_PERF_SEARCH_ROWS:-25000}"
else
    SEARCH_ROWS="${GALLERY_PERF_SEARCH_ROWS:-5000}"
fi
RELATED_ROWS="${GALLERY_PERF_RELATED_ROWS:-100000}"

echo "==> Create deterministic performance fixture"
if ! "$PYTHON" "$SCRIPTS_DIR/create_perf_fixture.py" \
    --root "$FIXTURE_ROOT" \
    --album-name a1111 \
    --images "${GALLERY_TEST_FIXTURE_IMAGES:-30}" \
    --metadata-db "$METADATA_DB" \
    --thumbnail-cache "$THUMBNAIL_CACHE" \
    --search-rows "$RELATED_ROWS" \
    --search-cohort-rows "$SEARCH_ROWS" \
    --related-assets \
    --clean >/dev/null; then
    echo "Unable to create performance fixture" >&2
    exit 1
fi

echo "==> Validate performance workload and budget registry"
if ! "$PYTHON" "$SCRIPTS_DIR/check_perf_budgets.py"; then
    exit 1
fi

echo "==> Start backend fixture on $BACKEND_URL"
(
    cd "$REPO_ROOT"
    PATH_SAFETY_ROOT="$FIXTURE_ROOT" \
    GALLERY_METADATA_DB="$METADATA_DB" \
    GALLERY_THUMBNAIL_CACHE_DIR="$THUMBNAIL_CACHE" \
    GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=false \
    GALLERY_SEARCH_INDEXER_ENABLED=false \
    GALLERY_METADATA_INDEXER_ENABLED=false \
    GALLERY_DERIVATIVE_RECONCILE_ENABLED=false \
    GALLERY_CATALOG_SERVICE_ENABLED=false \
    GALLERY_CATALOG_RECONCILE_ENABLED=false \
    GALLERY_CATALOG_WATCHER_ENABLED=false \
    GALLERY_INTEGRITY_CHECK_ENABLED=false \
    FRONTEND_PORT="$FRONTEND_PORT" \
    ENABLE_METRICS=false \
    "$PYTHON" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

for _ in {1..60}; do
    if curl --fail --silent "$BACKEND_URL/api/health" >/dev/null; then
        break
    fi
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        cat "$BACKEND_LOG" >&2
        exit 1
    fi
    sleep 0.5
done
if ! curl --fail --silent "$BACKEND_URL/api/health" >/dev/null; then
    cat "$BACKEND_LOG" >&2
    exit 1
fi

export GALLERY_PERF_RESULTS_DIR="$PERF_RESULTS_DIR"
export GALLERY_PERF_SEARCH_ROWS="$SEARCH_ROWS"
export GALLERY_PERF_RELATED_ROWS="$RELATED_ROWS"
export GALLERY_PERF_ALBUM_NAME="a1111"
export GALLERY_PERF_ALBUM_PATH="$FIXTURE_ROOT/a1111"
export GALLERY_PERF_SCAN_PATH="$FIXTURE_ROOT/a1111"

run_json_workload "managed search benchmark ($SEARCH_ROWS rows)" "search-benchmark-report.json" \
    env GALLERY_API_BASE_URL="$BACKEND_URL" GALLERY_PERF_INSPECTOR_QUERY=perf_0000 \
    "$PYTHON" "$SCRIPTS_DIR/bench_search.py"

run_json_workload "Library Inspector API benchmark ($RELATED_ROWS rows)" "library-inspector-report.json" \
    env GALLERY_API_BASE_URL="$BACKEND_URL" GALLERY_PERF_INSPECTOR_QUERY=perf_0000 \
    GALLERY_PERF_INSPECTOR_MIN_ROWS=1 GALLERY_PERF_INSPECTOR_MIN_TOTAL_INDEXED="$RELATED_ROWS" \
    "$PYTHON" "$SCRIPTS_DIR/perf_library_inspector.py"

run_json_workload "Library Inspector store benchmark ($RELATED_ROWS rows)" "inspector-store-report.json" \
    env GALLERY_METADATA_DB="$METADATA_DB" GALLERY_PERF_INSPECTOR_MIN_TOTAL_INDEXED="$RELATED_ROWS" \
    "$PYTHON" "$SCRIPTS_DIR/perf_inspector_store.py"

run_json_workload "facets benchmark ($RELATED_ROWS rows)" "facets-report.json" \
    env GALLERY_API_BASE_URL="$BACKEND_URL" "$PYTHON" "$SCRIPTS_DIR/perf_facets.py"

run_json_workload "Related Assets benchmark ($RELATED_ROWS rows)" "related-assets-benchmark-report.json" \
    env GALLERY_API_BASE_URL="$BACKEND_URL" GALLERY_METADATA_DB="$METADATA_DB" \
    GALLERY_PERF_ALBUM_PATH="$FIXTURE_ROOT/a1111" GALLERY_PERF_RELATED_ROWS="$RELATED_ROWS" \
    "$PYTHON" "$SCRIPTS_DIR/bench_related_assets.py"

run_json_workload "preview cold/warm benchmark" "preview-benchmark-report.json" \
    env GALLERY_API_BASE_URL="$BACKEND_URL" GALLERY_PERF_BENCH_PREVIEW_FOLDER="$FIXTURE_ROOT/a1111" \
    "$PYTHON" "$SCRIPTS_DIR/bench_preview.py"

run_json_workload "thumbnail cold/warm benchmark" "thumbnail-benchmark-report.json" \
    env GALLERY_API_BASE_URL="$BACKEND_URL" GALLERY_PERF_BENCH_THUMBNAIL_FOLDER="$FIXTURE_ROOT/a1111" \
    GALLERY_PERF_BENCH_THUMBNAIL_SAMPLES="${GALLERY_TEST_FIXTURE_IMAGES:-30}" \
    GALLERY_PERF_BENCH_THUMBNAIL_MAX_LONG_EDGE=128 \
    "$PYTHON" "$SCRIPTS_DIR/bench_thumbnail.py"

echo "==> Build production frontend for browser performance tests"
export VITE_API_URL="$BACKEND_URL"
export VITE_PORT="$FRONTEND_PORT"
if ! (cd "$REPO_ROOT/frontend" && corepack pnpm run build); then
    record_failure "production frontend build"
else
    export PATH_SAFETY_ROOT_PATH="$FIXTURE_ROOT"
    export GALLERY_BASE_URL="$FRONTEND_URL"
    export GALLERY_PERF_E2E=1
    export PLAYWRIGHT_RETRIES=0
    export GALLERY_PLAYWRIGHT_OUTPUT_DIR="$PLAYWRIGHT_OUTPUT_DIR"
    export GALLERY_PLAYWRIGHT_REPORT_DIR="$PLAYWRIGHT_REPORT_DIR"
    echo "==> Run production Playwright performance suite"
    if ! (cd "$REPO_ROOT/frontend" && corepack pnpm exec playwright test --config=playwright.perf.config.ts "$@"); then
        record_failure "production Playwright performance suite"
    fi
fi

echo "==> Validate expected performance reports"
if ! "$PYTHON" "$SCRIPTS_DIR/validate_perf_reports.py" --results-dir "$PERF_RESULTS_DIR" --suite ci; then
    record_failure "performance report contract"
fi

echo "==> Summarize performance reports"
if ! "$PYTHON" "$SCRIPTS_DIR/summarize_perf_reports.py" \
    --results-dir "$PERF_RESULTS_DIR" \
    --fail-on-regression; then
    record_failure "performance report summary"
fi

if [[ ${#FAILURES[@]} -gt 0 ]]; then
    echo "Performance suite failed (${#FAILURES[@]} boundaries): ${FAILURES[*]}" >&2
    exit 1
fi

echo "Performance suite passed; reports: $PERF_RESULTS_DIR"
