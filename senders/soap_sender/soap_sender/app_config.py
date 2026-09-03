"""Configuration for the SOAP Sender service.

SOAP_ENDPOINT_URL is the only required field.  Auth fields (API key, client cert,
WS-Security) are nullable — they are stubbed here and activate only when set,
so the service can run against the local http_mock_receiver without any auth config.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    # Service Bus
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_queue_name: str
    ingress_session_id: str
    message_store_queue_name: str
    # SOAP endpoint
    soap_endpoint_url: str
    soap_timeout_seconds: int
    # Auth stubs — all nullable; no-op when absent
    soap_api_key: str | None           # Added to Authorization: ApiKey <key> header
    soap_client_cert_path: str | None  # Path to PEM client cert for mTLS
    ws_security_enabled: bool          # Reserved for WS-Security token injection (not yet implemented)
    # Health check
    health_check_hostname: str | None
    health_check_port: int | None
    # Observability
    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str
    # Throttling
    max_messages_per_minute: int | None

    @staticmethod
    def read_env_config() -> AppConfig:
        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            ingress_session_id=_read_required_env("INGRESS_SESSION_ID"),
            message_store_queue_name=_read_required_env("MESSAGE_STORE_QUEUE_NAME"),
            soap_endpoint_url=_read_required_env("SOAP_ENDPOINT_URL"),
            soap_timeout_seconds=_read_int_env("SOAP_TIMEOUT_SECONDS") or 30,
            soap_api_key=_read_env("SOAP_API_KEY"),
            soap_client_cert_path=_read_env("SOAP_CLIENT_CERT_PATH"),
            ws_security_enabled=os.getenv("WS_SECURITY_ENABLED", "false").lower() == "true",
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_board=_read_required_env("HEALTH_BOARD"),
            peer_service=_read_required_env("PEER_SERVICE"),
            max_messages_per_minute=_read_positive_int_env("MAX_MESSAGES_PER_MINUTE"),
        )


def _read_env(name: str) -> str | None:
    return os.getenv(name)


def _read_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_int_env(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value is not None else None


def _read_positive_int_env(name: str) -> int | None:
    value = _read_int_env(name)
    if value is None:
        return None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer when provided")
    return value


def _read_required_int_env(name: str) -> int:
    value = _read_required_env(name)
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer value for configuration: {name}")
