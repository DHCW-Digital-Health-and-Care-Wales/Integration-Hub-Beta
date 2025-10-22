import logging

from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType
from hl7apy.parser import parse_message

from .hl7_ack_builder import build_nack

logger = logging.getLogger(__name__)


class ErrorHandler(AbstractErrorHandler):
    def reply(self) -> str:
        if isinstance(self.exc, UnsupportedMessageType):
            logger.error("Unsupported Message Type: %s", self.exc)
        else:
            logger.error("Invalid HL7 Message: %s", self.exc)

        try:
            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            nack_message = build_nack(message_control_id, msg)
            return nack_message.to_mllp()
        except Exception:
            return "MSH|^~\\&|||||||NACK||P|2.5|||AL\rMSA|AE|UNKNOWN|Error processing message\r"
