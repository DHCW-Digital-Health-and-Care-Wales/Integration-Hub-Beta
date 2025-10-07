import logging
import time
from types import TracebackType
from typing import Callable, Optional

from azure.servicebus import ServiceBusMessage, ServiceBusReceivedMessage, ServiceBusReceiver

logger = logging.getLogger(__name__)


class MessageReceiverClient:
    MAX_DELAY_SECONDS = 15 * 60 # 15 minutes
    INITIAL_DELAY_SECONDS = 5
    MAX_WAIT_TIME_SECONDS = 5

    def __init__(self, receiver: ServiceBusReceiver, session_id: Optional[str] = None):
        self.receiver = receiver
        self.session_id = session_id
        self.retry_attempt = 0
        self.delay = self.INITIAL_DELAY_SECONDS

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], bool]) -> None:

        while True:
            messages = self.receiver.receive_messages(max_message_count=num_of_messages,
                                                      max_wait_time=self.MAX_WAIT_TIME_SECONDS)

            for msg in messages:
                try:
                    is_success = message_processor(msg)

                    if is_success:
                        self.receiver.complete_message(msg)
                        logger.debug("Message processed and completed: %s", msg.message_id)
                        self.retry_attempt = 0
                        self.delay = self.INITIAL_DELAY_SECONDS

                    else:
                        logger.error("Message processing failed, message abandoned: %s", msg.message_id)
                        self._abandon_message_and_delay(msg)
                        break

                except Exception as e:
                    logger.error("Unexpected error processing message: %s", msg.message_id, exc_info=e)
                    self._abandon_message_and_delay(msg)
                    break

            if self.retry_attempt == 0 or not messages:
                break

    def _abandon_message_and_delay(self, msg: ServiceBusReceivedMessage) -> None:
        self.receiver.abandon_message(msg)
        self.retry_attempt += 1
        self._apply_backoff(msg)
        self.delay = min(self.delay * 2, self.MAX_DELAY_SECONDS)

    def _apply_backoff(self, msg: ServiceBusMessage) -> None:
        logger.error(
            "Retry attempt %d, waiting for %d seconds before retrying message: %s",
            self.retry_attempt, self.delay, msg.message_id
        )
        time.sleep(self.delay)

    def close(self) -> None:
        self.receiver.close()
        logger.debug("ServiceBusReceiverClient closed.")

    def __enter__(self) -> 'MessageReceiverClient':
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None
    ) -> None:
        self.close()
