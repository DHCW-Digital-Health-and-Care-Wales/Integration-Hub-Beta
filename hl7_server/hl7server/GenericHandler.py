import logging
from datetime import datetime

from hl7apy.mllp import AbstractHandler
from hl7apy.parser import parse_message
from .ServiceBusMessageSender import ServiceBusMessageSender


class GenericHandler(AbstractHandler):
    def reply(self) -> str:
        self.service_bus_client = ServiceBusMessageSender()
        msg = parse_message(self.incoming_message)
        msg_control_id = msg.msh.msh_10.value
        logging.info(f"Received message with control id: {msg_control_id}")

        # Send message to Service Bus queue
        try:
            self.service_bus_client.send_message(self.incoming_message)
            logging.info(f"Message {msg_control_id} sent to Service Bus queue")
            res = self.ack(msg_control_id)
        except Exception as e:
            logging.error(f"Failed to send message to Service Bus: {str(e)}")
            res = self.nack(msg_control_id)

        return res

    def ack(self, message_control_id: str) -> str:
        """
        Dummy ack implementation,
        TODO: implement with hl7py classes
        """
        ack_template = "\x0d".join(
            [
                "\x0bMSH|^~\\&|100|100|252|252|__TIME__||ACK^A31^ACK|__CONTROL_ID__|P|2.5",
                "MSA|AA|__CONTROL_ID__",
                "\x1c",
                "",
            ]
        )
        time = datetime.now().astimezone().strftime("%Y%m%d%H%M%S.%f%z")
        result = ack_template.replace("__CONTROL_ID__", message_control_id).replace("__TIME__", time)
        return result
    
    def nack(self, message_control_id: str) -> str:
        nack_template = "\x0d".join(
            [
                "\x0bMSH|^~\\&|100|100|252|252|__TIME__||ACK^A31^ACK|__CONTROL_ID__|P|2.5",
                "MSA|AE|__CONTROL_ID__",
                "\x1c",
                "",
            ]
        )
        time = datetime.now().astimezone().strftime("%Y%m%d%H%M%S.%f%z")
        result = nack_template.replace("__CONTROL_ID__", message_control_id).replace("__TIME__", time)
        return result
