"""
Application Configuration Module (EXERCISE 1 SOLUTION)
======================================================

This module demonstrates how to implement the configuration management pattern
used throughout the Integration Hub project. Instead of reading environment
variables scattered throughout the code, we centralize all configuration into
a single, type-safe AppConfig class.

WHY USE THIS PATTERN?
---------------------
1. Single Source of Truth: All configuration is defined in one place
2. Type Safety: Using dataclasses with type hints catches errors early
3. Validation: We can validate configuration at startup, failing fast if
   something is missing or invalid
4. Testability: Easy to mock configuration in tests
5. Documentation: The dataclass serves as documentation for all config options

COMPARING APPROACHES:
--------------------
BEFORE (scattered env vars):
    host = os.environ.get("HOST", "0.0.0.0")  # In server_application.py
    expected_version = os.environ.get("HL7_VERSION", "2.3.1")  # In message_handler.py

AFTER (centralized config):
    config = AppConfig.read_env_config()
    host = config.host
    expected_version = config.hl7_version

PRODUCTION REFERENCE:
--------------------
See hl7_server/hl7_server/app_config.py for the full production implementation
which includes Service Bus connection settings, health check configuration,
and validation flow settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    """
    Application configuration loaded from environment variables.

    This dataclass holds all configuration values needed by the server.
    Using a dataclass gives us:
    - Automatic __init__ method
    - Automatic __repr__ for debugging
    - Type hints for IDE support
    - Immutability (by default)

    Attributes:
        host: The network interface to bind the server to.
              "0.0.0.0" accepts connections from any interface.
              "127.0.0.1" only accepts local connections.

        port: The TCP port number to listen on.
              Must be unique for each service on the same host.

        hl7_version: The expected HL7 version in MSH-12 field.
                     Messages with different versions will be rejected.

        allowed_senders: Comma-separated list of allowed sending application
                         codes (MSH-3). If None, all senders are accepted.
                         Example: "169,245" allows only apps 169 and 245.

        connection_string: Azure Service Bus connection string.
                           WEEK 2 ADDITION: Used to connect to Service Bus.

        egress_queue_name: Queue to publish HL7 messages to for transformer.
                           WEEK 2 ADDITION: Messages go here after ACK.

        egress_session_id: Session ID for the egress queue (if session-enabled).
                           WEEK 2 ADDITION: Used for ordered message processing.
    """

    # =========================================================================
    # Server Network Configuration
    # =========================================================================
    host: str
    port: int

    # =========================================================================
    # HL7 Validation Settings
    # =========================================================================
    hl7_version: str | None
    allowed_senders: str | None

    # =========================================================================
    # WEEK 2 ADDITION: Service Bus Configuration
    # =========================================================================
    connection_string: str | None
    egress_queue_name: str | None
    egress_session_id: str | None

    @staticmethod
    def read_env_config() -> AppConfig:
        """
        Read configuration from environment variables.

        This static method creates an AppConfig instance by reading all
        required and optional environment variables. It's called once at
        server startup.

        Returns:
            An AppConfig instance with all settings populated.

        Raises:
            RuntimeError: If required environment variables are missing.
            ValueError: If environment variable values are invalid.

        Example:
            # In server_application.py:
            config = AppConfig.read_env_config()
            print(f"Starting server on {config.host}:{config.port}")
        """
        return AppConfig(
            # =====================================================================
            # Network settings - these have sensible defaults for development
            # =====================================================================
            host=_read_env_with_default("HOST", "0.0.0.0"),
            port=_read_int_env_with_default("PORT", 2575),
            # =====================================================================
            # Validation settings - optional, None means no validation
            # =====================================================================
            # HL7_VERSION: If set, reject messages with different version
            hl7_version=_read_env("HL7_VERSION"),
            # ALLOWED_SENDERS: If set, reject messages from unknown senders
            # This is the training equivalent of SENDING_APP in production
            allowed_senders=_read_env("ALLOWED_SENDERS"),
            # =====================================================================
            # WEEK 2 ADDITION: Service Bus settings
            # =====================================================================
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


# =============================================================================
# Helper Functions for Reading Environment Variables
# =============================================================================
# These utility functions encapsulate the logic for reading environment
# variables with proper type conversion and error handling.


def _read_env(name: str) -> str | None:
    """
    Read an optional environment variable.

    This is the simplest helper - it just reads the variable and returns
    None if it's not set. Use this for optional configuration.

    Args:
        name: The name of the environment variable.

    Returns:
        The value of the environment variable, or None if not set.

    Example:
        # Returns "2.3.1" if HL7_VERSION is set, None otherwise
        version = _read_env("HL7_VERSION")
    """
    value = os.getenv(name)
    # Return None for empty strings as well - they're effectively "not set"
    if value is None or value.strip() == "":
        return None
    return value


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


def _read_required_env(name: str) -> str:
    """
    Read a required environment variable.

    Use this for critical configuration that must be provided. The server
    will fail to start if these variables are missing, which is better than
    running with incorrect defaults.

    Args:
        name: The name of the environment variable.

    Returns:
        The value of the environment variable.

    Raises:
        RuntimeError: If the variable is not set or is empty.

    Example:
        # Raises RuntimeError if MANDATORY_QUEUE_NAME is not set
        queue = _read_required_env("MANDATORY_QUEUE_NAME")
    """
    value = _read_env(name)
    if value is None:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. Please add it to your .env file or docker-compose.yml"
        )
    return value


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
