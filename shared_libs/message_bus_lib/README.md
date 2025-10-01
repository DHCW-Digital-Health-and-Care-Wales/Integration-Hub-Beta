# Azure Service Bus Helper Library

A lightweight Python wrapper library for Azure Service Bus operations, designed for healthcare message processing integration workflows with built-in audit logging and retry mechanisms.

## Features

- **Simplified Service Bus Operations**: Easy-to-use clients for sending and receiving messages
- **Flexible Authentication**: Support for both connection strings and Azure credential-based authentication
- **Built-in Audit Logging**: Comprehensive event tracking with structured audit events
- **Automatic Retry Logic**: Exponential backoff for message processing failures

### Error Handling

- **Automatic Retries**: Up to 3 attempts for transient failures
- **Exponential Backoff**: 5s → 10s → 15min delays for processing failures

## Quick Start

### Installation

```bash
uv add message-bus-lib
```

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [message_bus_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

### Quality Checks

```bash
uv run ruff check
uv run bandit message_bus_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports message_bus_lib/**/*.py tests/**/*.py
```

### Unit tests

```bash
uv run python -m unittest discover tests
```
