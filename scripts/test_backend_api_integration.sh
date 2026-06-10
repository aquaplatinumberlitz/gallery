#!/usr/bin/env bash
set -euo pipefail

echo "=========================================="
echo "  Backend API Integration Tests"
echo "=========================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT/backend"

echo ""
echo ">>> Running API integration tests..."
python -m pytest tests/test_api_integration_health_and_safety.py \
                   tests/test_api_integration_scan.py \
                   tests/test_api_integration_derivatives.py \
                   tests/test_api_integration_metadata_search_facets.py \
                   tests/test_api_integration_index_status.py \
                   -v "$@"

echo ""
echo "=========================================="
echo "  Backend API integration tests complete"
echo "=========================================="
