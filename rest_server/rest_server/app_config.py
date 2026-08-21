from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Only fills in variables not already set in the environment, and is a no-op when the file is
# absent (e.g. in production containers, where a .env file is never baked into the image).
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

DEFAULT_MAX_REQUEST_SIZE_BYTES = 1048576  # 1MB request size cap

VALID_CONTENT_ADAPTERS = {"soap", "xml-raw"}
VALID_VALIDATOR_TYPES = {"hl7-xsd", "xsd", "none"}
VALID_OUTPUT_FORMATS = {"er7", "raw"}
SCHEMA_REQUIRED_VALIDATOR_TYPES = {"hl7-xsd", "xsd"}


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
    endpoint_path: str
    content_adapter: str
    validator_type: str
    validation_schema: str | None
    allowed_hl7_structures: List[str]
    allowed_source_identifiers: List[str]
    source_identifier_locator: List[str] | None
    message_control_id_locator: List[str] | None
    output_format: str
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

        endpoint_path = _read_env("ENDPOINT_PATH") or "/ingest"
        if not endpoint_path.startswith("/"):
            raise RuntimeError("ENDPOINT_PATH must start with '/'.")

        content_adapter = _read_required_env("CONTENT_ADAPTER")
        if content_adapter not in VALID_CONTENT_ADAPTERS:
            raise RuntimeError(
                f"Unsupported CONTENT_ADAPTER '{content_adapter}'. "
                f"Allowed values: {', '.join(sorted(VALID_CONTENT_ADAPTERS))}"
            )

        validator_type = _read_required_env("VALIDATOR_TYPE")
        if validator_type not in VALID_VALIDATOR_TYPES:
            raise RuntimeError(
                f"Unsupported VALIDATOR_TYPE '{validator_type}'. "
                f"Allowed values: {', '.join(sorted(VALID_VALIDATOR_TYPES))}"
            )

        output_format = _read_required_env("OUTPUT_FORMAT")
        if output_format not in VALID_OUTPUT_FORMATS:
            raise RuntimeError(
                f"Unsupported OUTPUT_FORMAT '{output_format}'. "
                f"Allowed values: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
            )

        validation_schema = _read_env("VALIDATION_SCHEMA")
        if validator_type in SCHEMA_REQUIRED_VALIDATOR_TYPES and not validation_schema:
            raise RuntimeError(f"VALIDATION_SCHEMA is required when VALIDATOR_TYPE is '{validator_type}'.")

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
            endpoint_path=endpoint_path,
            content_adapter=content_adapter,
            validator_type=validator_type,
            validation_schema=validation_schema,
            allowed_hl7_structures=_read_csv_list("ALLOWED_HL7_STRUCTURES", "ADT_A05,ADT_A39"),
            allowed_source_identifiers=_read_csv_list_optional("ALLOWED_SOURCE_IDENTIFIERS"),
            source_identifier_locator=_read_path_env("SOURCE_IDENTIFIER_LOCATOR"),
            message_control_id_locator=_read_path_env("MESSAGE_CONTROL_ID_LOCATOR"),
            output_format=output_format,
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


def _read_csv_list_optional(name: str) -> List[str]:
    raw = _read_env(name)
    if raw is None or raw.strip() == "":
        return []
    return [value.strip() for value in raw.split(",") if value.strip()]


def _read_path_env(name: str) -> List[str] | None:
    raw = _read_env(name)
    if raw is None or raw.strip() == "":
        return None
    segments = [segment.strip() for segment in raw.split("/") if segment.strip()]
    return segments or None


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
