from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_MESSAGE_SIZE_BYTES = 1048576  # 1MB - default message size limit for HL7 messages
DEFAULT_HOST = "0.0.0.0"  # nosec B104 - bind all interfaces inside the container
DEFAULT_PORT = 8080
DEFAULT_ENVIRONMENT = "DEV"

# Environments in which the interactive Swagger / OpenAPI UI is exposed.
SWAGGER_ENABLED_ENVIRONMENTS = frozenset({"DEV", "SIT"})

# Azure Service Bus Premium tier maximum message size.
SERVICE_BUS_LIMIT_BYTES = 104857600  # 100MB


@dataclass
class AppConfig:
    connection_string: str | None
    egress_queue_name: str | None
    egress_topic_name: str | None
    egress_session_id: str
    service_bus_namespace: str | None
    message_store_queue_name: str | None
    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str
    hl7_version: str | None
    sending_app: str | None
    environment: str
    host: str
    port: int
    hl7_validation_flow: str | None = None
    hl7_validation_standard: str | None = None
    max_message_size_bytes: int = DEFAULT_MAX_MESSAGE_SIZE_BYTES
    wrrs_queue_name: str | None = None
    wrrs_topic_name: str | None = None
    wrrs_egress_session_id: str | None = None
    wrrs_workflow_id: str | None = None

    @property
    def swagger_enabled(self) -> bool:
        return self.environment in SWAGGER_ENABLED_ENVIRONMENTS

    @staticmethod
    def read_env_config() -> AppConfig:
        egress_queue_name = _read_env("EGRESS_QUEUE_NAME")
        egress_topic_name = _read_env("EGRESS_TOPIC_NAME")

        if not egress_queue_name and not egress_topic_name:
            raise RuntimeError("Either EGRESS_QUEUE_NAME or EGRESS_TOPIC_NAME must be provided")

        if egress_queue_name and egress_topic_name:
            raise RuntimeError("Cannot specify both EGRESS_QUEUE_NAME and EGRESS_TOPIC_NAME.")

        hl7_validation_flow = _read_env("HL7_VALIDATION_FLOW")
        wrrs_queue_name, wrrs_topic_name, wrrs_egress_session_id, wrrs_workflow_id = _read_and_validate_wrrs_config(
            hl7_validation_flow
        )

        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            egress_queue_name=egress_queue_name,
            egress_topic_name=egress_topic_name,
            egress_session_id=_read_required_env("EGRESS_SESSION_ID"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            message_store_queue_name=_read_env("MESSAGE_STORE_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_board=_read_required_env("HEALTH_BOARD"),
            peer_service=_read_required_env("PEER_SERVICE"),
            hl7_version=_read_env("HL7_VERSION"),
            sending_app=_read_env("SENDING_APP"),
            environment=(_read_env("ENVIRONMENT") or DEFAULT_ENVIRONMENT).upper(),
            host=_read_env("HOST") or DEFAULT_HOST,
            port=_read_int_env("PORT") or DEFAULT_PORT,
            hl7_validation_flow=hl7_validation_flow,
            hl7_validation_standard=_read_env("HL7_VALIDATION_STANDARD"),
            max_message_size_bytes=_read_and_validate_message_size(),
            wrrs_queue_name=wrrs_queue_name,
            wrrs_topic_name=wrrs_topic_name,
            wrrs_egress_session_id=wrrs_egress_session_id,
            wrrs_workflow_id=wrrs_workflow_id,
        )


def _read_and_validate_wrrs_config(
    hl7_validation_flow: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Read the WRRS destination config, required only for the 'risp' flow (plan §3a).

    RISP is the only flow that sends directly to WRRS (in addition to, or instead of, the
    primary EGRESS_QUEUE_NAME/EGRESS_TOPIC_NAME destination), so WRRS_* variables are validated
    as required only when HL7_VALIDATION_FLOW is 'risp'; other flows can leave them unset.
    """
    wrrs_queue_name = _read_env("WRRS_QUEUE_NAME")
    wrrs_topic_name = _read_env("WRRS_TOPIC_NAME")
    wrrs_egress_session_id = _read_env("WRRS_EGRESS_SESSION_ID")
    wrrs_workflow_id = _read_env("WRRS_WORKFLOW_ID")

    if hl7_validation_flow != "risp":
        return wrrs_queue_name, wrrs_topic_name, wrrs_egress_session_id, wrrs_workflow_id

    if not wrrs_queue_name and not wrrs_topic_name:
        raise RuntimeError("The 'risp' flow requires either WRRS_QUEUE_NAME or WRRS_TOPIC_NAME to be provided.")
    if wrrs_queue_name and wrrs_topic_name:
        raise RuntimeError("Cannot specify both WRRS_QUEUE_NAME and WRRS_TOPIC_NAME.")
    if not wrrs_egress_session_id:
        raise RuntimeError("The 'risp' flow requires WRRS_EGRESS_SESSION_ID to be provided.")
    if not wrrs_workflow_id:
        raise RuntimeError("The 'risp' flow requires WRRS_WORKFLOW_ID to be provided.")

    return wrrs_queue_name, wrrs_topic_name, wrrs_egress_session_id, wrrs_workflow_id


def _read_and_validate_message_size() -> int:
    configured_size = _read_int_env("MAX_MESSAGE_SIZE_BYTES")

    if configured_size is None or configured_size <= 0:
        return DEFAULT_MAX_MESSAGE_SIZE_BYTES

    if configured_size > SERVICE_BUS_LIMIT_BYTES:
        raise ValueError(
            f"Maximum message size configured: {configured_size} bytes. "
            f"It exceeds Azure Service Bus Premium tier limit of {SERVICE_BUS_LIMIT_BYTES} bytes "
            f"({SERVICE_BUS_LIMIT_BYTES / 1024 / 1024:.1f}MB)."
        )

    return configured_size


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
