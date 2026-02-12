from __future__ import annotations

import os
from dataclasses import dataclass


# Helper functions to read environment variables with some basic validation and type conversion.
def _read_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value


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


def read_required_int_env(name: str) -> int:
    value = _read_required_env(name)
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"Invalid integer value for {name}: {value}")


@dataclass
class AppConfig:
    # Service bus bit
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_queue_name: str
    ingress_session_id: str | None

    # MLLP bit
    receiver_mllp_hostname: str
    receiver_mllp_port: int
    ack_timeout_seconds: int

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            receiver_mllp_hostname=_read_required_env("RECEIVER_MLLP_HOST"),
            receiver_mllp_port=read_required_int_env("RECEIVER_MLLP_PORT"),
            ack_timeout_seconds=_read_int_env("ACK_TIMEOUT_SECONDS") or 30,
        )
