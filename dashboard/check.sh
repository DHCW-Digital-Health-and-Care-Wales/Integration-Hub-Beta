#!/bin/bash
set -e
uv run ruff check
uv run bandit -r dashboard/ tests/
uv run mypy --ignore-missing-imports dashboard/
uv run pytest
