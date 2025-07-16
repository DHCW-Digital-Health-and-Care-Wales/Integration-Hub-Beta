# Container App Health Check

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [health_check_lib](.) folder, install dependencies and create virtual environment:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit health_check_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports health_check_lib/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
