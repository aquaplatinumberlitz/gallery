#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

base_ref="${PRETTIER_BASE:-}"
if [[ -z "$base_ref" ]] && git rev-parse --verify --quiet origin/main >/dev/null; then
  base_ref="origin/main"
fi

mapfile -t files < <(
  {
    if [[ -n "$base_ref" ]]; then
      git diff --name-only --diff-filter=ACMR --relative "$base_ref"...HEAD -- .
    fi
    git diff --name-only --diff-filter=ACMR --relative HEAD -- .
    git ls-files --others --exclude-standard -- .
  } | sort -u | grep -E '\.(css|html|js|json|scss|ts|vue)$' || true
)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No changed frontend files to check."
  exit 0
fi

prettier --check "${files[@]}"
