"""
=============================================================================
Application Configuration - Week 3 Training
=============================================================================

This module reads configuration from environment variables and provides
a typed configuration object for the sender application.

ENVIRONMENT VARIABLES:
---------------------
Required:
  - INGRESS_QUEUE_NAME: Queue to read transformed messages from
  - RECEIVER_MLLP_HOST: Hostname of the mock receiver
  - RECEIVER_MLLP_PORT: Port of the mock receiver

Optional:
  - SERVICE_BUS_CONNECTION_STRING: Connection string (for local development)
  - SERVICE_BUS_NAMESPACE: Namespace (for managed identity in production)
  - INGRESS_SESSION_ID: Session ID for ordered message delivery
  - ACK_TIMEOUT_SECONDS: How long to wait for ACK (default: 30)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    """
    Configuration for the Training HL7 Sender.

    This dataclass holds all configuration values needed by the sender.
    Using a dataclass provides:
    - Type checking at development time
    - Clear documentation of all required settings
    - Immutable configuration after creation
    """

    # Service Bus connection settings
    connection_string: str | None
    service_bus_namespace: str | None

    # Queue settings
    ingress_queue_name: str
    ingress_session_id: str | None

    # MLLP destination settings
    receiver_mllp_hostname: str
    receiver_mllp_port: int

    # Timeout settings
    ack_timeout_seconds: int

    @staticmethod
    def read_env_config() -> AppConfig:
        """
        Read configuration from environment variables.

        This is the standard pattern for containerized applications:
        configuration comes from the environment, not from config files.

        Returns:
            AppConfig: A fully populated configuration object

        Raises:
            RuntimeError: If a required environment variable is missing
            ValueError: If a numeric value is invalid
        """
        return AppConfig(
            # Service Bus connection (one of these is required)
            connection_string=_read_env("SERVICE_BUS_CONNECTION_STRING"),
            service_bus_namespace=_read_env("SERVICE_BUS_NAMESPACE"),
            # Queue configuration
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            # MLLP destination
            receiver_mllp_hostname=_read_required_env("RECEIVER_MLLP_HOST"),
            receiver_mllp_port=_read_required_int_env("RECEIVER_MLLP_PORT"),
            # Timeout (default 30 seconds)
            ack_timeout_seconds=_read_int_env("ACK_TIMEOUT_SECONDS") or 30,
        )


# =============================================================================
# Helper Functions
# =============================================================================


def _read_env(name: str) -> str | None:
    """
    Read an optional environment variable.

    Args:
        name: The name of the environment variable

    Returns:
        The value if set, None otherwise
    """
    return os.getenv(name)


def _read_required_env(name: str) -> str:
    """
    Read a required environment variable.

    Args:
        name: The name of the environment variable

    Returns:
        The value

    Raises:
        RuntimeError: If the variable is not set or is empty
    """
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required configuration: {name}")
    return value


def _read_int_env(name: str) -> int | None:
    """
    Read an optional integer environment variable.

    Args:
        name: The name of the environment variable

    Returns:
        The integer value if set, None otherwise
    """
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)


def _read_required_int_env(name: str) -> int:
    """
    Read a required integer environment variable.

    Args:
        name: The name of the environment variable

    Returns:
        The integer value

    Raises:
        RuntimeError: If the variable is not set
        ValueError: If the value is not a valid integer
    """
    value = _read_required_env(name)
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Invalid integer value for configuration: {name}")