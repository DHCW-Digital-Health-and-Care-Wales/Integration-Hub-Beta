# Health Check Library

TCP-based health monitoring for Azure Container Apps, enabling load balancers and orchestration platforms to verify service availability through simple socket connections.

## Overview

Unlike HTTP-based health checks that return JSON responses, this library uses a simpler TCP approach. It opens a socket and accepts connections. When external monitoring systems successfully connect, the application is healthy.

This design integrates seamlessly with Azure's infrastructure:

- **Container orchestration** - Azure Container Apps can restart unhealthy instances
- **Application monitoring** - Operations teams can verify service status

## Features

- **Lightweight**: No HTTP overhead, just TCP socket connections
- **Configurable endpoints**: Custom host/port (defaults: `127.0.0.1:9000`)

## Usage

### Basic Usage

```python
from health_check_lib.health_check_server import TCPHealthCheckServer

# Use with context manager for automatic cleanup
with TCPHealthCheckServer("127.0.0.1", 9000) as health_check_server:
    health_check_server.start()
    # Your application logic here
    # Health check runs in background thread
```

### Real-World Example from hl7_server

```python
from health_check_lib.health_check_server import TCPHealthCheckServer

class Hl7ServerApplication:
    def start_server(self) -> None:
        app_config = AppConfig.read_env_config()

        # Initialize health check server
        self.health_check_server = TCPHealthCheckServer(
            app_config.health_check_hostname,
            app_config.health_check_port
        )

        try:
            # Start MLLP server
            self._server.serve_forever()
            # Start health check in background
            self.health_check_server.start()
        except Exception as e:
            logger.exception("Server error: %s", e)
            self.stop_server()
            raise

    def stop_server(self) -> None:
        if self.health_check_server:
            self.health_check_server.stop()
            logger.info("Health check server shut down.")
```

## Development

### Dependencies

- [uv](https://docs.astral.sh/uv/) - Python package and project manager
- macOS: `brew install uv`
- Other platforms: See [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

### Build / checks

In the [health_check_lib](.) folder, to create a virtual environment and install project dependencies:

```bash
uv sync
```

Run unit tests:

```bash
uv run python -m unittest discover tests
```
