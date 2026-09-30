"""Configuration for the HL7 Mock Receiver service.

Service Bus settings are nullable so the receiver can run standalone (e.g. from the
dev_tools/integration_hub_tester Mock Receiver bar) without a live Service Bus emulator/namespace -
mirrors the same nullable pattern used by the sibling http_mock_receiver service.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    egress_queue_name: str | None
    egress_session_id: str | None
    service_bus_namespace: str | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING", required=False),
            egress_queue_name=_read_env("EGRESS_QUEUE_NAME", required=False),
            egress_session_id=_read_env("EGRESS_SESSION_ID", required=False),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False)
        )

    @property
    def service_bus_enabled(self) -> bool:
        """True when enough Service Bus config is present to attempt forwarding."""
        return bool(self.egress_queue_name and (self.connection_string or self.service_bus_namespace))


def _read_env(name: str, required: bool = False) -> str | None:
    value = os.getenv(name)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(f"Missing required configuration: {name}")
    return value
