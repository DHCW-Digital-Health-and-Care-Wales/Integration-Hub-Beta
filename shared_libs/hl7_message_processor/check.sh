#!/bin/bash

set -e
PACKAGE=hl7_message_processor

uv run ruff check
uv run bandit -r $PACKAGE tests/
uv run mypy --ignore-missing-imports $PACKAGE tests
uv run python -m unittest discover tests
