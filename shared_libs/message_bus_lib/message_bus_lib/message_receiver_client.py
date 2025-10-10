import logging
import time
from types import TracebackType
from typing import Callable, Optional

from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusMessage,
    ServiceBusReceivedMessage,
    ServiceBusReceiveMode,
    ServiceBusReceiver,
)
from azure.servicebus.exceptions import SessionCannotBeLockedError

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
        self.next_retry_time: Optional[float] = None

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], bool]) -> None:
        if not self._apply_delay_and_check_if_its_retry_time():
            return

        try:
            autolock_renewer = AutoLockRenewer() if self.session_id else None
            with self.sb_client.get_queue_receiver(
                queue_name = self.queue_name,
                session_id = self.session_id,
                receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                auto_lock_renewer = autolock_renewer,
                max_wait_time = self.MAX_WAIT_TIME_SECONDS
            ) as receiver:

                messages = receiver.receive_messages(max_message_count=num_of_messages,
                                                      max_wait_time=self.MAX_WAIT_TIME_SECONDS)
                for i, msg in enumerate(messages):
                    try:
                        is_success = message_processor(msg)
                        if is_success:
                            receiver.complete_message(msg)
                            logger.debug("Message processed and completed: %s", msg.message_id)
                            self._clear_retry_state()
                        else:
                            logger.error(
                                "Message processing failed, abandoning subsequent messages: %s",
                                msg.message_id
                            )
                            self._abort_message_processing(receiver, messages[i:])
                            self._set_delay_before_retry()
                            break
                    except Exception as e:
                        logger.error("Unexpected error processing message: %s", msg.message_id, exc_info=e)
                        self._abort_message_processing(receiver, messages[i:])
                        self._set_delay_before_retry()
                        break

                autolock_renewer.close() if autolock_renewer else None
        except SessionCannotBeLockedError:
            logger.warning("Session %s cannot be locked currently. Will retry later.", self.session_id)
            time.sleep(self.MAX_WAIT_TIME_SECONDS)

    def _apply_delay_and_check_if_its_retry_time(self) -> bool:
        if self.next_retry_time:
            sleep_time = min(self.next_retry_time - time.time(), self.MAX_WAIT_TIME_SECONDS)
            if sleep_time > 0:
                logger.debug("Sleeping for : %s before retry", sleep_time)
                time.sleep(sleep_time)

            if time.time() < self.next_retry_time:
                return False
        return True

    def _clear_retry_state(self) -> None:
        self.retry_attempt = 0
        self.delay = self.INITIAL_DELAY_SECONDS
        self.next_retry_time = None

    def _abort_message_processing(
            self,
            receiver: ServiceBusReceiver,
            messages_to_abandon: list[ServiceBusReceivedMessage]
    ) -> None:

        for msg in messages_to_abandon:
            receiver.abandon_message(msg)
            logger.debug("Message abandoned: %s", msg.message_id)

    def _set_delay_before_retry(self) -> None:
        self.next_retry_time = time.time() + self.delay
        logger.info(
            "Scheduled waiting for %d seconds before next attempt (%d) to retry failes message",
            self.delay, self.retry_attempt
        )
        self.delay = min(self.delay * 2, self.MAX_DELAY_SECONDS)
        self.retry_attempt += 1

    def close(self) -> None:
        logger.debug("ServiceBusReceiverClient closed.")

    def __enter__(self) -> 'MessageReceiverClient':
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None
    ) -> None:
        self.close()
