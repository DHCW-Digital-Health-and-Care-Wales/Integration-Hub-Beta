from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    connection_string: str | None
    egress_queue_name: str | None
    service_bus_namespace: str | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING", required=False),
            egress_queue_name=_read_env("EGRESS_QUEUE_NAME", required=True),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False)
        )


def _read_env(name: str, required: bool = False) -> str | None:
    value = os.getenv(name)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(f"Missing required configuration: {name}")
    return value
