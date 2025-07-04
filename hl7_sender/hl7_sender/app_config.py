from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    ingress_queue_name: str | None
    service_bus_namespace: str | None
    receiver_mllp_hostname: str | None
    receiver_mllp_port: int | None
    audit_queue_name: str | None
    workflow_id: str | None
    microservice_id: str | None
    ack_timeout_seconds: int

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING", required=False),
            ingress_queue_name=_read_env("INGRESS_QUEUE_NAME", required=True),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False),
            receiver_mllp_hostname=_read_env("RECEIVER_MLLP_HOST", required=True),
            receiver_mllp_port=_read_int_env("RECEIVER_MLLP_PORT", required=True),
            audit_queue_name=_read_env("AUDIT_QUEUE_NAME", required=True),
            workflow_id=_read_env("WORKFLOW_ID", required=True),
            microservice_id=_read_env("MICROSERVICE_ID", required=True),
            ack_timeout_seconds=_read_int_env("ACK_TIMEOUT_SECONDS", required=False) or 30,
        )


def _read_env(name: str, required: bool = False) -> str | None:
    value = os.getenv(name)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(f"Missing required configuration: {name}")
    return value

def _read_int_env(name: str, required: bool = False) -> int | None:
    value = os.getenv(name)
    if value is None:
        if required:
            raise RuntimeError(f"Missing required configuration: {name}")
        return None
    return int(value)

