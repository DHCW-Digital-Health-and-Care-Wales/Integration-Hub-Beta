# Metric Sender Library

Azure Monitor Insights metric sender library for Integration Hub services.

## Overview

This library provides metric sending functionality that sends telemetry data to Azure Monitor Insights using RBAC authentication. When Azure Monitor is not configured, it gracefully falls back to using the standard Python logger. The library uses OpenTelemetry counters to track metrics and can send custom key-value pairs to Azure Application Insights.

## Usage

```python
from metric_sender_lib import MetricSender

# Initialize with workflow and microservice identifiers
metric_sender = MetricSender(
    workflow_id="my-workflow",
    microservice_id="my-service"
)

# Send custom metrics
metric_sender.send_metric("custom_metric_name", 5, {"additional_attr": "value"})

# Convenient wrapper for message received events (uses workflow_id as key with value 1)
metric_sender.send_message_received_metric()
# or with custom attributes
metric_sender.send_message_received_metric({"key": "value"})

# Generic metric sending with default value of 1
metric_sender.send_metric("message_processed")
# Generic metric sending with custom value and attributes
metric_sender.send_metric("message_processed", 3, {"status": "success"})
```

## Environment Variables

- `APPLICATIONINSIGHTS_CONNECTION_STRING`: **Optional**. The connection string for Azure Application Insights.
  - If this environment variable is set, the library will initialize Azure Monitor for metrics telemetry.
  - If this environment variable is not set or is empty, Azure Monitor metrics will be disabled. The library will use the standard Python logger, and metric details will be formatted into the log message.
- `INSIGHTS_UAMI_CLIENT_ID`: **Optional**. The client ID of the User-Assigned Managed Identity to use for authentication with Azure Monitor.
  - If this variable is set, the library will use `ManagedIdentityCredential` to authenticate.
  - If this variable is not set, is empty, or contains only whitespace, the library will fall back to using `DefaultAzureCredential`. This allows for flexible authentication, including local development using Azure CLI credentials or other authentication methods supported by `DefaultAzureCredential`.

## Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

## Build / checks

In the [metric_sender_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit metric_sender_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports metric_sender_lib/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
