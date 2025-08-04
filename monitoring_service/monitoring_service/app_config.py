from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class MonitoringAppConfig:
    connection_string: str | None
    service_bus_namespace: str | None
    audit_queue_name: str
    database_connection_string: str
    stored_procedure_name: str
    health_check_hostname: str | None
    health_check_port: int | None

    @staticmethod
    def read_env_config() -> MonitoringAppConfig:
        return MonitoringAppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING", required=False),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE", required=False),
            audit_queue_name=_read_env("AUDIT_QUEUE_NAME", required=True),
            database_connection_string=_read_env("DATABASE_CONNECTION_STRING", required=True),
            stored_procedure_name=_read_env("STORED_PROCEDURE_NAME", required=False) or "[queue].[prInsertEvent]",
            health_check_hostname=_read_env("HEALTH_CHECK_HOST", required=False),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT", required=False),
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
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"Invalid integer value for {name}: {value}")