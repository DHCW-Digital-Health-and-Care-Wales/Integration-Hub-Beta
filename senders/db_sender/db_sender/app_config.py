from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    # Service Bus Connection
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_topic_name: str
    ingress_subscription_name: str
    ingress_session_id: str | None

    # Database Connection
    db_server: str
    db_port: int
    db_name: str
    db_stored_procedure: str
    db_username: str | None
    db_password: str | None
    db_encrypt: str
    db_trust_server_certificate: str
    db_connection_timeout: int
    db_command_timeout: int
    managed_identity_client_id: str | None

    # Application & Logging
    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str
    health_check_hostname: str | None
    health_check_port: int | None
    log_level: str
    default_is_priority: int
    max_batch_size: int

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_topic_name=_read_required_env("INGRESS_TOPIC_NAME"),
            ingress_subscription_name=_read_required_env("INGRESS_SUBSCRIPTION_NAME"),
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            db_server=_read_required_env("DB_SERVER", default="localhost"),
            db_port=_read_int_env("DB_PORT") or 1433,
            db_name=_read_required_env("DB_NAME", default="DRS"),
            db_stored_procedure=_read_required_env("DB_STORED_PROCEDURE", default="dbo.prQueueMessage"),
            db_username=_read_env("DB_USERNAME") or ("sa" if _read_env("MSSQL_SA_PASSWORD") else None),
            db_password=_read_env("DB_PASSWORD") or _read_env("MSSQL_SA_PASSWORD"),
            db_encrypt=_read_env("DB_ENCRYPT") or "Yes",
            db_trust_server_certificate=_read_env("DB_TRUST_SERVER_CERTIFICATE") or "No",
            db_connection_timeout=_read_int_env("DB_CONNECTION_TIMEOUT") or 30,
            db_command_timeout=_read_int_env("DB_COMMAND_TIMEOUT") or 60,
            managed_identity_client_id=_read_env("MANAGED_IDENTITY_CLIENT_ID"),
            workflow_id=_read_env("WORKFLOW_ID") or "risp-to-wrrs",
            microservice_id=_read_env("MICROSERVICE_ID") or "wrrs_stmsg_dbsender",
            health_board=_read_env("HEALTH_BOARD") or "SHARED",
            peer_service=_read_env("PEER_SERVICE") or "WRRS",
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            log_level=_read_env("LOG_LEVEL") or "INFO",
            default_is_priority=_read_int_env("DEFAULT_IS_PRIORITY") or 0,
            max_batch_size=_read_int_env("MAX_BATCH_SIZE") or 10,
        )


def _read_env(name: str) -> str | None:
    val = os.getenv(name)
    if val is not None and val.strip() == "":
        return None
    return val


def _read_required_env(name: str, default: str | None = None) -> str:
    val = os.getenv(name)
    if val is not None and val.strip() != "":
        return val.strip()
    if default is not None:
        return default
    raise RuntimeError(f"Missing required configuration: {name}")


def _read_int_env(name: str) -> int | None:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return None
    try:
        return int(val.strip())
    except ValueError:
        raise ValueError(f"Invalid integer value for configuration: {name}")
