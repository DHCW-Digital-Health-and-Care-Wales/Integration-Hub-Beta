from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    ingress_queue_name: str
    ingress_session_id: str | None
    egress_queue_name: str
    egress_session_id: str | None
    service_bus_namespace: str | None
    audit_queue_name: str | None
    workflow_id: str
    microservice_id: str
    health_check_hostname: str | None
    health_check_port: int | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            egress_queue_name=_read_required_env("EGRESS_QUEUE_NAME"),
            egress_session_id=_read_env("EGRESS_SESSION_ID"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            audit_queue_name=_read_env("AUDIT_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
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
    if value is not None:
        return int(value)
    else:
        return None
