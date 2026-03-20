import logging
from contextlib import AbstractContextManager
from typing import Optional

from azure.servicebus import (
    ServiceBusClient,
    ServiceBusReceiver,
    ServiceBusReceiveMode,
)

from message_bus_lib.message_receiver_client import MessageReceiverClient

logger = logging.getLogger(__name__)


class SubscriptionReceiverClient(MessageReceiverClient):
    MAX_DELAY_SECONDS = 15 * 60  # 15 minutes
    INITIAL_DELAY_SECONDS = 5
    MAX_WAIT_TIME_SECONDS = 60
    LOCK_RENEWAL_DURATION_SECONDS = 5 * 60  # default AutoLockRenewer limit

    def __init__(
        self, sb_client: ServiceBusClient, topic_name: str, subscription_name: str, session_id: Optional[str] = None
    ):
        self.sb_client = sb_client
        self.topic_name = topic_name
        self.subscription_name = subscription_name
        self.session_id = session_id
        self.retry_attempt = 0
        self.delay = self.INITIAL_DELAY_SECONDS
        self.next_retry_time: Optional[float] = None

    def _get_receiver(self, autolock_renewer: object | None) -> AbstractContextManager[ServiceBusReceiver]:
        return self.sb_client.get_subscription_receiver(
            topic_name=self.topic_name,
            subscription_name=self.subscription_name,
            session_id=self.session_id,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            auto_lock_renewer=autolock_renewer,
            max_wait_time=self.MAX_WAIT_TIME_SECONDS,
        )
