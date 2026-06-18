#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
if [[ -x "$REPO_ROOT/backend/.venv_linux/bin/python" ]]; then
    BACKEND_PYTHON="$REPO_ROOT/backend/.venv_linux/bin/python"
else
    BACKEND_PYTHON="${PYTHON:-python}"
fi

echo "==> Backend Ruff lint"
"$SCRIPT_DIR/lint_backend.sh"

echo "==> Backend Ruff format check"
"$SCRIPT_DIR/format_backend_check.sh"

echo "==> Backend pytest"
cd "$REPO_ROOT"
"$BACKEND_PYTHON" -m pytest backend/tests/ -q \
    --cov=backend \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-fail-under=85 \
    "$@"
