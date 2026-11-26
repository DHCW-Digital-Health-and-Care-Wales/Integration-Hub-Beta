#!/usr/bin/env bash
# Mirror Azure DevOps CI code quality and test gates for a single Python app/lib.
# Usage: bash .agents/skills/pr-quality-gate/scripts/check-app.sh <app_dir> [pkg_dir]

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <app_dir> [pkg_dir]" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
APP_DIR="${1%/}"
PKG_DIR="${2:-$(basename "$APP_DIR")}"
TARGET_DIR="$REPO_ROOT/$APP_DIR"

if [ ! -d "$TARGET_DIR" ]; then
  echo "ERROR: Directory not found: $TARGET_DIR" >&2
  exit 2
fi

cd "$TARGET_DIR"

echo "=== PR Quality Gate: $APP_DIR (package: $PKG_DIR) ==="

echo "[1/5] Ruff..."
uv run ruff check .

echo "[2/5] Bandit (medium+ severity)..."
if [ -d "tests" ]; then
  uv run bandit -r "$PKG_DIR" tests --severity-level medium
else
  uv run bandit -r "$PKG_DIR" --severity-level medium
fi

echo "[3/5] uv audit (--locked)..."
if [ -f "uv.lock" ]; then
  uv audit --locked --ignore GHSA-5239-wwwm-4pmq
else
  echo "Skipping uv audit (no uv.lock)"
fi

echo "[4/5] MyPy (package + tests)..."
if [ -d "tests" ]; then
  uv run mypy "$PKG_DIR" tests --ignore-missing-imports
else
  uv run mypy "$PKG_DIR" --ignore-missing-imports
fi

echo "[5/5] Unit tests..."
if [ -d "tests" ]; then
  case "$APP_DIR" in
    dashboard|mock_receivers/http_mock_receiver)
      uv run pytest tests -v
      ;;
    *)
      uv run python -m unittest discover tests -v
      ;;
  esac
else
  echo "No tests/ directory, skipping unit tests."
fi

if command -v node >/dev/null 2>&1; then
  JS_FILES=$(git -C "$REPO_ROOT" diff --name-only -- "$APP_DIR/**/*.js" "$APP_DIR/*.js" 2>/dev/null || true)
  if [ -n "$JS_FILES" ]; then
    echo "[JS] Checking modified JavaScript syntax..."
    while IFS= read -r js_file; do
      [ -f "$REPO_ROOT/$js_file" ] && node --check "$REPO_ROOT/$js_file"
    done <<< "$JS_FILES"
    echo "JS syntax OK"
  fi
fi

echo "=== PASSED: $APP_DIR ==="
