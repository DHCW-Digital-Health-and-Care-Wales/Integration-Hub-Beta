from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.identity import DefaultAzureCredential
from typing import Optional
from .ServiceBusConfig import ServiceBusConfig


class ServiceBusMessageSender:
    def __init__(self):
        self.config = ServiceBusConfig.from_env()
        self._client: Optional[ServiceBusClient] = None

    def send_message(self, message_content: str) -> None:
        if self.config.is_local_setup():
            client = ServiceBusClient.from_connection_string(
                conn_str=self.config.connection_string
            )
        else:
            # Use namespace for cloud environment
            fully_qualified_namespace = f"{self.config.namespace}.servicebus.windows.net"
            credential = DefaultAzureCredential()
            client = ServiceBusClient(
                fully_qualified_namespace=fully_qualified_namespace,
                credential=credential
            )

        with client:
            with client.get_queue_sender(queue_name=self.config.queue_name) as sender:
                message = ServiceBusMessage(message_content)
                sender.send_messages(message)