import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_queue_name: str
    microservice_id: str
    health_check_hostname: str | None
    health_check_port: int | None
    # SQL database configuration
    sql_server: str
    sql_database: str
    sql_username: str | None
    sql_password: str | None
    sql_encrypt: str
    sql_trust_server_certificate: str
    # Optional client ID for user-assigned Managed Identity auth.
    # Leave unset (None) to use the system-assigned identity.
    managed_identity_client_id: str | None

    @staticmethod
    def read_env_config() -> "AppConfig":
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            sql_server=_read_required_env("SQL_SERVER"),
            sql_database=_read_required_env("SQL_DATABASE"),
            sql_username=_read_env("SQL_USERNAME"),
            sql_password=_read_env("SQL_PASSWORD"),
            sql_encrypt=_read_required_env("SQL_ENCRYPT"),
            sql_trust_server_certificate=_read_required_env("SQL_TRUST_SERVER_CERTIFICATE"),
            managed_identity_client_id=_read_env("MANAGED_IDENTITY_CLIENT_ID"),
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


__all__ = ["AppConfig"]
