import os
from dataclasses import dataclass

_DEFAULT_PG_PORT = 5432
# Secure by default: local development explicitly opts out via PG_SSLMODE=disable.
_DEFAULT_PG_SSLMODE = "require"


@dataclass
class AppConfig:
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_queue_name: str
    microservice_id: str
    health_check_hostname: str | None
    health_check_port: int | None
    # PostgreSQL database configuration
    pg_host: str
    pg_database: str
    pg_user: str
    pg_password: str | None
    pg_port: int = _DEFAULT_PG_PORT
    pg_sslmode: str = _DEFAULT_PG_SSLMODE
    # Optional client ID for user-assigned Managed Identity auth.
    # Leave unset (None) to use the system-assigned identity.
    managed_identity_client_id: str | None = None

    @staticmethod
    def read_env_config() -> "AppConfig":
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            pg_host=_read_required_env("PG_HOST"),
            pg_database=_read_required_env("PG_DATABASE"),
            # Required in both auth modes: with Entra auth the database role name is
            # still supplied as the connection user, only the password differs.
            pg_user=_read_required_env("PG_USER"),
            # POSTGRES_PASSWORD is the name used by the postgres container image, so the
            # same secret drives both the server and the clients in local development.
            # Absent means Managed Identity auth.
            pg_password=_read_env("POSTGRES_PASSWORD"),
            pg_port=_read_int_env("PG_PORT") or _DEFAULT_PG_PORT,
            pg_sslmode=_read_env("PG_SSLMODE") or _DEFAULT_PG_SSLMODE,
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
