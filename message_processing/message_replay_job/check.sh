#!/bin/bash

set -e
uv sync
uv run ruff check
uv run bandit -r message_replay_job tests/
uv run mypy --ignore-missing-imports message_replay_job
uv run python -m unittest discover tests
