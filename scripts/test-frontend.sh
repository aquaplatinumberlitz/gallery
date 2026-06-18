#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT/frontend"

echo "==> Frontend lint"
corepack pnpm run lint

echo "==> Frontend unit tests"
corepack pnpm run test:unit

echo "==> Frontend build"
corepack pnpm run build
