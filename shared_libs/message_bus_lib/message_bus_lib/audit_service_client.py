import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from .audit_event import AuditEvent, AuditEventType
from .message_sender_client import MessageSenderClient

logger = logging.getLogger(__name__)


class AuditServiceClient:
    def __init__(self, sender_client: MessageSenderClient, workflow_id: str, microservice_id: str):
        self.sender_client = sender_client
        self.workflow_id = workflow_id
        self.microservice_id = microservice_id
        self._message_counts: Dict[str, int] = {
            "received": 0,
            "processed": 0,
            "failed": 0,
            "validation_success": 0,
            "validation_failed": 0
        }

    def _create_audit_event(
        self,
        event_type: AuditEventType,
        message_content: str,
        validation_result: Optional[str] = None,
        error_details: Optional[str] = None
    ) -> AuditEvent:
        return AuditEvent(
            workflow_id=self.workflow_id,
            microservice_id=self.microservice_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            message_content=message_content,
            validation_result=validation_result,
            error_details=error_details
        )

    def log_message_received(self, message_content: str, validation_result: Optional[str] = None) -> None:
        event = self._create_audit_event(
            AuditEventType.MESSAGE_RECEIVED,
            message_content,
            validation_result=validation_result
        )
        self._send_audit_event(event)
        self._message_counts["received"] += 1

    def log_message_processed(self, message_content: str, validation_result: Optional[str] = None) -> None:
        event = self._create_audit_event(
            AuditEventType.MESSAGE_PROCESSED,
            message_content,
            validation_result=validation_result
        )
        self._send_audit_event(event)
        self._message_counts["processed"] += 1

    def log_message_failed(self, message_content: str, error_details: str, 
                           validation_result: Optional[str] = None) -> None:
        event = self._create_audit_event(
            AuditEventType.MESSAGE_FAILED,
            message_content,
            validation_result=validation_result,
            error_details=error_details
        )
        self._send_audit_event(event)
        self._message_counts["failed"] += 1

    def log_validation_result(self, message_content: str, validation_result: str, 
                              is_success: bool) -> None:
        event_type = AuditEventType.VALIDATION_SUCCESS if is_success else AuditEventType.VALIDATION_FAILED
        event = self._create_audit_event(
            event_type,
            message_content,
            validation_result=validation_result
        )
        self._send_audit_event(event)

        if is_success:
            self._message_counts["validation_success"] += 1
        else:
            self._message_counts["validation_failed"] += 1

    def log_component_status(self, status: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
        status_info = {
            "component_id": self.microservice_id,
            "workflow_id": self.workflow_id,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message_counts": self._message_counts.copy(),
            "additional_info": additional_info or {}
        }
        
        try:
            status_data = json.dumps(status_info)
            self.sender_client.send_text_message(status_data)
            logger.debug(f"Component status logged: {status}")
        except Exception as e:
            logger.error(f"Failed to log component status: {e}")

    def get_message_counts(self) -> Dict[str, int]:
        return self._message_counts.copy()

    def reset_message_counts(self) -> None:
        self._message_counts = {
            "received": 0,
            "processed": 0,
            "failed": 0,
            "validation_success": 0,
            "validation_failed": 0 
        }
        logger.debug("Message counts reset") 
    
    def _send_audit_event(self, event: AuditEvent) -> None:
        try:
            audit_data = json.dumps(event.to_dict())
            self.sender_client.send_text_message(audit_data)
            logger.debug(f"Audit event sent: {event.event_type.value}")
        except Exception as e:
            logger.error(f"Failed to send audit event: {e}")
            raise

    def close(self) -> None:
        if self.sender_client:
            self.sender_client.close()
            logger.debug("AuditServiceClient closed.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()
