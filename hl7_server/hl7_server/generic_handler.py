import logging

from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message

from .base_handler import BaseHandler
from .chemocare_handler import ChemocareHandler
from .hl7_constant import Hl7Constants
from .hl7_validator import ValidationException

# Configure logging
logger = logging.getLogger(__name__)


class GenericHandler(BaseHandler):
    def reply(self) -> str:
        try:
            self.audit_client.log_message_received(self.incoming_message, "Message received successfully")

            msg = parse_message(self.incoming_message, find_groups=False)
            message_control_id = msg.msh.msh_10.value
            message_type = msg.msh.msh_9.to_er7()
            authority_code = msg.msh.msh_3.value
            logger.info(
                "Received message type: %s, Control ID: %s, Authority: %s",
                message_type,
                message_control_id,
                authority_code,
            )

            # Check if this is a Chemocare message and delegate if so
            if self._is_chemocare_message(authority_code):
                logger.info("Delegating to ChemocareHandler for authority code: %s", authority_code)
                return self._delegate_to_chemocare_handler()

            # Continue with standard PHW/generic processing
            self.validator.validate(msg)
            self.audit_client.log_validation_result(
                self.incoming_message, f"Valid HL7 message - Type: {message_type}", is_success=True
            )

            self._send_to_service_bus(message_control_id)

            ack_message = self.create_ack(message_control_id, msg)

            self.audit_client.log_message_processed(self.incoming_message, "ACK generated successfully")

            logger.info("ACK generated successfully")
            return ack_message
        except HL7apyException as e:
            error_msg = f"HL7 parsing error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise
        except ValidationException as e:
            error_msg = f"HL7 validation error: {e}"
            logger.error(error_msg)

            self.audit_client.log_validation_result(self.incoming_message, error_msg, is_success=False)
            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise e
        except Exception as e:
            error_msg = f"Unexpected error while processing message: {e}"
            logger.exception(error_msg)

            self.audit_client.log_message_failed(self.incoming_message, error_msg)
            raise

    def _is_chemocare_message(self, authority_code: str) -> bool:
        return authority_code in Hl7Constants.CHEMOCARE_AUTHORITY_CODES

    def _delegate_to_chemocare_handler(self) -> str:
        chemocare_handler = ChemocareHandler(
            self.incoming_message, self.sender_client, self.audit_client, self.validator
        )
        return chemocare_handler.reply()
