import os
import uuid
from dataclasses import dataclass

_DEFAULT_SQL_ENCRYPT = "Yes"
_DEFAULT_SQL_TRUST_SERVER_CERTIFICATE = "No"
_DEFAULT_REPLAY_BATCH_SIZE = 100


@dataclass
class AppConfig:
    replay_batch_id: str
    connection_string: str | None
    service_bus_namespace: str | None
    priority_queue_name: str
    # SQL database configuration
    sql_server: str
    sql_database: str
    sql_username: str | None
    sql_password: str | None
    sql_encrypt: str = _DEFAULT_SQL_ENCRYPT
    sql_trust_server_certificate: str = _DEFAULT_SQL_TRUST_SERVER_CERTIFICATE
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
            sql_server=_read_required_env("SQL_SERVER"),
            sql_database=_read_required_env("SQL_DATABASE"),
            sql_username=_read_env("SQL_USERNAME"),
            sql_password=_read_env("MSSQL_SA_PASSWORD"),
            sql_encrypt=_read_env("SQL_ENCRYPT") or _DEFAULT_SQL_ENCRYPT,
            sql_trust_server_certificate=(
                _read_env("SQL_TRUST_SERVER_CERTIFICATE") or _DEFAULT_SQL_TRUST_SERVER_CERTIFICATE
            ),
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


def _validate_uuid(value: str) -> None:
    try:
        uuid.UUID(value)
    except ValueError as e:
        raise RuntimeError(f"REPLAY_BATCH_ID is not a valid UUID: {value}") from e


__all__ = ["AppConfig"]
