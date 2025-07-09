import logging
from azure.servicebus import ServiceBusMessage, ServiceBusSender
from azure.servicebus.exceptions import (
    MessageSizeExceededError,
    OperationTimeoutError,
    ServiceBusError,
)
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MAX_SERVICE_BUS_RETRIES = 3

class MessageSenderClient:
    def __init__(self, sender: ServiceBusSender, message_destination: str):
        self.sender = sender
        self.message_destination = message_destination

    def send_message(self, message_data: bytes, custom_properties: Optional[Dict[str, str]] = None):
        message = ServiceBusMessage(
            body=message_data,
            application_properties=custom_properties or {}
        )

        last_error = None
        for _ in range(MAX_SERVICE_BUS_RETRIES):
            try:
                self.sender.send_messages(message)
                logger.debug("Message sent successfully to: %s", self.message_destination)
                return
            except OperationTimeoutError:
                continue
            except MessageSizeExceededError:
                raise
            except ServiceBusError as e:
                last_error = e
                continue
        if last_error:
            raise last_error
        

    def send_text_message(self, message_text: str, custom_properties: Optional[Dict[str, str]] = None):
        self.send_message(message_text.encode('utf-8'), custom_properties)

    def close(self):
        self.sender.close()
        logger.debug("ServiceBusSenderClient closed.")

    def __enter__(self):
        return self

    def close(self):
        if self.sender:
            self.sender.close()
        logger.debug("ServiceBusSenderClient closed.")

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()
