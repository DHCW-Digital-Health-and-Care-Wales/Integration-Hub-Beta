import logging
import os
from typing import Optional, Union

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import metrics

logger = logging.getLogger(__name__)


class AzureMonitorFactory:
    """
    Factory for centralized Azure Monitor initialization.

    This factory ensures Azure Monitor is initialized only once across the application,
    regardless of how many libraries (event_logger, metric_sender, etc.) need it.
    """

    _initialized: bool = False
    _meter: Optional[metrics.Meter] = None
    _is_enabled: Optional[bool] = None
    _connection_string: Optional[str] = None
    _uami_client_id: Optional[str] = None

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if Azure Monitor is enabled based on environment configuration."""
        if cls._is_enabled is None:
            cls._connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
            cls._is_enabled = bool(cls._connection_string)
        return cls._is_enabled

    @classmethod
    def ensure_initialized(cls) -> bool:
        """
        Ensure Azure Monitor is initialized.

        Returns:
            bool: True if initialization was successful or already initialized, False otherwise.
        """
        if cls._initialized:
            return True

        if not cls.is_enabled():
            logger.info(
                "Azure Monitor initialization skipped - "
                "APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty."
            )
            return False

        try:
            credential = cls._get_credential()
            configure_azure_monitor(credential=credential)
            cls._initialized = True
            cls._meter = metrics.get_meter(__name__)
            logger.info("Azure Monitor initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Azure Monitor: {e}")
            return False

    @classmethod
    def get_meter(cls) -> Optional[metrics.Meter]:
        """
        Get the OpenTelemetry meter for metrics.

        Returns:
            Optional[metrics.Meter]: The meter if Azure Monitor is initialized, None otherwise.
        """
        if not cls._initialized:
            cls.ensure_initialized()
        return cls._meter

    @classmethod
    def _get_credential(cls) -> Union[DefaultAzureCredential, ManagedIdentityCredential]:
        """Get the appropriate Azure credential based on environment configuration."""
        # Cache UAMI client ID lookup
        if cls._uami_client_id is None:
            cls._uami_client_id = os.getenv("INSIGHTS_UAMI_CLIENT_ID", "").strip()

        if cls._uami_client_id:
            logger.info(
                f"Using ManagedIdentityCredential with client_id: {cls._uami_client_id}"
            )
            return ManagedIdentityCredential(client_id=cls._uami_client_id)
        else:
            logger.info(
                "Using DefaultAzureCredential (INSIGHTS_UAMI_CLIENT_ID not set)"
            )
            return DefaultAzureCredential()
