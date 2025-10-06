#!/bin/bash

set -e

uv run ruff check
uv run bandit -r hl7_phw_transformer tests/
uv run mypy --ignore-missing-imports hl7_phw_transformer
uv run python -m unittest discover tests
