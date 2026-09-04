#!/bin/bash

set -e

uv run ruff check
uv run bandit -r rest_server/ tests/
uv run mypy --ignore-missing-imports rest_server/ tests/
uv run python -m unittest discover tests
