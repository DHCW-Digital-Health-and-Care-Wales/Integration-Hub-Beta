#!/bin/bash
set -e

uv run ruff check
uv run bandit -r lims_trrr_mapper/ tests/
uv run mypy --ignore-missing-imports lims_trrr_mapper/ tests/
uv run python -m unittest discover tests
