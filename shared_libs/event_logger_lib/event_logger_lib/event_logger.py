import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.monitor.opentelemetry import configure_azure_monitor

from .log_event import LogEvent, EventType

logger = logging.getLogger(__name__)


class EventLogger:
    _azure_monitor_initialized: bool = False

    def __init__(self, workflow_id: str, microservice_id: str) -> None:
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
        connection_string = os.getenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
        ).strip()
        self.azure_monitor_enabled = bool(connection_string)

        if self.azure_monitor_enabled:
            self._initialize_azure_monitor()
        else:
            logger.info(
                "Azure Monitor logging is disabled - "
                "APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty. "
                "Standard logger will be used."
            )

    def _initialize_azure_monitor(self) -> None:
        if EventLogger._azure_monitor_initialized:
            logger.debug(
                "Azure Monitor already initialized, skipping re-initialization"
            )
            return

        # Check if this library should initialize Azure Monitor
        azure_monitor_owner = (
            os.getenv("AZURE_MONITOR_OWNER", "event_logger").strip().lower()
        )
        if azure_monitor_owner != "event_logger":
            logger.info(
                f"Azure Monitor initialization skipped - AZURE_MONITOR_OWNER is '{azure_monitor_owner}', "
                "not 'event_logger'"
            )
            EventLogger._azure_monitor_initialized = (
                True  # Mark as handled to prevent retries
            )
            return

        try:
            credential = self._get_credential()
            configure_azure_monitor(
                credential=credential,
            )
            EventLogger._azure_monitor_initialized = True
            logger.info("Azure Monitor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Monitor: {e}")
            self.azure_monitor_enabled = False
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

    def _create_log_event(
        self,
        event_type: EventType,
        message_content: str,
        validation_result: Optional[str] = None,
        error_details: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> LogEvent:
        return LogEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            message_content=message_content,
            validation_result=validation_result,
            error_details=error_details,
            event_id=event_id,
        )

    def log_message_received(
        self,
        message_content: str,
        validation_result: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_RECEIVED,
            message_content,
            validation_result=validation_result,
            event_id=event_id,
        )
        self._send_log_event(event)

    def log_message_processed(
        self,
        message_content: str,
        validation_result: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_PROCESSED,
            message_content,
            validation_result=validation_result,
            event_id=event_id,
        )
        self._send_log_event(event)

    def log_message_failed(
        self,
        message_content: str,
        error_details: str,
        validation_result: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_FAILED,
            message_content,
            validation_result=validation_result,
            error_details=error_details,
            event_id=event_id,
        )
        self._send_log_event(event)

    def log_validation_result(
        self,
        message_content: str,
        validation_result: str,
        is_success: bool,
        event_id: Optional[str] = None,
    ) -> None:
        event_type = (
            EventType.VALIDATION_SUCCESS if is_success else EventType.VALIDATION_FAILED
        )
        event = self._create_log_event(
            event_type,
            message_content,
            validation_result=validation_result,
            event_id=event_id,
        )
        self._send_log_event(event)

    def _send_log_event(self, event: LogEvent) -> None:
        try:
            event_dict = {
                **asdict(event),
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
            }

            if self.azure_monitor_enabled:
                logger.info("Integration Hub Event", extra=event_dict)
                logger.debug(f"Event logged to Azure Monitor: {event.event_type.value}")
            else:
                logger.info(f"Integration Hub Event: {event_dict}")

        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            raise
