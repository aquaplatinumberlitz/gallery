#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

legacy_pattern='--(bg-color|text-color|muted-text|primary-color|border-color|surface-color|gallery-surface[^[:space:];,)]*|title-color|bg-secondary|placeholder-bg|photocard-border|album-border-color|folder-color|neon-color)'

# Explicitly approved zones for non-standard visual identity. The current source
# should not need these generic tokens, but keeping the allowlist here documents
# where future exceptions must stay.
allowed_files_regex='^(src/components/(IntroScreen|ToastItem)[.]vue|src/styles/(_lightbox-[^/]+|main)[.]scss)$'

matches="$(rg --line-number --no-heading --glob '!dist/**' --glob '!node_modules/**' -- "$legacy_pattern" src || true)"

violations="$(
  printf '%s\n' "$matches" \
    | awk -F: -v allowed="$allowed_files_regex" 'NF && $1 !~ allowed { print }'
)"

if [[ -n "$violations" ]]; then
  printf 'Forbidden legacy UI color tokens found outside approved brand/toast/effect zones:\n\n' >&2
  printf '%s\n' "$violations" >&2
  exit 1
fi

printf 'No forbidden legacy UI color tokens found.\n'
