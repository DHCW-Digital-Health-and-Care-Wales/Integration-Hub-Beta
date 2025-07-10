# HL7 MLLP Mock Receiver

Configurable HL7 MLLP server built with hl7apy package used for testing.

Accepted message types:

- "ADT^A31^ADT_A05"
- "ADT^A28^ADT_A05"

A negative ack (NACK) can be produced by having the word `fail` inside the message body.

## Development

### Dependencies

- python3
- pipx - to run code quality checks ([Ruff](https://github.com/astral-sh/ruff), [Bandit](https://github.com/PyCQA/bandit))
- uv

### Build / checks

In the [hl7_mock_receiver](.) folder create a virtual environment:

```
uv venv
```

Install dependencies:

```
uv sync
```

Run code quality checks:

```
pipx run ruff check
pipx run bandit hl7_mock_receiver/**/*.py tests/**/*.py
pipx run mypy --ignore-missing-imports hl7_mock_receiver/**/*.py tests/**/*.py
```

Run unit tests:

```
python -m unittest discover tests
```

## Running HL7 server

You can run the HL7 server directly with python or build docker image and run it in the container.
To define host and port the server should bind to use environment variables configuration.

### Environment variables

- **HOST** - default 127.0.0.1
- **PORT** - default 2576
- **LOG_LEVEL** - default 'INFO'

### Running directly

From the [hl7_mock_receiver](.) folder run:

```sh
python application.py
```

### Runing in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
