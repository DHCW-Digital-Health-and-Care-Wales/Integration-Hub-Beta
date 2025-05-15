import logging
from azure.servicebus import ServiceBusMessage
from typing import Dict, Optional

logger = logging.getLogger("MessageSenderClient")
logger.setLevel(logging.DEBUG)


class MessageSenderClient:
    def __init__(self, sender, topic_name: str):
        self.sender = sender
        self.topic_name = topic_name

    def send_message(self, message_data: bytes, custom_properties: Optional[Dict[str, str]] = None):
        
        message = ServiceBusMessage(
            body=message_data,
            application_properties=custom_properties or {}
        )

        self.sender.send_messages(message)
        logger.debug("Message sent successfully to topic: %s", self.topic_name)

    def send_text_message(self, message_text: str, custom_properties: Optional[Dict[str, str]] = None):
        self.send_message(message_text.encode('utf-8'), custom_properties)

    def close(self):
        self.sender.close()
        logger.debug("ServiceBusSenderClient closed.")
