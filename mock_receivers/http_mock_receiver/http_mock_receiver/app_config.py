"""Configuration for the HTTP Mock Receiver service.

All settings are read from environment variables.  Credentials and Service Bus
connection details are nullable so the service can run locally without Azure
infrastructure (log-and-respond only mode).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    host: str
    port: int
    log_level: str
    # Service Bus settings — nullable; when absent the service skips SB forwarding.
    service_bus_connection_string: str | None
    service_bus_namespace: str | None
    egress_queue_name: str | None
    egress_session_id: str | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            host=os.getenv("HOST", "0.0.0.0"),  # nosec B104 - bind all interfaces inside the container
            port=int(os.getenv("PORT", "8080")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            service_bus_connection_string=os.getenv("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=os.getenv("SERVICE_BUS_NAMESPACE"),
            egress_queue_name=os.getenv("EGRESS_QUEUE_NAME"),
            egress_session_id=os.getenv("EGRESS_SESSION_ID"),
        )

    @property
    def service_bus_enabled(self) -> bool:
        """True when enough Service Bus config is present to attempt forwarding."""
        return bool(self.egress_queue_name and (
            self.service_bus_connection_string or self.service_bus_namespace
        ))
