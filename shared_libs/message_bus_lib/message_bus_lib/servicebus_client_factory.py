from azure.servicebus import ServiceBusClient, ServiceBusSender, ServiceBusReceiver, ServiceBusReceiveMode
from azure.identity import DefaultAzureCredential

from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_receiver_client import MessageReceiverClient
from message_bus_lib.message_sender_client import MessageSenderClient

SERVICEBUS_NAMESPACE_SUFFIX = ".servicebus.windows.net"


class ServiceBusClientFactory:
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.servicebus_client = self._build_service_bus_client()

    def _build_service_bus_client(self) -> ServiceBusClient:
        if self.config.is_using_connection_string():
            return ServiceBusClient.from_connection_string(self.config.connection_string)
        else:
            fully_qualified_namespace = self.config.service_bus_namespace + SERVICEBUS_NAMESPACE_SUFFIX
            credential = DefaultAzureCredential()
            return ServiceBusClient(fully_qualified_namespace, credential)

    def create_topic_sender_client(self, topic_name: str) -> MessageSenderClient:
        sender: ServiceBusSender = self.servicebus_client.get_topic_sender(topic_name=topic_name)
        return MessageSenderClient(sender, topic_name)

    def create_queue_sender_client(self, queue_name: str) -> MessageSenderClient:
        sender: ServiceBusSender = self.servicebus_client.get_queue_sender(queue_name=queue_name)
        return MessageSenderClient(sender, queue_name)

    def create_message_receiver_client(self, queue_name: str) -> MessageReceiverClient:
        receiver: ServiceBusReceiver = self.servicebus_client.get_queue_receiver(
            queue_name=queue_name,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK
        )
        return MessageReceiverClient(receiver)
