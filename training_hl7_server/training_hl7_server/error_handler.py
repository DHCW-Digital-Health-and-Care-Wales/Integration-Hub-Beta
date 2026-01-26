import logging



from hl7apy.mllp import AbstractErrorHandler, UnsupportedMessageType


logger = logging.getLogger(__name__)


class ErrorHandler(AbstractErrorHandler):
    def __init__(self, exc: Exception, msg: str):
        super().__init__(exc, msg)


    def reply(self) -> str:
        if isinstance(self.exc, UnsupportedMessageType):
            error_msg = f"Unsupported Message Type: {self.exc}"
            logger.error(error_msg)
        
        else:
            error_msg = f"Invalid HL7 Message: {self.exc}"
            logger.error(error_msg)
           
        raise self.exc
