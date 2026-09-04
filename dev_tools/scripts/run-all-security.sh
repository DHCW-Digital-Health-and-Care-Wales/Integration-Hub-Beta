#!/bin/bash
# Runs security checks (bandit static analysis + uv dependency audit) for every
# component in the repo, mirroring the per-app check.sh / pr-validation.yml convention.
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

# `uv audit` is a newer/experimental subcommand — older uv installs don't have it.
HAS_UV_AUDIT=1
uv audit --help >/dev/null 2>&1 || HAS_UV_AUDIT=0
if [ $HAS_UV_AUDIT -eq 0 ]; then
  echo "warning: this uv install has no 'audit' subcommand (upgrade uv for dependency vulnerability scanning) — skipping" >&2
fi

FAILED=()

for d in "${APP_DIRS[@]}"; do
  echo ""
  echo "=== $d ==="
  bandit_dir="$(basename "$d")"
  app_failed=0
  (
    cd "$ROOT_DIR/$d" || exit 1
    if [ -d "tests" ]; then
      uv tool run bandit -r "$bandit_dir" tests --severity-level medium
    else
      uv tool run bandit -r "$bandit_dir" --severity-level medium
    fi
  )
  [ $? -ne 0 ] && app_failed=1

  if [ $HAS_UV_AUDIT -eq 1 ]; then
    # Known no-fix advisory for a transitive Pygments dependency; review periodically.
    ( cd "$ROOT_DIR/$d" && uv audit --locked --ignore GHSA-5239-wwwm-4pmq )
    [ $? -ne 0 ] && app_failed=1
  fi

  if [ $app_failed -ne 0 ]; then
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
