import logging

from event_logger_lib.event_logger import EventLogger
from hl7_validation import XmlValidationError
from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType
from hl7apy.parser import parse_message

from .exceptions.validation_exception import ValidationException
from .hl7_ack_builder import HL7AckBuilder
from .hl7_constant import Hl7Constants

logger = logging.getLogger(__name__)

# Business/schema/structural validation failures -> AR (Application Reject).
# Everything else (parsing failures, unsupported types, unexpected errors) -> AE (Application Error).
VALIDATION_EXCEPTIONS = (ValidationException, XmlValidationError)


class ErrorHandler(AbstractErrorHandler):
    """Turns any exception raised while processing an inbound MLLP message into an HL7 NACK.

    hl7apy's MLLPRequestHandler routes every exception raised during dispatch (parsing failures,
    unsupported message types, and any exception raised from GenericHandler.reply(), including
    validation and unexpected processing errors) through this handler. Rather than re-raising (which
    previously caused the connection to be closed with no reply sent), this now returns a built NACK
    so the sending system always receives an explicit HL7 response.
    """

    def __init__(
        self, exc: Exception, msg: str, event_logger: EventLogger, ack_builder: HL7AckBuilder | None = None
    ):
        super().__init__(exc, msg)
        self.event_logger = event_logger
        self.ack_builder = ack_builder or HL7AckBuilder()

    def reply(self) -> str:
        error_msg, category, ack_code = self._classify_failure()

        logger.error(error_msg)
        # Telemetry failures must not prevent the NACK from being sent: EventLogger re-raises on
        # send failure, so keep this best-effort and always proceed to build/return the NACK.
        try:
            self.event_logger.log_message_failed(self.incoming_message, error_msg, category)
        except Exception as e:
            logger.error("Failed to log message failure before sending NACK: %s", e)

        nack = self._build_nack(ack_code, error_msg)
        logger.info("NACK built successfully (MSA-1=%s, control_id=%s)", ack_code, nack.msa.msa_2.value)
        return nack.to_mllp()

    def _classify_failure(self) -> tuple[str, str, str]:
        if isinstance(self.exc, VALIDATION_EXCEPTIONS):
            return f"HL7 validation error: {self.exc}", "HL7 validation failed", Hl7Constants.ACK_CODE_REJECT
        if isinstance(self.exc, UnsupportedMessageType):
            return f"Unsupported Message Type: {self.exc}", "Unsupported message type", Hl7Constants.ACK_CODE_ERROR
        if isinstance(self.exc, HL7apyException):
            return f"Invalid HL7 Message: {self.exc}", "Invalid HL7 message format", Hl7Constants.ACK_CODE_ERROR
        return (
            f"Unexpected error while processing message: {self.exc}",
            "Unexpected processing error",
            Hl7Constants.ACK_CODE_ERROR,
        )

    def _build_nack(self, ack_code: str, reason: str) -> Message:
        # Attempt to recover the original message so the NACK can echo its MSH fields and control ID.
        # This succeeds for validation/unexpected-processing failures (the message parsed fine
        # earlier) and fails for genuine parsing failures, falling back to a generic NACK.
        try:
            original_msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = original_msg.msh.msh_10.value
        except Exception:
            return self.ack_builder.build_generic_nack(reason)

        return self.ack_builder.build_nack(message_control_id, original_msg, ack_code, reason)
