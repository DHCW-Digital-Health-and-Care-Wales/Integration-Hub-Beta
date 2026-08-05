#!/bin/bash
set -e
uv run ruff check
uv run bandit -r soap_subscription_sender/ tests/
uv run mypy --ignore-missing-imports soap_subscription_sender/
uv run pytest
