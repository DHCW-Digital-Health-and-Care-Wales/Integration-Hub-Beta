import logging
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusReceiveMode,
    ServiceBusReceiver,
    ServiceBusSender,
)

from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_receiver_client import MessageReceiverClient
from message_bus_lib.message_sender_client import MessageSenderClient

SERVICEBUS_NAMESPACE_SUFFIX = ".servicebus.windows.net"
MAX_LOCK_RENEWAL_DURATION = 300 # 5 minutes

class ServiceBusClientFactory:
    def __init__(self, config: ConnectionConfig):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.servicebus_client = self._build_service_bus_client()

    def _build_service_bus_client(self) -> ServiceBusClient:
        if self.config.is_using_connection_string():
            return ServiceBusClient.from_connection_string(self.config.connection_string) # type: ignore
        else:
            fully_qualified_namespace = self.config.service_bus_namespace + SERVICEBUS_NAMESPACE_SUFFIX # type: ignore
            credential = DefaultAzureCredential()
            return ServiceBusClient(fully_qualified_namespace, credential)

    def create_topic_sender_client(self, topic_name: str, session_id: Optional[str] = None) -> MessageSenderClient:
        self.logger.debug("Creating message sender client for topic '%s' with session_id '%s'", topic_name, session_id)
        sender: ServiceBusSender = self.servicebus_client.get_topic_sender(topic_name=topic_name)
        return MessageSenderClient(sender, topic_name, session_id)

    def create_queue_sender_client(self, queue_name: str, session_id: Optional[str] = None) -> MessageSenderClient:
        self.logger.debug("Creating message sender client for queue '%s' with session_id '%s'", queue_name, session_id)
        sender: ServiceBusSender = self.servicebus_client.get_queue_sender(queue_name=queue_name)
        return MessageSenderClient(sender, queue_name, session_id)

    def create_message_receiver_client(
            self, queue_name: str, session_id: Optional[str] = None
    ) -> MessageReceiverClient:
        self.logger.debug(
            "Creating message receiver client for queue '%s' with session_id '%s'", queue_name, session_id
        )

        lock_renewal = AutoLockRenewer(max_lock_renewal_duration=MAX_LOCK_RENEWAL_DURATION) if session_id else None

        receiver: ServiceBusReceiver = self.servicebus_client.get_queue_receiver(
            queue_name=queue_name,
            session_id=session_id,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            lock_renewal=lock_renewal,
        )

        return MessageReceiverClient(receiver, session_id)
