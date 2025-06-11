import logging

from hl7apy.mllp import UnsupportedMessageType, AbstractErrorHandler

logger = logging.getLogger(__name__)


class ErrorHandler(AbstractErrorHandler):
    def reply(self):
        if isinstance(self.exc, UnsupportedMessageType):
            logger.error("Unsupported Message Type: %s", self.exc)
        else:
            logger.error("Invalid HL7 Message: %s", self.exc)
