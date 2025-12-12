import logging
import os
from typing import Dict, Any, Optional

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import metrics
from opentelemetry.metrics import Counter

logger = logging.getLogger(__name__)


class MetricSender:
    def __init__(
        self,
        workflow_id: str,
        microservice_id: str,
        health_board: str,
        peer_service: str,
    ):
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
        self.health_board = health_board
        self.peer_service = peer_service
        self._counters: Dict[str, Counter] = {}

        connection_string = os.getenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
        ).strip()
        self.azure_monitor_enabled = bool(connection_string)

        if self.azure_monitor_enabled:
            self._initialize_azure_monitor()
        else:
            logger.info(
                "Azure Monitor metrics is disabled - APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty. "
                "Metrics will be logged to standard logger."
            )

    def _initialize_azure_monitor(self) -> None:
        # Check if this library should initialize Azure Monitor
        # AZURE_MONITOR_OWNER needs set to 'metric_sender' on components where only metric_sender_lib is used
        azure_monitor_owner = (
            os.getenv("AZURE_MONITOR_OWNER", "event_logger").strip().lower()
        )
        if azure_monitor_owner != "metric_sender":
            logger.info(
                f"Azure Monitor initialization skipped - AZURE_MONITOR_OWNER is '{azure_monitor_owner}', "
                "not 'metric_sender'. Metrics will still be collected if Azure Monitor is initialized elsewhere."
            )
            # Don't initialize, but metrics can still be sent if EventLogger initialized Azure Monitor
            self._meter = metrics.get_meter(__name__)
            return

        try:
            # DIAGNOSTIC: Log handler count BEFORE configure_azure_monitor
            root_logger = logging.getLogger()
            logger.warning(
                f"[DIAGNOSTIC MetricSender] BEFORE configure_azure_monitor: "
                f"Root logger has {len(root_logger.handlers)} handlers: "
                f"{[type(h).__name__ for h in root_logger.handlers]}"
            )

            credential = self._get_credential()
            configure_azure_monitor(credential=credential)

            # DIAGNOSTIC: Log handler count AFTER configure_azure_monitor
            logger.warning(
                f"[DIAGNOSTIC MetricSender] AFTER configure_azure_monitor: "
                f"Root logger has {len(root_logger.handlers)} handlers: "
                f"{[type(h).__name__ for h in root_logger.handlers]}"
            )

            self._meter = metrics.get_meter(__name__)
            logger.info("Azure Monitor metrics initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Monitor metrics: {e}")
            raise

    def _get_credential(self):
        uami_client_id = os.getenv("INSIGHTS_UAMI_CLIENT_ID", "").strip()
        if uami_client_id:
            logger.info(
                f"Using ManagedIdentityCredential with client_id: {uami_client_id}"
            )
            return ManagedIdentityCredential(client_id=uami_client_id)
        else:
            logger.info(
                "Using DefaultAzureCredential (INSIGHTS_UAMI_CLIENT_ID not set)"
            )
            return DefaultAzureCredential()

    def _get_or_create_counter(self, key: str) -> Counter:
        if key not in self._counters:
            self._counters[key] = self._meter.create_counter(
                name=key, description=f"Counter for {key}"
            )
            logger.debug(f"Created new counter for metric: {key}")
        return self._counters[key]

    def send_metric(
        self, key: str, value: int = 1, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Send a custom metric to Azure Application Insights.

        Args:
            key: The metric name (appears as the metric in Azure Monitor).
            value: The metric value (default is 1 for counter increment).
            attributes: Optional dictionary of attributes to include with the metric.
        """
        try:
            metric_attributes = {
                "workflow_id": self.workflow_id,
                "microservice_id": self.microservice_id,
                "health_board": self.health_board,
                "peer_service": self.peer_service,
            }

            if attributes:
                metric_attributes.update(attributes)

            if self.azure_monitor_enabled and self._meter:
                counter = self._get_or_create_counter(key)
                counter.add(value, attributes=metric_attributes)
                logger.debug(
                    f"Metric sent to Azure Monitor: {key}={value} with attributes: {metric_attributes}"
                )
            else:
                logger.info(
                    f"Integration Hub Metric (local log): {key}={value}, attributes: {metric_attributes}"
                )

        except Exception as e:
            logger.error(f"Failed to send metric '{key}': {e}")
            raise

    def send_message_received_metric(
        self, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        self.send_metric(key="messages_received", value=1, attributes=attributes)

    def send_message_sent_metric(
        self, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        self.send_metric(key="messages_sent", value=1, attributes=attributes)
