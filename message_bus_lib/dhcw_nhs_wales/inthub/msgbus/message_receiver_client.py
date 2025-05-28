import logging
from azure.servicebus import ServiceBusMessage, ServiceBusReceiver
from typing import Callable

from message_bus_lib.dhcw_nhs_wales.inthub.msgbus.processing_result import ProcessingResult

logger = logging.getLogger(__name__)


class MessageReceiverClient:
    def __init__(self, receiver: ServiceBusReceiver):
        self.receiver = receiver

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], ProcessingResult]):
        messages = self.receiver.receive_messages(max_message_count=num_of_messages, max_wait_time=5)

        for msg in messages:
            try:
                result = message_processor(msg)

                if result.success:
                    self.receiver.complete_message(msg)
                    logger.debug("Message processed and completed: %s", msg.message_id)

                elif result.retry is False:
                    self.receiver.abandon_message(msg)
                    logger.error("Message processing failed, message abandoned: %s", msg.message_id)

                else:
                    reason = result.get("error_reason", "Unknown error")
                    self.receiver.dead_letter_message(msg, reason=reason)
                    logger.error("Message processing failed, message dead lettered: %s", msg.message_id)

            except Exception as e:
                logger.error("Unexpected error processing message: %s", msg.message_id, exc_info=e)
                self.receiver.abandon_message(msg)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.receiver.close()
        logger.debug("ServiceBusReceiverClient closed.")
