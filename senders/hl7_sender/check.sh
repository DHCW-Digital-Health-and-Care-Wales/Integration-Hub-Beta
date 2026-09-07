#!/bin/bash

set -e

uv run ruff check
uv run bandit -r hl7_sender/ tests/
uv run mypy --ignore-missing-imports hl7_sender/ tests/
uv run python -m unittest discover tests