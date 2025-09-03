# HL7 Sender

HL7 Sender Service is a message delivery service that subscribes to transformed HL7 messages from the message bus and reliably delivers them to target systems (e.g., MPI - Master Patient Index). Handles connection management, retries, delivery acknowledgements, and error reporting to ensure end-to-end message delivery.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_sender](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_sender/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_sender/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
