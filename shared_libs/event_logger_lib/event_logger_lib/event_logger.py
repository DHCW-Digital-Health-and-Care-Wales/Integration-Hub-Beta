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

    def __init__(self, workflow_id: str, microservice_id: str):
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
        connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
        self.enabled = bool(connection_string)

        if self.enabled:
            self._initialize_azure_monitor()
        else:
            logger.debug("Event logging is disabled - APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty")

    def _initialize_azure_monitor(self) -> None:
        try:
            credential = self._get_credential()
            configure_azure_monitor(
                credential=credential,
                logger_name=__name__,
            )
            logger.info("Azure Monitor initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Azure Monitor: {e}")
            self.enabled = False
            raise

    def _get_credential(self):
        uami_client_id = os.getenv("INSIGHTS_UAMI_CLIENT_ID", "").strip()
        if uami_client_id:
            logger.info(f"Using ManagedIdentityCredential with client_id: {uami_client_id}")
            return ManagedIdentityCredential(client_id=uami_client_id)
        else:
            logger.info("Using DefaultAzureCredential (INSIGHTS_UAMI_CLIENT_ID not set)")
            return DefaultAzureCredential()

    def _create_log_event(
        self,
        event_type: EventType,
        message_content: str,
        validation_result: Optional[str] = None,
        error_details: Optional[str] = None
    ) -> LogEvent:
        return LogEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            message_content=message_content,
            validation_result=validation_result,
            error_details=error_details
        )

    def log_message_received(self, message_content: str, validation_result: Optional[str] = None) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_RECEIVED,
            message_content,
            validation_result=validation_result
        )
        self._send_log_event(event)

    def log_message_processed(self, message_content: str, validation_result: Optional[str] = None) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_PROCESSED,
            message_content,
            validation_result=validation_result
        )
        self._send_log_event(event)

    def log_message_failed(self, message_content: str, error_details: str,
                           validation_result: Optional[str] = None) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_FAILED,
            message_content,
            validation_result=validation_result,
            error_details=error_details
        )
        self._send_log_event(event)

    def log_validation_result(self, message_content: str, validation_result: str,
                              is_success: bool) -> None:
        event_type = EventType.VALIDATION_SUCCESS if is_success else EventType.VALIDATION_FAILED
        event = self._create_log_event(
            event_type,
            message_content,
            validation_result=validation_result
        )
        self._send_log_event(event)

    def _send_log_event(self, event: LogEvent) -> None:
        if not self.enabled:
            logger.debug(f"Event logging disabled, skipping event: {event.event_type.value}")
            return

        try:
            logger.info(
                "Integration Hub Event",
                extra={
                    **asdict(event),
                    "event_type": event.event_type.value,
                    "timestamp": event.timestamp.isoformat(),
                }
            )

            logger.debug(f"Event logged to Azure Monitor: {event.event_type.value}")
        except Exception as e:
            logger.error(f"Failed to send log event to Azure Monitor: {e}")
            raise
