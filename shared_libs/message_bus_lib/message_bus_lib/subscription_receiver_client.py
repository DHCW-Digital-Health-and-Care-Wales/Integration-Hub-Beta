import logging
from contextlib import AbstractContextManager
from typing import Optional

from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusReceiveMode,
    ServiceBusReceiver,
)

from message_bus_lib.message_receiver_client import MessageReceiverClient

logger = logging.getLogger(__name__)


class SubscriptionReceiverClient(MessageReceiverClient):
    def __init__(
        self, sb_client: ServiceBusClient, topic_name: str, subscription_name: str, session_id: Optional[str] = None
    ):
        super().__init__(sb_client, queue_name="", session_id=session_id)
        self.topic_name = topic_name
        self.subscription_name = subscription_name

    def _get_receiver(
        self, autolock_renewer: Optional[AutoLockRenewer] | None
    ) -> AbstractContextManager[ServiceBusReceiver]:
        return self.sb_client.get_subscription_receiver(
            topic_name=self.topic_name,
            subscription_name=self.subscription_name,
            session_id=self.session_id,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            auto_lock_renewer=autolock_renewer,
            max_wait_time=self.MAX_WAIT_TIME_SECONDS,
        )
