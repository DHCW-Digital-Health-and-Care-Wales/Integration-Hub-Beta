#!/bin/bash
# Runs ruff check for every component in the repo, mirroring the per-app
# check.sh convention (uv run ruff check).
# Written for bash 3.2 (macOS default) — no mapfile/readarray.
set -o pipefail

# Two levels up: dev_tools/scripts/ -> dev_tools/ -> repo root.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Discover every component with a pyproject.toml, skipping virtual envs
# and egg-info build artefacts.
APP_DIRS=()
while IFS= read -r d; do
  APP_DIRS+=("$d")
done < <(
  find . -maxdepth 3 -name pyproject.toml \
    -not -path "*/.venv/*" -not -path "*/node_modules/*" \
    | xargs -n1 dirname \
    | sed 's|^\./||' \
    | sort
)

FAILED=()

for d in "${APP_DIRS[@]}"; do
  echo ""
  echo "=== $d ==="
  ( cd "$ROOT_DIR/$d" && uv run ruff check . )
  if [ $? -ne 0 ]; then
    FAILED+=("$d")
  fi
done

echo ""
echo "===================="
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "ALL PASSED"
  exit 0
else
  echo "FAILED: ${FAILED[*]}"
  exit 1
fi
