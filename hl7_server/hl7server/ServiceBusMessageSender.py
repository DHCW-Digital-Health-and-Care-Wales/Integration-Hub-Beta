from azure.servicebus import ServiceBusClient, ServiceBusMessage
from typing import Optional
import os


class ServiceBusMessageSender:
    def __init__(self):
        self.connection_string = os.getenv("SERVICE_BUS_CONNECTION_STRING")
        self.queue_name = os.getenv("QUEUE_NAME")
        self._client: Optional[ServiceBusClient] = None

    def send_message(self, message_content: str) -> None:
        with ServiceBusClient.from_connection_string(
            conn_str=self.connection_string
        ) as client:
            with client.get_queue_sender(queue_name=self.queue_name) as sender:
                message = ServiceBusMessage(message_content)
                sender.send_messages(message)