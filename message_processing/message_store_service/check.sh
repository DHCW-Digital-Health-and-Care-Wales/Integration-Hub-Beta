#!/bin/bash

set -e

uv run ruff check
uv run bandit -r message_store_service tests/
uv run mypy --ignore-missing-imports message_store_service
uv run python -m unittest discover tests
