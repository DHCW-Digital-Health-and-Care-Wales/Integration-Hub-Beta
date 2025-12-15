import logging
from datetime import datetime, timezone
from typing import Optional

from azure_monitor_lib import AzureMonitorFactory

from .log_event import LogEvent, EventType

logger = logging.getLogger(__name__)


class EventLogger:
    def __init__(
        self,
        workflow_id: str,
        microservice_id: str,
        azure_monitor_factory: AzureMonitorFactory
    ) -> None:
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
        self._azure_monitor_factory = azure_monitor_factory
        self.azure_monitor_enabled = self._azure_monitor_factory.is_enabled()

        if self.azure_monitor_enabled:
            self._azure_monitor_factory.ensure_initialized()
        else:
            logger.info(
                "Azure Monitor logging is disabled - "
                "APPLICATIONINSIGHTS_CONNECTION_STRING not set or empty. "
                "Standard logger will be used."
            )


    def _create_log_event(
        self,
        event_type: EventType,
        message_content: str,
        validation_result: Optional[str] = None,
        error_details: Optional[str] = None,
    ) -> LogEvent:
        return LogEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            message_content=message_content,
            validation_result=validation_result,
            error_details=error_details,
        )

    def log_message_received(
        self, message_content: str, validation_result: Optional[str] = None
    ) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_RECEIVED,
            message_content,
            validation_result=validation_result,
        )
        self._send_log_event(event)

    def log_message_processed(
        self, message_content: str, validation_result: Optional[str] = None
    ) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_PROCESSED,
            message_content,
            validation_result=validation_result,
        )
        self._send_log_event(event)

    def log_message_failed(
        self,
        message_content: str,
        error_details: str,
        validation_result: Optional[str] = None,
    ) -> None:
        event = self._create_log_event(
            EventType.MESSAGE_FAILED,
            message_content,
            validation_result=validation_result,
            error_details=error_details,
        )
        self._send_log_event(event)

    def log_validation_result(
        self, message_content: str, validation_result: str, is_success: bool
    ) -> None:
        event_type = (
            EventType.VALIDATION_SUCCESS if is_success else EventType.VALIDATION_FAILED
        )
        event = self._create_log_event(
            event_type, message_content, validation_result=validation_result
        )
        self._send_log_event(event)

    def _send_log_event(self, event: LogEvent) -> None:
        try:
            event_dict = {
                "workflow_id": event.workflow_id,
                "microservice_id": event.microservice_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "message_content": event.message_content,
                "validation_result": event.validation_result,
                "error_details": event.error_details,
            }

            if self.azure_monitor_enabled:
                logger.info("Integration Hub Event", extra=event_dict)
                logger.debug(f"Event logged to Azure Monitor: {event.event_type.value}")
            else:
                logger.info(f"Integration Hub Event: {event_dict}")

        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            raise
