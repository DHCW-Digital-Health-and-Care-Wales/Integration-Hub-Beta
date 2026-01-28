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
            host = os.environ.get("HOST", "0.0.0.0"),
            port = int(os.environ.get("PORT", "2575")),
            hl7_version = os.environ.get("HL7_VERSION", "2.3.1"),
            allowed_senders = os.environ.get("ALLOWED_SENDERS")
        )
