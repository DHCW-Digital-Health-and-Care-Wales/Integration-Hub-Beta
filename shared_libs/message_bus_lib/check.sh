#!/bin/bash

set -e
PACKAGE=message_bus_lib

uv run ruff check
uv run bandit -r $PACKAGE tests/
uv run mypy --ignore-missing-imports $PACKAGE tests
uv run python -m unittest discover tests
