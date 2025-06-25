import logging

from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType
from message_bus_lib.audit_service_client import AuditServiceClient

logger = logging.getLogger(__name__)


class ErrorHandler(AbstractErrorHandler):
    def __init__(self, msg, audit_client: AuditServiceClient):
        super().__init__(msg)
        self.audit_client = audit_client

    def reply(self):
        if isinstance(self.exc, UnsupportedMessageType):
            error_msg = f"Unsupported Message Type: {self.exc}"
            logger.error(error_msg)
            self.audit_client.log_message_failed(self.incoming_message, error_msg, "Unsupported message type")
        else:
            error_msg = f"Invalid HL7 Message: {self.exc}"
            logger.error(error_msg)
            self.audit_client.log_message_failed(self.incoming_message, error_msg, "Invalid HL7 message format")

        raise self.exc
