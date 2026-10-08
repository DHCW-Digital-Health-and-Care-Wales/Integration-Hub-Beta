# Transformer Base Library

Standardized framework for building HL7 message transformation services, providing configuration management, Service Bus integration, health checks, and audit logging infrastructure.

## Overview

All Integration Hub transformers (PHW, Chemo, PIMS) inherit from this base library to ensure consistent behavior across services. Instead of each transformer implementing its own Service Bus connectivity, health check endpoints, and audit logging, they extend `BaseTransformer` and implement only their specific transformation logic.

This design promotes:

- **Code reuse**: Common infrastructure is implemented once and shared
- **Consistency**: All transformers behave predictably with standardized audit logs
- **Maintainability**: Infrastructure changes apply to all transformers automatically
- **Rapid development**: New transformers require only domain-specific mapping logic

## Features

- **Standardized interface**: Abstract base class ensures all transformers implement required methods
- **Lifecycle management**: Service Bus connection handling
- **Health check integration**: Built-in TCP health check server for monitoring
- **Audit logging**: Hooks for customizing received/processed/failed event messages
- **Message processing**: Built-in retry logic and error handling for Service Bus messages

## Usage

### Creating a New Transformer

```python
from hl7apy.core import Message
from transformer_base_lib import BaseTransformer

class MyTransformer(BaseTransformer):
    def __init__(self) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("MyTransformer", config_path)

    def transform_message(self, hl7_msg: Message) -> Message:
        """Implement your transformation logic here"""
        new_message = Message(version="2.5")
        # Apply your mappings
        map_msh(hl7_msg, new_message)
        map_pid(hl7_msg, new_message)

        return new_message
```

### Running a Transformer

```python
# application.py
from .my_transformer import MyTransformer

def main() -> None:
    transformer = MyTransformer()
    transformer.run()  # Handles everything: Service Bus, health checks, processing loop

if __name__ == "__main__":
    main()
```

### Configuration

Create a `config.ini` file in your transformer directory:

```ini
[DEFAULT]
MAX_BATCH_SIZE = 10
```

Set environment variables for Service Bus connectivity:

```bash
CONNECTION_STRING=Endpoint=sb://...
INGRESS_QUEUE_NAME=phw-inbound
EGRESS_QUEUE_NAME=mpi-inbound
WORKFLOW_ID=phw-to-mpi
MICROSERVICE_ID=phw-transformer
HEALTH_CHECK_PORT=9000
```

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [transformer_base_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run code quality checks:

```bash
uv run ruff check
uv run bandit transformer_base_lib/**/*.py tests/**/*.py
uv run mypy --ignore-missing-imports transformer_base_lib/**/*.py tests/**/*.py
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
