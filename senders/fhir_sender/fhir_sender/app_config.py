"""Configuration for the FHIR Sender service (all values come from environment variables)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, TypeVar

_Number = TypeVar("_Number", int, float)

AUTH_MODE_API_KEY = "api_key"
AUTH_MODE_OAUTH2 = "oauth2"


@dataclass
class AppConfig:
    # Service Bus
    connection_string: str | None
    service_bus_namespace: str | None
    ingress_queue_name: str
    ingress_session_id: str | None
    max_batch_size: int
    # Promptly endpoint
    fhir_endpoint_url: str
    allow_insecure_http: bool
    request_timeout_seconds: int
    max_attempts: int
    backoff_seconds: float
    max_retry_after_seconds: float
    poll_interval_seconds: float
    poll_timeout_seconds: float
    # Authentication: exactly one mechanism per environment
    auth_mode: str
    api_key: str | None
    oauth_token_url: str | None
    oauth_client_id: str | None
    oauth_client_secret: str | None
    oauth_scope: str | None
    # Health check
    health_check_hostname: str | None
    health_check_port: int | None
    # Observability
    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str

    @staticmethod
    def read_env_config() -> AppConfig:
        auth_mode = os.getenv("FHIR_AUTH_MODE", AUTH_MODE_API_KEY).lower().strip()
        if auth_mode == AUTH_MODE_API_KEY:
            api_key: str | None = _read_required_env("FHIR_API_KEY")
            oauth: dict[str, str | None] = {k: None for k in ("url", "id", "secret", "scope")}
        elif auth_mode == AUTH_MODE_OAUTH2:
            api_key = None
            oauth = {
                "url": _read_required_env("FHIR_OAUTH_TOKEN_URL"),
                "id": _read_required_env("FHIR_OAUTH_CLIENT_ID"),
                "secret": _read_required_env("FHIR_OAUTH_CLIENT_SECRET"),
                "scope": _read_required_env("FHIR_OAUTH_SCOPE"),
            }
        else:
            raise ValueError(f"FHIR_AUTH_MODE must be '{AUTH_MODE_API_KEY}' or '{AUTH_MODE_OAUTH2}'")

        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            ingress_session_id=_read_required_env("INGRESS_SESSION_ID"),
            max_batch_size=_read_positive_number("MAX_BATCH_SIZE", 1, int),
            fhir_endpoint_url=_read_required_env("FHIR_ENDPOINT_URL"),
            allow_insecure_http=os.getenv("FHIR_ALLOW_INSECURE_HTTP", "false").lower().strip() == "true",
            request_timeout_seconds=_read_positive_number("FHIR_TIMEOUT_SECONDS", 30, int),
            max_attempts=_read_positive_number("FHIR_MAX_ATTEMPTS", 3, int),
            backoff_seconds=_read_positive_number("FHIR_BACKOFF_SECONDS", 2.0, float),
            max_retry_after_seconds=_read_positive_number("FHIR_MAX_RETRY_AFTER_SECONDS", 60.0, float),
            poll_interval_seconds=_read_positive_number("FHIR_POLL_INTERVAL_SECONDS", 5.0, float),
            poll_timeout_seconds=_read_positive_number("FHIR_POLL_TIMEOUT_SECONDS", 120.0, float),
            auth_mode=auth_mode,
            api_key=api_key,
            oauth_token_url=oauth["url"],
            oauth_client_id=oauth["id"],
            oauth_client_secret=oauth["secret"],
            oauth_scope=oauth["scope"],
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_optional_int("HEALTH_CHECK_PORT"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_board=_read_required_env("HEALTH_BOARD"),
            peer_service=_read_required_env("PEER_SERVICE"),
        )


def _read_env(name: str) -> str | None:
    value = os.getenv(name)
    return value if value is not None and value.strip() != "" else None


def _read_required_env(name: str) -> str:
    value = _read_env(name)
    if value is None:
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_optional_int(name: str) -> int | None:
    value = _read_env(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer value for configuration: {name}") from None


def _read_positive_number(name: str, default: _Number, cast: Callable[[str], _Number]) -> _Number:
    value = _read_env(name)
    if value is None:
        return default
    try:
        number = cast(value)
    except ValueError:
        raise ValueError(f"Invalid numeric value for configuration: {name}") from None
    if number <= 0:
        raise ValueError(f"{name} must be a positive number")
    return number
