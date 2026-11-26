#!/bin/bash
set -e
uv run ruff check
uv run bandit -c pyproject.toml -r ultra7/ app.py tests/
uv run mypy --ignore-missing-imports ultra7/ app.py
uv run python -m unittest discover tests
