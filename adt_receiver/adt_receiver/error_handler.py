import logging

from event_logger_lib.event_logger import EventLogger
from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType

from .hl7_nack_builder import HL7NackBuilder

logger = logging.getLogger(__name__)


class ErrorHandler(AbstractErrorHandler):
    def __init__(self, exc: Exception, msg: str, event_logger: EventLogger):
        super().__init__(exc, msg)
        self.event_logger = event_logger

    def reply(self) -> str:
        if isinstance(self.exc, UnsupportedMessageType):
            error_msg = f"Unsupported Message Type: {self.exc}"
            logger.error(error_msg)
            self.event_logger.log_message_failed(self.incoming_message, error_msg, "Unsupported message type")
        else:
            error_msg = f"Invalid HL7 Message: {self.exc}"
            logger.error(error_msg)
            self.event_logger.log_message_failed(self.incoming_message, error_msg, "Invalid HL7 message format")

        nack_builder = HL7NackBuilder()
        nack = nack_builder.build_nack(self.incoming_message)
        return nack.to_mllp()
