#!/bin/bash
set -e
uv run ruff check
uv run bandit -r workflow_designer/ tests/
uv run mypy --ignore-missing-imports workflow_designer/
uv run pytest
