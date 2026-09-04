#!/bin/bash
# Runs mypy for every component in the repo, mirroring the pr-validation.yml
# pipeline's MyPy step (uv tool run mypy <package> tests --ignore-missing-imports).
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
  target_dir="$(basename "$d")"
  (
    cd "$ROOT_DIR/$d" || exit 1
    # Not every component follows the outer-dir/inner-package-of-the-same-name
    # layout (e.g. flat my_tools/* scripts) — fall back to scanning "." for those.
    [ -d "$target_dir" ] || target_dir="."
    # Pin the tool env to Python 3.13 (the repo's target version) so mypy doesn't
    # misreport modern syntax (e.g. PEP 604 unions) as errors under an older default.
    if [ -d "tests" ]; then
      uv tool run --python 3.13 mypy "$target_dir" tests --ignore-missing-imports
    else
      uv tool run --python 3.13 mypy "$target_dir" --ignore-missing-imports
    fi
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
