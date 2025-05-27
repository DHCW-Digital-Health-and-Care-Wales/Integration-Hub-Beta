from datetime import datetime
import logging
from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from hl7apy.exceptions import HL7apyException
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def print_message(message: str) -> None:
    print(message.replace("\r", "\n"))


class GenericHandler(AbstractHandler):

    def reply(self) -> str:
        try:
            msg = parse_message(self.incoming_message)
            message_control_id = msg.msh.msh_10.value
            logger.info("Received message with Control ID: %s", message_control_id)

            ack_message = self.create_ack(message_control_id)
            logger.info("ACK generated successfully")

            return ack_message
        except HL7apyException as e:
            logger.error("HL7 parsing error: %s", e)
        except Exception as e:
            logger.exception("Unexpected error while processing message")

        # In case of error, return a default negative ACK-- TODO
        return self.create_fault("UNKNOWN", error_text="Processing Error")

    def create_ack(self, message_control_id: str) -> str:
        """
        Dummy ack implementation,
        TODO: implement with hl7py classes
        """
        ack_template = "\x0d".join(
            [
                "\x0bMSH|^~\\&|100|100|252|252|__TIME__||ACK^A311^ACK|__CONTROL_ID__|P|2.5",
                "MSA|AA|__CONTROL_ID__",
                "\x1c",
                "",
            ]
        )
        time = datetime.now().astimezone().strftime("%Y%m%d%H%M%S.%f%z")
        result = ack_template.replace("__CONTROL_ID__", message_control_id).replace("__TIME__", time)
        return result