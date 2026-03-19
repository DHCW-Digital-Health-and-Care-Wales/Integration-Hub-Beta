import logging
from types import TracebackType
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.servicebus import (
    ServiceBusClient,
    ServiceBusSender,
)

from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_receiver_client import MessageReceiverClient
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.subscription_receiver_client import SubscriptionReceiverClient

SERVICEBUS_NAMESPACE_SUFFIX = ".servicebus.windows.net"
MAX_LOCK_RENEWAL_DURATION = 300  # 5 minutes



class ServiceBusClientFactory:
    def __init__(self, config: ConnectionConfig):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.servicebus_client = self._build_service_bus_client()

    def _build_service_bus_client(self) -> ServiceBusClient:
        if self.config.is_using_connection_string():
            return ServiceBusClient.from_connection_string(self.config.connection_string)  # type: ignore
        else:
            fully_qualified_namespace = self.config.service_bus_namespace + SERVICEBUS_NAMESPACE_SUFFIX  # type: ignore
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
        return MessageReceiverClient(self.servicebus_client, queue_name, session_id)

    def create_subscription_receiver_client(
        self, topic_name: str, subscription_name: str, session_id: Optional[str] = None
    ) -> SubscriptionReceiverClient:
        self.logger.debug(
            "Creating message receiver client for topic '%s', subscription '%s' with session_id '%s'",
            topic_name,
            subscription_name,
            session_id,
        )
        return SubscriptionReceiverClient(self.servicebus_client, topic_name, subscription_name, session_id)

    def close(self) -> None:
        """Close the underlying ServiceBusClient."""
        if self.servicebus_client:
            self.servicebus_client.close()
            self.logger.debug("ServiceBusClientFactory closed")

    def __enter__(self) -> "ServiceBusClientFactory":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.close()
