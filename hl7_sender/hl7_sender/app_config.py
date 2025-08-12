from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    ingress_queue_name: str
    service_bus_namespace: str | None
    receiver_mllp_hostname: str
    receiver_mllp_port: int
    health_check_hostname: str | None
    health_check_port: int | None
    audit_queue_name: str
    workflow_id: str
    microservice_id: str
    ack_timeout_seconds: int

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            receiver_mllp_hostname=_read_required_env("RECEIVER_MLLP_HOST"),
            receiver_mllp_port=_read_required_int_env("RECEIVER_MLLP_PORT"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            audit_queue_name=_read_required_env("AUDIT_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            ack_timeout_seconds=_read_int_env("ACK_TIMEOUT_SECONDS") or 30,
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

def _read_required_int_env(name: str) -> int:
    value = _read_required_env(name)
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer value for configuration: {name}")
