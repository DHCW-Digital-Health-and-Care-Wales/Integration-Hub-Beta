from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    host : str
    port : int
    hl7_version: str
    allowed_senders: list[str]
    connection_string: str | None
    service_bus_namespace: str | None
    egress_queue_name: str | None
    egress_session_id: str | None

    @staticmethod
    def read_env_config() -> AppConfig:

        return AppConfig(
            host=_read_required_env("HOST"),
            port= _read_int_required_env("PORT"),
            hl7_version=_read_required_env("HL7_VERSION"),
            allowed_senders=_read_required_env_list("ALLOWED_SENDERS"),
            # SERVICE_BUS_CONNECTION_STRING: Connection string for local dev (emulator)
            # SERVICE_BUS_NAMESPACE: Namespace for Azure deployment (managed identity)
            # One of these should be set when using Service Bus
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            # EGRESS_QUEUE_NAME: Queue where validated messages are published
            # The transformer component reads from this queue
            egress_queue_name=_read_env("EGRESS_QUEUE_NAME"),
            # EGRESS_SESSION_ID: Session ID for ordered message processing
            # Session-enabled queues ensure messages are processed in order
            egress_session_id=_read_env("EGRESS_SESSION_ID")
        )


def _read_env(name: str) -> str | None:
    return os.getenv(name)

def _read_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    else:
        return value

def _read_required_env_list(name: str) -> list[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    else:
        return value.split(",")  # Split comma-separated list into a Python list

def _read_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)

def _read_int_required_env(name: str) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    else:
        return int(value)
