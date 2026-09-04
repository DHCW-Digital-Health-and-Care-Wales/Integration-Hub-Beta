#!/bin/bash
set -e
uv run ruff check
uv run bandit -r http_mock_receiver/ tests/
uv run mypy --ignore-missing-imports http_mock_receiver/
uv run pytest
