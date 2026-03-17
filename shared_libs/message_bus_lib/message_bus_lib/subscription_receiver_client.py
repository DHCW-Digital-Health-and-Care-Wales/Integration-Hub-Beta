import logging
import time
from typing import Callable, Optional

from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusMessage,
    ServiceBusReceiveMode,
)
from azure.servicebus.exceptions import SessionCannotBeLockedError

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

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], bool]) -> None:
        if not self._apply_delay_and_check_if_its_retry_time():
            return

        try:
            autolock_renewer = AutoLockRenewer() if self.session_id else None
            with self.sb_client.get_subscription_receiver(
                topic_name=self.topic_name,
                subscription_name=self.subscription_name,
                session_id=self.session_id,
                receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                auto_lock_renewer=autolock_renewer,
                max_wait_time=self.MAX_WAIT_TIME_SECONDS,
            ) as receiver:
                messages = receiver.receive_messages(
                    max_message_count=num_of_messages, max_wait_time=self.MAX_WAIT_TIME_SECONDS
                )
                for i, msg in enumerate(messages):
                    try:
                        is_success = message_processor(msg)
                        if is_success:
                            receiver.complete_message(msg)
                            logger.debug("Message processed and completed: %s", msg.message_id)
                            self._clear_retry_state()
                        else:
                            logger.error(
                                "Message processing failed, abandoning subsequent messages: %s", msg.message_id
                            )
                            self._abort_message_processing(receiver, messages[i:])
                            self._set_delay_before_retry()
                            break
                    except Exception as e:
                        logger.error("Unexpected error processing message: %s", msg.message_id, exc_info=e)
                        self._abort_message_processing(receiver, messages[i:])
                        self._set_delay_before_retry()
                        break
                    finally:
                        if autolock_renewer:
                            autolock_renewer.close()

        except SessionCannotBeLockedError as e:
            logger.warning(
                "Session cannot be locked. This may occur if another instance is "
                "processing messages for the same session. Exception: %s",
                str(e),
            )
            time.sleep(self.MAX_WAIT_TIME_SECONDS)
