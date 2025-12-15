# Azure Monitor Library

A centralized library for Azure Monitor initialization used across Integration Hub shared libraries.

## Purpose

This library provides a single factory for Azure Monitor initialization to prevent duplicate initialization and logging when multiple shared libraries (event_logger_lib, metric_sender_lib, etc.) are used in the same application.

## Usage

```python
from azure_monitor_lib import AzureMonitorFactory

# Ensure Azure Monitor is initialized
success = AzureMonitorFactory.ensure_initialized()

# Get meter for metrics
meter = AzureMonitorFactory.get_meter()

# Check if Azure Monitor is enabled
enabled = AzureMonitorFactory.is_enabled()
```

## Dependencies

- azure-identity
- azure-monitor-opentelemetry
- opentelemetry-api
- opentelemetry-sdk
