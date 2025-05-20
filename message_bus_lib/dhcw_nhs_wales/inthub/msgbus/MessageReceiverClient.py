import logging
from azure.servicebus import ServiceBusMessage
from typing import Callable

logger = logging.getLogger("MessageReceiverClient")
logger.setLevel(logging.DEBUG)


class MessageReceiverClient:
    def __init__(self, receiver):
        self.receiver = receiver

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], dict]):
        messages = self.receiver.receive_messages(max_message_count=num_of_messages, max_wait_time=5)

        for msg in messages:
            try:
                result = message_processor(msg)

                if result.get("success"):
                    self.receiver.complete_message(msg)
                    logger.debug("Message processed and completed: %s", msg.message_id)

                elif result.get("retry", False):
                    self.receiver.abandon_message(msg)
                    logger.error("Message processing failed, message abandoned: %s", msg.message_id)

                else:
                    reason = result.get("error_reason", "Unknown error")
                    self.receiver.dead_letter_message(msg, reason=reason)
                    logger.error("Message processing failed, message dead lettered: %s", msg.message_id)

            except Exception as e:
                logger.error("Unexpected error processing message: %s", msg.message_id, exc_info=e)
                self.receiver.abandon_message(msg)

    def close(self):
        self.receiver.close()
        logger.debug("ServiceBusReceiverClient closed.")