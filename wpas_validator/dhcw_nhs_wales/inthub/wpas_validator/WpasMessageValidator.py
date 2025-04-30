from azure.servicebus import ServiceBusMessage
from dataclasses import dataclass
import os
from dhcw_nhs_wales.inthub.msgbus.MessageReceiverClient import MessageReceiverClient
from dhcw_nhs_wales.inthub.msgbus.MessageSenderClient import MessageSenderClient
from dhcw_nhs_wales.inthub.wpas_validator.xmlvalidator import XmlValidator

@dataclass
class WpasMessageValidatorConfig:
    CONNECTION_STRING: str
    INGRESS_QUEUE_NAME: str
    VALIDATED_WPAS_EGRESS_TOPIC_NAME: str
    SERVICE_BUS_NAMESPACE: str
    MAX_BATCH_SIZE: int

    @staticmethod
    def readEnv():
        return WpasMessageValidatorConfig(
              CONNECTION_STRING= os.environ.get('CONNECTION_STRING'),
              INGRESS_QUEUE_NAME= os.environ.get('INGRESS_QUEUE_NAME'),
              VALIDATED_WPAS_EGRESS_TOPIC_NAME= os.environ.get('VALIDATED_WPAS_EGRESS_TOPIC_NAME'),
              SERVICE_BUS_NAMESPACE= os.environ.get('SERVICE_BUS_NAMESPACE'),
              MAX_BATCH_SIZE= os.environ.get('MAX_BATCH_SIZE')
        )

class WpasMessageValidator:

    def __init__(self, config: WpasMessageValidatorConfig, receiver: MessageReceiverClient, validator: XmlValidator, sender: MessageSenderClient):
        self.recevier = receiver
        self.validator = validator
        self.sender = sender
        self.config = config

    def run(self):
        self.recevier.receive_messages(self.config.MAX_BATCH_SIZE, message_processor= self.process_message)

    def process_message(self, message: ServiceBusMessage):
        xml = message.body
        validaton_result = self.validator.validate(xml)
        if validaton_result.is_valid:
            self.sender.send_message(message.body)
