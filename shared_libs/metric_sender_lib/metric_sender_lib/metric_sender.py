import logging
from typing import Dict, Any, Optional

from azure_monitor_lib import AzureMonitorFactory
from opentelemetry.metrics import Counter

logger = logging.getLogger(__name__)


class MetricSender:
    def __init__(
        self,
        workflow_id: str,
        microservice_id: str,
        health_board: str,
        peer_service: str,
        azure_monitor_factory: AzureMonitorFactory,
    ):
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
        self.health_board = health_board
        self.peer_service = peer_service
        self._counters: Dict[str, Counter] = {}
        self._azure_monitor_factory = azure_monitor_factory
        self.azure_monitor_enabled = self._azure_monitor_factory.is_enabled()

        if self.azure_monitor_enabled:
            self._azure_monitor_factory.ensure_initialized()
            self._meter = self._azure_monitor_factory.get_meter()
        else:
            logger.info(
                "Azure Monitor metrics is disabled - APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty. "
                "Metrics will be logged to standard logger."
            )
            self._meter = None


    def _get_or_create_counter(self, key: str) -> Counter:
        # Optimized: Use dict.get() to avoid double lookup
        counter = self._counters.get(key)
        if counter is None:
            counter = self._meter.create_counter(
                name=key, description=f"Counter for {key}"
            )
            self._counters[key] = counter
            logger.debug(f"Created new counter for metric: {key}")
        return counter

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
            # Optimized: Pre-allocate dict with known size and merge efficiently
            if attributes:
                metric_attributes = {
                    "workflow_id": self.workflow_id,
                    "microservice_id": self.microservice_id,
                    "health_board": self.health_board,
                    "peer_service": self.peer_service,
                    **attributes  # Merge additional attributes
                }
            else:
                metric_attributes = {
                    "workflow_id": self.workflow_id,
                    "microservice_id": self.microservice_id,
                    "health_board": self.health_board,
                    "peer_service": self.peer_service,
                }

            # Optimized: Single condition check for enabled state
            if self.azure_monitor_enabled and self._meter is not None:
                counter = self._get_or_create_counter(key)
                counter.add(value, attributes=metric_attributes)
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
