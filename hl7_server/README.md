# HL7 MLLP server

Configurable HL7 MLLP server built with hl7apy package.

## Development

### Dependencies

- python3
- pipx - to run code quality checks ([Ruff](https://github.com/astral-sh/ruff), [Bandit](https://github.com/PyCQA/bandit))

### Build / checks

In the [hl7_server](.) folder create virtual environment and start using it:
```
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:
```
pip install -r requirements.txt
```

Run code quality checks:
```
pipx run ruff check
pipx run bandit hl7_server/**/*.py tests/**/*.py
pipx run mypy --ignore-missing-imports hl7_server/**/*.py tests/**/*.py
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
- **PORT** - default 2575
- **LOG_LEVEL** - default 'INFO'

### Running directly

From the [hl7_server](.) folder run:
```sh
python application.py
```

### Runing in docker

You can build the docker image with provided [Dockerfile](./Dockerfile) or you can run selected workflow
using Docker compose configuration in [local](../local/README.md).
