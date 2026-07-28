import os
import uuid
from dataclasses import dataclass

_DEFAULT_PG_PORT = 5432
# Secure by default: local development explicitly opts out via PG_SSLMODE=disable.
_DEFAULT_PG_SSLMODE = "require"
_DEFAULT_REPLAY_BATCH_SIZE = 100


@dataclass
class AppConfig:
    replay_batch_id: str
    connection_string: str | None
    service_bus_namespace: str | None
    priority_queue_name: str
    # PostgreSQL database configuration
    pg_host: str
    pg_database: str
    pg_user: str
    pg_password: str | None
    pg_port: int = _DEFAULT_PG_PORT
    pg_sslmode: str = _DEFAULT_PG_SSLMODE
    replay_batch_size: int = _DEFAULT_REPLAY_BATCH_SIZE
    # Optional client ID for user-assigned Managed Identity auth.
    # Leave unset (None) to use the system-assigned identity.
    managed_identity_client_id: str | None = None

    @staticmethod
    def read_env_config() -> "AppConfig":
        replay_batch_id = _read_required_env("REPLAY_BATCH_ID")
        _validate_uuid(replay_batch_id)

        return AppConfig(
            replay_batch_id=replay_batch_id,
            replay_batch_size=_read_replay_batch_size(_read_env("REPLAY_BATCH_SIZE")),
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            priority_queue_name=_read_required_env("PRIORITY_QUEUE_NAME"),
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


def _read_replay_batch_size(value: str | None) -> int:
    # Default to _DEFAULT_REPLAY_BATCH_SIZE if not set or empty/whitespace, otherwise validate it's a positive integer.
    if not value or value.strip() == "":
        return _DEFAULT_REPLAY_BATCH_SIZE
    try:
        parsed = int(value)
        if parsed <= 0:
            raise ValueError()
    except ValueError as e:
        raise RuntimeError(f"REPLAY_BATCH_SIZE must be a positive integer, got: {value}") from e
    return parsed


def _read_env(name: str) -> str | None:
    return os.getenv(name)


def _read_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)


def _validate_uuid(value: str) -> None:
    try:
        uuid.UUID(value)
    except ValueError as e:
        raise RuntimeError(f"REPLAY_BATCH_ID is not a valid UUID: {value}") from e


__all__ = ["AppConfig"]
