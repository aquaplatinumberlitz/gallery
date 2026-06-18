#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Backend tests with coverage
BACKEND_PYTHON="${PYTHON:-python}"
if [[ -x "$REPO_ROOT/backend/.venv_linux/bin/python" ]]; then
    BACKEND_PYTHON="$REPO_ROOT/backend/.venv_linux/bin/python"
fi

cd "$REPO_ROOT"

echo "==> Backend pytest"
"$BACKEND_PYTHON" -m pytest backend/tests/ -q \
    --cov=backend \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-fail-under=85 \
    "$@"

# Frontend unit + build
cd "$REPO_ROOT/frontend"

echo "==> Frontend vitest"
corepack pnpm run test:unit

echo "==> Frontend build"
corepack pnpm run build
