#!/bin/bash
set -e
uv run ruff check
uv run bandit -r fhir_sender/ tests/
uv run mypy --ignore-missing-imports fhir_sender/ tests/
uv run python -m unittest discover tests
