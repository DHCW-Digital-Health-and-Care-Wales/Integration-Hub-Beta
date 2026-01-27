from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_MESSAGE_SIZE_BYTES = 1048576  # 1MB - default message size limit for HL7 messages


@dataclass
class AppConfig:
    allowed_senders: str | None
    hl7_version: str | None
    connection_string: str | None
    egress_queue_name: str | None
    egress_session_id: str | None
    host: str | None = "0.0.0.0"
    port: int | None = 2580


    @staticmethod
    def read_env_config() -> AppConfig:

        return AppConfig(
            host=_read_env_with_default("HOST", "0.0.0.0"),
            port=_read_int_env_with_default("PORT", 2575),
            hl7_version=_read_env("HL7_VERSION"),
            allowed_senders=_read_env("ALLOWED_SENDERS"),
            # SERVICE_BUS_CONNECTION_STRING: Connection string for Azure Service Bus
            # For local development, this connects to the Service Bus Emulator
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            # EGRESS_QUEUE_NAME: Queue where validated messages are published
            # The transformer component reads from this queue
            egress_queue_name=_read_env("EGRESS_QUEUE_NAME"),
            # EGRESS_SESSION_ID: Session ID for ordered message processing
            # Session-enabled queues ensure messages are processed in order
            egress_session_id=_read_env("EGRESS_SESSION_ID"),
        )

def _read_and_validate_message_size() -> int:
    configured_size = _read_int_env_with_default("MAX_MESSAGE_SIZE_BYTES")

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

def _read_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value

# def _read_required_env(name: str) -> str:
#     value = os.getenv(name)
#     if value is None or value.strip() == "":
#         raise RuntimeError(f"Missing required configuration: {name}")
#     else:
#         return value

def _read_env_with_default(name: str, default: str) -> str:
    """
    Read an environment variable with a default value.

    Use this for settings that have sensible defaults but can be overridden.

    Args:
        name: The name of the environment variable.
        default: The default value if the variable is not set.

    Returns:
        The value of the environment variable, or the default.

    Example:
        # Returns "0.0.0.0" if HOST is not set
        host = _read_env_with_default("HOST", "0.0.0.0")
    """
    value = _read_env(name)
    return value if value is not None else default

def _read_int_env_with_default(name: str, default: int) -> int:
    """
    Read an integer environment variable with a default value.

    Environment variables are always strings, so this helper converts
    the string to an integer after reading it.

    Args:
        name: The name of the environment variable.
        default: The default integer value if the variable is not set.

    Returns:
        The integer value of the environment variable, or the default.

    Raises:
        ValueError: If the value cannot be converted to an integer.

    Example:
        # Returns 2575 if PORT is not set
        port = _read_int_env_with_default("PORT", 2575)
    """
    value = _read_env(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable '{name}' must be an integer, got '{value}'")