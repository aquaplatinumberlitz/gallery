#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Backend Ruff lint"
"$SCRIPT_DIR/lint_backend.sh"

echo "==> Backend Ruff format check"
"$SCRIPT_DIR/format_backend_check.sh"

cd "$SCRIPT_DIR/../frontend"

echo "==> Frontend ESLint"
corepack pnpm run lint

echo "==> Frontend Prettier check"
corepack pnpm run format:check
