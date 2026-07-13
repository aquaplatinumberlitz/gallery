#!/usr/bin/env bash
set -euo pipefail

SUITE="${1:-}"
shift || true

if [[ "$SUITE" != "functional" && "$SUITE" != "perf" ]]; then
    echo "Usage: $0 <functional|perf> [Playwright test paths...]" >&2
    exit 2
fi

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
    TEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/gallery-${SUITE}-XXXXXX")"
    MANAGED_TMP=1
fi

FIXTURE_ROOT="$TEST_TMP/gallery-fixture"
METADATA_DB="$TEST_TMP/gallery.db"
THUMBNAIL_CACHE="$TEST_TMP/thumbnail-cache"
BACKEND_LOG="$TEST_TMP/backend.log"
BACKEND_PID=""

cleanup() {
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ "$MANAGED_TMP" == "1" && "${GALLERY_TEST_KEEP_TMP:-0}" != "1" ]]; then
        rm -rf "$TEST_TMP"
    else
        echo "Test artifacts retained at $TEST_TMP"
    fi
}
trap cleanup EXIT

echo "==> Create deterministic $SUITE fixture"
FIXTURE_ARGS=(
    --root "$FIXTURE_ROOT"
    --album-name a1111
    --images "${GALLERY_TEST_FIXTURE_IMAGES:-30}"
    --metadata-db "$METADATA_DB"
    --thumbnail-cache "$THUMBNAIL_CACHE"
    --clean
)
if [[ "$SUITE" == "perf" ]]; then
    SEARCH_PROFILE="${GALLERY_PERF_SEARCH_PROFILE:-ci}"
    if [[ "$SEARCH_PROFILE" == "scheduled" ]]; then
        SEARCH_ROWS="${GALLERY_PERF_SEARCH_ROWS:-25000}"
    else
        SEARCH_ROWS="${GALLERY_PERF_SEARCH_ROWS:-5000}"
    fi
    FIXTURE_ARGS+=(--search-rows "$SEARCH_ROWS")
    export GALLERY_PERF_SEARCH_ROWS="$SEARCH_ROWS"
fi
"$PYTHON" "$SCRIPTS_DIR/create_perf_fixture.py" \
    "${FIXTURE_ARGS[@]}" >/dev/null

if [[ "$SUITE" == "perf" ]]; then
    echo "==> Validate performance budget registry"
    "$PYTHON" "$SCRIPTS_DIR/check_perf_budgets.py"
fi

echo "==> Start backend fixture on $BACKEND_URL"
(
    cd "$REPO_ROOT"
    PATH_SAFETY_ROOT="$FIXTURE_ROOT" \
    GALLERY_METADATA_DB="$METADATA_DB" \
    GALLERY_THUMBNAIL_CACHE_DIR="$THUMBNAIL_CACHE" \
    GALLERY_CATALOG_STARTUP_CATCHUP_ENABLED=false \
    FRONTEND_PORT="$FRONTEND_PORT" \
    ENABLE_METRICS=false \
    GALLERY_INTEGRITY_CHECK_ENABLED="${GALLERY_INTEGRITY_CHECK_ENABLED:-false}" \
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

if [[ "$SUITE" == "perf" ]]; then
    PERF_RESULTS_DIR="$REPO_ROOT/frontend/test-results/perf"
    mkdir -p "$PERF_RESULTS_DIR"
    echo "==> Run managed search benchmark (${GALLERY_PERF_SEARCH_ROWS} rows)"
    GALLERY_API_BASE_URL="$BACKEND_URL" \
        "$PYTHON" "$SCRIPTS_DIR/bench_search.py" | tee "$PERF_RESULTS_DIR/search-benchmark-report.json"
fi

cd "$REPO_ROOT/frontend"

if [[ "${GALLERY_TEST_SKIP_BUILD:-0}" != "1" ]]; then
    echo "==> Build frontend"
    corepack pnpm run build
fi

export VITE_API_URL="$BACKEND_URL"
export PATH_SAFETY_ROOT_PATH="$FIXTURE_ROOT"
export GALLERY_BASE_URL="$FRONTEND_URL"
export VITE_PORT="$FRONTEND_PORT"
export PLAYWRIGHT_HTML_OPEN=never
if [[ "$SUITE" == "perf" ]]; then
    export GALLERY_PERF_E2E=1
fi

if [[ "$SUITE" == "functional" ]]; then
    if [[ $# -gt 0 ]]; then
        TEST_PATHS=("$@")
    else
        TEST_PATHS=(tests/e2e/*.spec.ts)
    fi
    SHARD_ARGS=()
    if [[ -n "${GALLERY_TEST_SHARD:-}" ]]; then
        SHARD_ARGS=(--shard="$GALLERY_TEST_SHARD")
    fi
    echo "==> Run functional Playwright suite"
    corepack pnpm exec playwright test "${TEST_PATHS[@]}" \
        --project=chromium \
        "${SHARD_ARGS[@]}" \
        --reporter=html
else
    if [[ $# -gt 0 ]]; then
        TEST_PATHS=("$@")
    else
        TEST_PATHS=(tests/e2e/perf)
    fi
    echo "==> Run Playwright performance suite"
    corepack pnpm exec playwright test "${TEST_PATHS[@]}" \
        --project=chromium \
        --workers=1 \
        --reporter=html
fi
