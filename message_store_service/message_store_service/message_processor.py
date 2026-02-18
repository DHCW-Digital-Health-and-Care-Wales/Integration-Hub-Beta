import logging

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger

logger = logging.getLogger(__name__)


def process_message(message: ServiceBusMessage, event_logger: EventLogger) -> bool:
    try:
        message_body = b"".join(message.body).decode("utf-8")

        correlation_id = message.correlation_id

        # TODO: Store message in Azure Database
        logger.info(f"Message received (correlation_id={correlation_id})")

        return True

    except Exception as e:
        logger.error(f"Failed to process message: {e}")
        try:
            event_logger.log_message_failed(
                message_body if message_body is not None else "<message decode failed>",
                f"Failed to process message: {e}",
                "Message processing failed",
                correlation_id=message.correlation_id if message else None
            )
        except Exception as log_error:
            logger.error(f"Failed to log error: {log_error}")
        return False

