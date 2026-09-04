from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

DEFAULT_MAX_REQUEST_SIZE_BYTES = 1048576  # 1MB request size cap


@dataclass
class AppConfig:
    connection_string: str | None
    egress_queue_name: str | None
    egress_topic_name: str | None
    egress_session_id: str
    service_bus_namespace: str | None
    message_store_queue_name: str
    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str
    health_check_hostname: str | None
    health_check_port: int | None
    host: str
    port: int
    soap_endpoint_path: str
    schema_group: str
    allowed_hl7_structures: List[str]
    allowed_assigning_authorities: List[str]
    max_request_size_bytes: int = DEFAULT_MAX_REQUEST_SIZE_BYTES
    tls_cert_file: str | None = None
    tls_key_file: str | None = None

    @staticmethod
    def read_env_config() -> "AppConfig":
        egress_queue_name = _read_env("EGRESS_QUEUE_NAME")
        egress_topic_name = _read_env("EGRESS_TOPIC_NAME")

        if not egress_queue_name and not egress_topic_name:
            raise RuntimeError("Either EGRESS_QUEUE_NAME or EGRESS_TOPIC_NAME must be provided")

        if egress_queue_name and egress_topic_name:
            raise RuntimeError("Cannot specify both EGRESS_QUEUE_NAME and EGRESS_TOPIC_NAME.")

        soap_endpoint_path = _read_env("SOAP_ENDPOINT_PATH") or "/soap"
        if not soap_endpoint_path.startswith("/"):
            raise RuntimeError("SOAP_ENDPOINT_PATH must start with '/'.")

        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            egress_queue_name=egress_queue_name,
            egress_topic_name=egress_topic_name,
            egress_session_id=_read_required_env("EGRESS_SESSION_ID"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            message_store_queue_name=_read_required_env("MESSAGE_STORE_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_board=_read_required_env("HEALTH_BOARD"),
            peer_service=_read_required_env("PEER_SERVICE"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            host=_read_env("HOST") or "127.0.0.1",
            port=_read_int_env("PORT") or 8080,
            soap_endpoint_path=soap_endpoint_path,
            schema_group=_read_env("HL7_SCHEMA_GROUP") or "phw",
            allowed_hl7_structures=_read_csv_list("ALLOWED_HL7_STRUCTURES", "ADT_A05,ADT_A39"),
            allowed_assigning_authorities=_read_csv_list("ALLOWED_ASSIGNING_AUTHORITIES", "328"),
            max_request_size_bytes=_read_and_validate_request_size(),
            tls_cert_file=_read_env("TLS_CERT_FILE"),
            tls_key_file=_read_env("TLS_KEY_FILE"),
        )


def _read_and_validate_request_size() -> int:
    configured_size = _read_int_env("MAX_REQUEST_SIZE_BYTES")

    if configured_size is None or configured_size <= 0:
        return DEFAULT_MAX_REQUEST_SIZE_BYTES

    service_bus_limit_bytes = 104857600  # 100MB Azure Service Bus Premium tier limit
    if configured_size > service_bus_limit_bytes:
        raise ValueError(
            f"Maximum request size configured: {configured_size} bytes. "
            f"It exceeds Azure Service Bus Premium tier limit of {service_bus_limit_bytes} bytes "
            f"({service_bus_limit_bytes / 1024 / 1024:.1f}MB)."
        )

    return configured_size


def _read_csv_list(name: str, default: str) -> List[str]:
    raw = _read_env(name)
    if raw is None or raw.strip() == "":
        raw = default

    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values:
        raise RuntimeError(f"Configuration {name} must include at least one value")

    return values


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
