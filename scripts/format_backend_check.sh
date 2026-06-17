#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -x backend/venv/bin/python ]]; then
  PYTHON=backend/venv/bin/python
elif [[ -x backend/.venv_linux/bin/python ]]; then
  PYTHON=backend/.venv_linux/bin/python
else
  PYTHON=python
fi

base_ref="${RUFF_BASE:-}"
if [[ -z "$base_ref" ]] && git rev-parse --verify --quiet origin/main >/dev/null; then
  base_ref="origin/main"
fi

mapfile -t files < <(
  {
    if [[ -n "$base_ref" ]]; then
      git diff --name-only --diff-filter=ACMR "$base_ref"...HEAD -- backend scripts start.py
    fi
    git diff --name-only --diff-filter=ACMR HEAD -- backend scripts start.py
    git ls-files --others --exclude-standard -- backend scripts start.py
  } | sort -u | grep -E '^((backend|scripts)/.*|start)\.py$' || true
)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No changed backend Python files to format-check."
  exit 0
fi

"$PYTHON" -m ruff format --check "${files[@]}"
