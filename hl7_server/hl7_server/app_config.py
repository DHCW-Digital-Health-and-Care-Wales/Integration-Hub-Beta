from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_MESSAGE_SIZE_BYTES = 1048576  # 1MB - default message size limit for HL7 messages


@dataclass
class AppConfig:
    connection_string: str | None
    egress_queue_name: str | None
    egress_topic_name: str | None
    egress_session_id: str | None
    service_bus_namespace: str | None
    audit_queue_name: str
    workflow_id: str
    microservice_id: str
    hl7_version: str | None
    sending_app: str | None
    health_check_hostname: str | None
    health_check_port: int | None
    hl7_validation_flow: str | None = None
    max_message_size_bytes: int = DEFAULT_MAX_MESSAGE_SIZE_BYTES

    @staticmethod
    def read_env_config() -> AppConfig:
        egress_queue_name = _read_env("EGRESS_QUEUE_NAME")
        egress_topic_name = _read_env("EGRESS_TOPIC_NAME")

        if not egress_queue_name and not egress_topic_name:
            raise RuntimeError("Either EGRESS_QUEUE_NAME or EGRESS_TOPIC_NAME must be provided")

        if egress_queue_name and egress_topic_name:
            raise RuntimeError("Cannot specify both EGRESS_QUEUE_NAME and EGRESS_TOPIC_NAME.")

        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            egress_queue_name=egress_queue_name,
            egress_topic_name=egress_topic_name,
            egress_session_id=_read_env("EGRESS_SESSION_ID"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            audit_queue_name=_read_required_env("AUDIT_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            hl7_version=_read_env("HL7_VERSION"),
            sending_app=_read_env("SENDING_APP"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            hl7_validation_flow=_read_env("HL7_VALIDATION_FLOW"),
            max_message_size_bytes=_read_and_validate_message_size(),
        )

def _read_and_validate_message_size() -> int:
    configured_size = _read_int_env("MAX_MESSAGE_SIZE_BYTES")

    if configured_size is None or configured_size <= 0:
        return DEFAULT_MAX_MESSAGE_SIZE_BYTES

    service_bus_limit_bytes = 104857600  # 100MB - Azure Service Bus Premium tier limit

    if configured_size > service_bus_limit_bytes:
        raise ValueError(
            f"Maximum message size configured: {configured_size} bytes. "
            f"It exceeds Azure Service Bus Premium tier limit of {service_bus_limit_bytes} bytes "
            f"({service_bus_limit_bytes / 1024 /1024:.1f}MB)."
        )

    return configured_size

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
