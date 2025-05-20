import logging
from typing import Any, Dict, Optional

from azure.servicebus import ServiceBusMessage, ServiceBusSender

logger = logging.getLogger("MessageSenderClient")
logger.setLevel(logging.DEBUG)


class MessageSenderClient:
    def __init__(self, sender: ServiceBusSender, topic_name: str) -> None:
        self.sender = sender
        self.topic_name = topic_name

    def send_message(self, message_data: bytes, custom_properties: Optional[Dict[str, str]] = None) -> None:
        message_properties: Dict[str | bytes, Any] = {}
        if custom_properties:
            for key, value in custom_properties.items():
                message_properties[key] = value

        message = ServiceBusMessage(body=message_data, application_properties=message_properties)
        self.sender.send_messages(message)
        logger.debug("Message sent successfully to topic: %s", self.topic_name)

    def send_text_message(self, message_text: str, custom_properties: Optional[Dict[str, str]] = None) -> None:
        self.send_message(message_text.encode("utf-8"), custom_properties)

    def close(self) -> None:
        self.sender.close()
        logger.debug("ServiceBusSenderClient closed.")
