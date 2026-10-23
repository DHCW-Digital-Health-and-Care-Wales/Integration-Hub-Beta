#!/bin/bash

set -e

uv run ruff check
uv run bandit -r hl7_lims_wrrs_transformer tests/
uv run mypy --ignore-missing-imports hl7_lims_wrrs_transformer
uv run python -m unittest discover tests
