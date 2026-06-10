#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Deterministic Test Suite"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ---- Backend API integration tests ----
echo ""
echo "--- Backend API Integration Tests ---"
bash "$SCRIPT_DIR/test_backend_api_integration.sh" "$@"

# ---- Frontend build and Playwright contract tests ----
echo ""
echo "--- Frontend Contract Tests ---"
bash "$SCRIPT_DIR/test_frontend_contract.sh" "$@"

echo ""
echo "=========================================="
echo "  All deterministic tests complete"
echo "=========================================="
echo ""
echo "  NOTE: Perf smoke tests are separate and require a running app."
echo "  Run: bash scripts/test_perf_smoke.sh"
