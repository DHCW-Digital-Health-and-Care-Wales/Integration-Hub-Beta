#!/bin/bash

set -e

uv run ruff check
uv run bandit -r hl7_core_reference_transformer tests/
uv run mypy --ignore-missing-imports hl7_core_reference_transformer
uv run python -m unittest discover tests
