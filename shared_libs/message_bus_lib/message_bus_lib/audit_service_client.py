import json
import logging
from datetime import datetime
from typing import Optional

from .audit_event import AuditEvent, AuditEventType
from .message_sender_client import MessageSenderClient

logger = logging.getLogger(__name__)


class AuditServiceClient:
    def __init__(self, sender_client: MessageSenderClient, workflow_id: str, microservice_id: str):
        self.sender_client = sender_client
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
    
    def log_message_received(self, message_content: str, validation_result: Optional[str] = None) -> None:
        event = AuditEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=AuditEventType.MESSAGE_RECEIVED,
            timestamp=datetime.datetime.now(datetime.UTC),
            message_content=message_content,
            validation_result=validation_result,
        )
        self._send_audit_event(event)
    
    def log_message_processed(self, message_content: str, validation_result: Optional[str] = None) -> None:
        event = AuditEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=AuditEventType.MESSAGE_PROCESSED,
            timestamp=datetime.datetime.now(datetime.UTC),
            message_content=message_content,
            validation_result=validation_result
        )
        self._send_audit_event(event)
    
    def log_message_failed(self, message_content: str, error_details: str, 
                          validation_result: Optional[str] = None) -> None:
        event = AuditEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=AuditEventType.MESSAGE_FAILED,
            timestamp=datetime.datetime.now(datetime.UTC),
            message_content=message_content,
            validation_result=validation_result,
            error_details=error_details
        )
        self._send_audit_event(event)
    
    def log_validation_result(self, message_content: str, validation_result: str, 
                            is_success: bool) -> None:
        event_type = AuditEventType.VALIDATION_SUCCESS if is_success else AuditEventType.VALIDATION_FAILED
        event = AuditEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=event_type,
            timestamp=datetime.datetime.now(datetime.UTC),
            message_content=message_content,
            validation_result=validation_result,
        )
        self._send_audit_event(event)
    
    def _send_audit_event(self, event: AuditEvent) -> None:
        try:
            audit_data = json.dumps(event.to_dict())
            self.sender_client.send_text_message(audit_data)
            logger.debug(f"Audit event sent: {event.event_type.value}")
        except Exception as e:
            logger.error(f"Failed to send audit event: {e}")