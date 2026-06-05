#!/bin/bash
set -e
uv run ruff check
uv run bandit -r replay_browser/ tests/
uv run mypy --ignore-missing-imports replay_browser/
uv run python -m unittest discover tests
