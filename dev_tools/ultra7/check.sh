#!/bin/bash
set -e
uv run ruff check
uv run mypy --ignore-missing-imports ultra7/
uv run python -m unittest discover tests
