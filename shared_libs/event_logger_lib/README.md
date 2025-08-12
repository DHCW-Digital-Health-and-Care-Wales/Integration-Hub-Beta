# Event Logger Library

Azure Monitor Insights event logging library for Integration Hub services.

## Overview

This library provides event logging functionality that sends telemetry data to Azure Monitor Insights using RBAC authentication.

## Usage

```python
from event_logger_lib import EventLogger, EventType

# Initialize with workflow and microservice identifiers
event_logger = EventLogger(
    workflow_id="my-workflow",
    microservice_id="my-service"
)

# Log various events
event_logger.log_message_received("HL7 message content")
event_logger.log_message_processed("HL7 message content", "Processing successful")
event_logger.log_message_failed("HL7 message content", "Error details")
```

## Environment Variables

- `APPLICATIONINSIGHTS_CONNECTION_STRING`: **Required** to enable event logging. If this environment variable is not set or is empty, event logging will be disabled. This should contain the Application Insights connection string with the instrumentation key and ingestion endpoint.
- `INSIGHTS_UAMI_CLIENT_ID`: **Optional**. The client ID of the User-Assigned Managed Identity to use for authentication.
  - If this variable is set, the library will use `ManagedIdentityCredential` to authenticate with Azure.
  - If this variable is not set, is empty, or contains only whitespace, the library will fall back to using `DefaultAzureCredential`. This allows for flexible authentication, including local development using Azure CLI credentials or other authentication methods supported by `DefaultAzureCredential`.

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [event_logger_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit event_logger_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports event_logger_lib/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
