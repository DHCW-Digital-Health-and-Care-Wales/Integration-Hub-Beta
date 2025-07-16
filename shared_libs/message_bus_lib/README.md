# Azure Service Bus helper library

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [message_bus_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit message_bus_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports message_bus_lib/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
