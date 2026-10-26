#!/bin/bash

set -e

uv run ruff check
uv run bandit -r db_sender/ tests/
uv run mypy --ignore-missing-imports db_sender/ tests/
uv run python -m unittest discover tests
