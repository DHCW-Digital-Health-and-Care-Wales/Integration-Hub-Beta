import logging
import time
from types import TracebackType
from typing import Callable, Optional

from azure.servicebus import AutoLockRenewer, ServiceBusClient, ServiceBusMessage, ServiceBusReceiveMode

logger = logging.getLogger(__name__)


class MessageReceiverClient:
    MAX_DELAY_SECONDS = 15 * 60 # 15 minutes
    INITIAL_DELAY_SECONDS = 5
    MAX_WAIT_TIME_SECONDS = 60

    def __init__(self, sb_client: ServiceBusClient, queue_name: str, session_id: Optional[str] = None):
        self.sb_client = sb_client
        self.queue_name = queue_name
        self.session_id = session_id
        self.retry_attempt = 0
        self.delay = self.INITIAL_DELAY_SECONDS

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], bool]) -> None:

        autolock_renewer = AutoLockRenewer() if self.session_id else None
        with self.sb_client.get_queue_receiver(
            queue_name = self.queue_name,
            session_id = self.session_id,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            auto_lock_renewer = autolock_renewer,
            max_wait_time = self.MAX_WAIT_TIME_SECONDS
        ) as receiver:
            for msg in receiver:
                is_success = message_processor(msg)
                if is_success:
                    receiver.complete_message(msg)
                    logger.info("Message processed and completed: %s", msg.message_id)
                else:
                    logger.error("Message processing failed, message abandoned: %s", msg.message_id)
                    receiver.abandon_message(msg)
                    time.sleep(self.INITIAL_DELAY_SECONDS)
                    break
            autolock_renewer.close() if autolock_renewer else None

    def close(self) -> None:
        pass

    def __enter__(self) -> 'MessageReceiverClient':
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None
    ) -> None:
        self.close()
