import os
from dataclasses import dataclass

from azure.servicebus import ServiceBusMessage

from dhcw_nhs_wales_inthub.msgbus.MessageReceiverClient import MessageReceiverClient
from dhcw_nhs_wales_inthub.msgbus.MessageSenderClient import MessageSenderClient
from dhcw_nhs_wales_inthub.wpas_validator.xmlvalidator import XmlValidator


@dataclass
class WpasMessageValidatorConfig:
    CONNECTION_STRING: str | None
    INGRESS_QUEUE_NAME: str
    VALIDATED_WPAS_EGRESS_TOPIC_NAME: str
    SERVICE_BUS_NAMESPACE: str
    MAX_BATCH_SIZE: int

    @classmethod
    def readEnv(self) -> 'WpasMessageValidatorConfig':
        return WpasMessageValidatorConfig(
            CONNECTION_STRING = os.environ.get("CONNECTION_STRING"),
            INGRESS_QUEUE_NAME = os.environ["INGRESS_QUEUE_NAME"],
            VALIDATED_WPAS_EGRESS_TOPIC_NAME = os.environ["VALIDATED_WPAS_EGRESS_TOPIC_NAME"],
            SERVICE_BUS_NAMESPACE = os.environ["SERVICE_BUS_NAMESPACE"],
            MAX_BATCH_SIZE = int(os.environ["MAX_BATCH_SIZE"]),
        )

class WpasMessageValidator:
    def __init__(
        self,
        config: WpasMessageValidatorConfig,
        receiver: MessageReceiverClient,
        validator: XmlValidator,
        sender: MessageSenderClient,
    ):
        self.recevier = receiver
        self.validator = validator
        self.sender = sender
        self.config = config

    def run(self) -> None:
        self.recevier.receive_messages(self.config.MAX_BATCH_SIZE, message_processor=self.process_message)

    def process_message(self, message: ServiceBusMessage) -> dict:
        xml = message.body
        validaton_result = self.validator.validate(xml)
        if validaton_result.is_valid:
            self.sender.send_message(message.body)
        return {'success': True}
