"""Configuration for the HL7 Topic Mock Receiver service.

Service Bus settings are nullable so the receiver can run standalone (e.g. from the
dev_tools/integration_hub_tester Mock Receiver bar) without a live Service Bus emulator/namespace -
mirrors the same nullable pattern used by the sibling hl7_mock_receiver/http_mock_receiver services.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    egress_topic_name: str | None
    egress_session_id: str | None
    service_bus_namespace: str | None
    health_check_hostname: str | None
    health_check_port: int | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING", required=False),
            egress_topic_name=_read_env("EGRESS_TOPIC_NAME", required=False),
            egress_session_id=_read_env("EGRESS_SESSION_ID", required=False),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST", required=False),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
        )

    @property
    def service_bus_enabled(self) -> bool:
        """True when enough Service Bus config is present to attempt forwarding."""
        return bool(self.egress_topic_name and (self.connection_string or self.service_bus_namespace))


def _read_env(name: str, required: bool = False) -> str | None:
    value = os.getenv(name)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)
