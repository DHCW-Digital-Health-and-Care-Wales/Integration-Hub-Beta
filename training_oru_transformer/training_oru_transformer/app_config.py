"""
Application Configuration for Training HL7 Transformer
======================================================

This module provides centralized configuration management for the transformer.
All environment variables are read once at startup and stored in a dataclass.

LEARNING OBJECTIVES:
-------------------
1. Understand how transformers connect to Service Bus queues
2. Learn the ingress/egress queue naming pattern
3. See how session IDs enable ordered message processing

PRODUCTION REFERENCE:
--------------------
See shared_libs/transformer_base_lib/transformer_base_lib/app_config.py
for the full TransformerConfig class used in production.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass


@dataclass
class TransformerConfig:
    """
    Configuration for the training transformer.

    This dataclass holds all settings needed to run the transformer.
    It mirrors the production TransformerConfig but is simplified
    for training purposes.

    Attributes:
        connection_string: Azure Service Bus connection string
        ingress_queue_name: Queue to read messages FROM
        ingress_session_id: Session ID for the ingress queue
        egress_queue_name: Queue to publish transformed messages TO
        egress_session_id: Session ID for the egress queue
        max_batch_size: Maximum messages to receive in one batch
    """

    # =========================================================================
    # Service Bus Configuration
    # =========================================================================
    connection_string: str

    # Ingress queue settings - where we READ messages from
    ingress_queue_name: str
    ingress_session_id: str | None

    # Egress queue settings - where we WRITE transformed messages to
    egress_queue_name: str
    egress_session_id: str | None

    # Processing settings
    max_batch_size: int

    @staticmethod
    def from_env_and_config_file(config_path: str) -> TransformerConfig:
        """
        Load configuration from environment variables and config file.

        Environment variables provide runtime configuration (connection strings,
        queue names), while the config.ini file provides static settings
        (batch size).

        Args:
            config_path: Path to the config.ini file.

        Returns:
            A TransformerConfig instance with all settings populated.

        Raises:
            RuntimeError: If required environment variables are missing.
        """
        # Read optional settings from config.ini
        config = configparser.ConfigParser()
        config.read(config_path)
        max_batch_size = config.getint("DEFAULT", "MAX_BATCH_SIZE", fallback=10)

        return TransformerConfig(
            # ===================================================================
            # Service Bus Connection
            # ===================================================================
            # The connection string is REQUIRED - fail fast if not set
            connection_string=_read_required_env("SERVICE_BUS_CONNECTION_STRING"),
            # ===================================================================
            # Ingress Queue - where we READ messages from
            # ===================================================================
            # This is the queue that the HL7 Server publishes to
            # The transformer reads from this queue, processes messages, and
            # acknowledges them (removes from queue) when done.
            ingress_queue_name=_read_required_env("INGRESS_QUEUE_NAME"),
            ingress_session_id=_read_env("INGRESS_SESSION_ID"),
            # ===================================================================
            # Egress Queue - where we WRITE transformed messages to
            # ===================================================================
            # After transformation, messages go to this queue for the next
            # component in the pipeline (e.g., an HL7 Sender).
            egress_queue_name=_read_required_env("EGRESS_QUEUE_NAME"),
            egress_session_id=_read_env("EGRESS_SESSION_ID"),
            # Processing settings from config file
            max_batch_size=max_batch_size,
        )


# =============================================================================
# Helper Functions for Reading Environment Variables
# =============================================================================


def _read_env(name: str) -> str | None:
    """
    Read an optional environment variable.

    Args:
        name: The name of the environment variable.

    Returns:
        The value, or None if not set or empty.
    """
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value


def _read_required_env(name: str) -> str:
    """
    Read a required environment variable.

    Args:
        name: The name of the environment variable.

    Returns:
        The value of the environment variable.

    Raises:
        RuntimeError: If the variable is not set or is empty.
    """
    value = _read_env(name)
    if value is None:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. Please add it to your .env file or docker-compose.yml"
        )
    return value
