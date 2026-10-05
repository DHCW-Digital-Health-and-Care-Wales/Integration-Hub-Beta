#!/bin/bash

set -e

uv run ruff check
uv run bandit -r lookup_service/ tests/
uv run mypy --ignore-missing-imports lookup_service/ tests/
uv run python -m unittest discover tests
