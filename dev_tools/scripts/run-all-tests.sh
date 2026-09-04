#!/bin/bash
# Runs unit tests for every service and shared lib in the repo, mirroring
# the per-app check.sh convention (uv sync + unittest discover tests).
# Written for bash 3.2 (macOS default) — no mapfile/readarray.
set -o pipefail

# Two levels up: dev_tools/scripts/ -> dev_tools/ -> repo root.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

# Discover every component with both a pyproject.toml and a tests/ directory,
# skipping virtual envs and egg-info build artefacts.
APP_DIRS=()
while IFS= read -r d; do
  APP_DIRS+=("$d")
done < <(
  find . -maxdepth 3 -name pyproject.toml \
    -not -path "*/.venv/*" -not -path "*/node_modules/*" \
    | xargs -n1 dirname \
    | while read -r d; do [ -d "$d/tests" ] && echo "$d"; done \
    | sed 's|^\./||' \
    | sort
)

FAILED=()

for d in "${APP_DIRS[@]}"; do
  echo ""
  echo "=== $d ==="
  (
    cd "$ROOT_DIR/$d" || exit 1
    # --reinstall bypasses uv's build cache, which otherwise can serve stale
    # wheels for local shared_libs/ path dependencies after they change.
    uv sync --locked --all-groups --reinstall && uv run python -m unittest discover tests -v
  )
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
