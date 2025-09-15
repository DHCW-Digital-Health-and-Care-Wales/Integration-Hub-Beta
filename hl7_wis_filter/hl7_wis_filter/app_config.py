from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AppConfig:
    connection_string: Optional[str]
    ingress_queue_name: str
    egress_queue_name: str
    service_bus_namespace: Optional[str]
    audit_queue_name: str
    workflow_id: str
    microservice_id: str
    health_check_hostname: Optional[str]
    health_check_port: Optional[int]

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            egress_queue_name=_read_required_env("EGRESS_QUEUE_NAME"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            audit_queue_name=_read_required_env("AUDIT_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
        )


def _read_env(name: str) -> Optional[str]:
    return os.getenv(name)


def _read_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_int_env(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"Invalid integer value for {name}: {value}")
