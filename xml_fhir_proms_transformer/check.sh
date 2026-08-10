#!/bin/bash
set -e
uv run ruff check
uv run bandit -r proms_fhir_transformer/ tests/
uv run mypy --ignore-missing-imports proms_fhir_transformer/
uv run python -m unittest discover tests
