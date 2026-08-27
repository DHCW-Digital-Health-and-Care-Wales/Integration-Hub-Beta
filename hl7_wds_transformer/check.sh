#!/bin/bash
set -e
uv run ruff check
uv run bandit -r hl7_wds_transformer/ tests/
uv run mypy --ignore-missing-imports hl7_wds_transformer/
uv run pytest
