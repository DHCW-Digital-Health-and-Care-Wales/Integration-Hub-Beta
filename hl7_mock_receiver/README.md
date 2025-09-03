# HL7 MLLP Mock Receiver

Configurable HL7 MLLP server built with hl7apy package used for testing.

Accepted message types:

- "ADT^A31^ADT_A05"
- "ADT^A28^ADT_A05"
- "ADT^A40^ADT_A39"

A negative ack (NACK) can be produced by having the word `fail` inside the message body.

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [hl7_mock_receiver](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit hl7_mock_receiver/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports hl7_mock_receiver/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```

## Running HL7 server

You can run the HL7 server directly with uv or build docker image and run it in the container.
To define host and port the server should bind to use environment variables configuration.

### Environment variables

- **HOST** - default 127.0.0.1
- **PORT** - default 2576
- **LOG_LEVEL** - default 'INFO'

### Running directly

From the [hl7_mock_receiver](.) folder run:

```bash
python application.py
```

### Running in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
