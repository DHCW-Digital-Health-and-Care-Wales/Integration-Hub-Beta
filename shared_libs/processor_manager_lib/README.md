# Processor Manager Library

A lightweight Python library for managing long-running message processing services with graceful shutdown handling.

## Overview

The Processor Manager library provides a simple interface for managing the lifecycle of message processing applications. It handles Unix signal management (SIGTERM, SIGINT) to enable graceful shutdowns when services are stopped or interrupted.

## Features

- **Signal Handling**: Automatic handling of SIGTERM and SIGINT signals for graceful shutdown
- **Simple API**: Easy-to-use interface for checking running state

## Usage

### With Service Bus Message Processing

```python
from processor_manager_lib import ProcessorManager
from message_bus_lib import ServiceBusClientFactory

processor_manager = ProcessorManager()
receiver = ServiceBusClientFactory.create_receiver(...)

while processor_manager.is_running:
    messages = receiver.receive_messages(max_wait_time=5)
    for message in messages:
        process_message(message)
        receiver.complete_message(message)

# Graceful shutdown
receiver.close()
```

## How It Works

The `ProcessorManager` class:

1. Sets up signal handlers for SIGTERM (graceful shutdown) and SIGINT (Ctrl+C)
2. Maintains an internal `_running` flag
3. When a shutdown signal is received, sets `_running` to False
4. Applications check `is_running` property in their main loop
5. When False, the loop exits and cleanup can occur

This allows containerized applications to shut down gracefully when stopped by orchestrators like Azure Container Apps.

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the processor_manager_lib folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

### Unit tests

```bash
uv run python -m unittest discover tests
```
