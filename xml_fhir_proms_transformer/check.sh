#!/bin/bash
set -e
uv run ruff check
uv run bandit -r xml_fhir_proms_transformer/ tests/
uv run mypy --ignore-missing-imports xml_fhir_proms_transformer/
uv run python -m unittest discover tests
