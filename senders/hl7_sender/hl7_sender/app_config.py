from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    connection_string: str | None
    ingress_queue_name: str | None
    ingress_session_id: str | None
    service_bus_namespace: str | None
    receiver_mllp_hostname: str
    receiver_mllp_port: int
    health_check_hostname: str | None
    health_check_port: int | None
    message_store_queue_name: str | None
    workflow_id: str
    microservice_id: str
    health_board: str
    peer_service: str
    ack_timeout_seconds: int
    max_messages_per_minute: int | None
    ingress_topic_name: str | None = field(default=None, kw_only=True)
    ingress_subscription_name: str | None = field(default=None, kw_only=True)

    @staticmethod
    def read_env_config() -> AppConfig:
        ingress_queue_name = (_read_env("INGRESS_QUEUE_NAME") or "").strip() or None
        ingress_topic_name = (_read_env("INGRESS_TOPIC_NAME") or "").strip() or None
        ingress_subscription_name = (_read_env("INGRESS_SUBSCRIPTION_NAME") or "").strip() or None
        validate_ingress_config(ingress_queue_name, ingress_topic_name, ingress_subscription_name)

        return AppConfig(
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            ingress_queue_name=ingress_queue_name,
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            receiver_mllp_hostname=_read_required_env("RECEIVER_MLLP_HOST"),
            receiver_mllp_port=_read_required_int_env("RECEIVER_MLLP_PORT"),
            health_check_hostname=_read_env("HEALTH_CHECK_HOST"),
            health_check_port=_read_int_env("HEALTH_CHECK_PORT"),
            message_store_queue_name=_read_env("MESSAGE_STORE_QUEUE_NAME"),
            workflow_id=_read_required_env("WORKFLOW_ID"),
            microservice_id=_read_required_env("MICROSERVICE_ID"),
            health_board=_read_required_env("HEALTH_BOARD"),
            peer_service=_read_required_env("PEER_SERVICE"),
            ack_timeout_seconds=_read_int_env("ACK_TIMEOUT_SECONDS") or 30,
            max_messages_per_minute=_read_positive_int_env("MAX_MESSAGES_PER_MINUTE"),
            ingress_topic_name=ingress_topic_name,
            ingress_subscription_name=ingress_subscription_name,
        )


def validate_ingress_config(
    ingress_queue_name: str | None,
    ingress_topic_name: str | None,
    ingress_subscription_name: str | None,
) -> None:
    """Ensure ingress is configured as exactly one of: a queue, or a topic+subscription pair."""
    has_queue = bool(ingress_queue_name)
    has_topic = bool(ingress_topic_name) or bool(ingress_subscription_name)

    if has_queue and has_topic:
        raise RuntimeError(
            "Invalid ingress configuration: INGRESS_QUEUE_NAME cannot be set together with "
            "INGRESS_TOPIC_NAME/INGRESS_SUBSCRIPTION_NAME. Configure only one ingress transport."
        )

    if not has_queue and not has_topic:
        raise RuntimeError(
            "Missing required configuration: set either INGRESS_QUEUE_NAME, or both "
            "INGRESS_TOPIC_NAME and INGRESS_SUBSCRIPTION_NAME."
        )

    if has_topic and (not ingress_topic_name or not ingress_subscription_name):
        raise RuntimeError(
            "Missing required configuration: INGRESS_TOPIC_NAME and INGRESS_SUBSCRIPTION_NAME "
            "must both be set when using topic-based ingress."
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
