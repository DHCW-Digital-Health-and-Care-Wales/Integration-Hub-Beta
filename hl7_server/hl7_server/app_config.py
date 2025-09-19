from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    egress_queue_name: str
    service_bus_namespace: str | None
    audit_queue_name: str
    workflow_id: str
    microservice_id: str
    hl7_version: str | None
    sending_app: str | None
    health_check_hostname: str | None
    health_check_port: int | None
    hl7_validation_flow: str | None = None
    max_message_size_bytes: int = 1048576  # Default 1MB

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            egress_queue_name=_read_required_env("EGRESS_QUEUE_NAME"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            audit_queue_name=_read_required_env("AUDIT_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            hl7_version=_read_env("HL7_VERSION"),
            sending_app=_read_env("SENDING_APP"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            hl7_validation_flow=_read_env("HL7_VALIDATION_FLOW"),
            max_message_size_bytes=_read_int_env("MAX_MESSAGE_SIZE_BYTES") or 1048576,
        )


def _read_env(name: str) -> str | None:
    return os.getenv(name)


def _read_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    else:
        return value

def _read_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)
