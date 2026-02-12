import logging
from threading import Lock
from types import TracebackType
from typing import Dict, Optional

from azure.servicebus import ServiceBusMessage, ServiceBusSender
from azure.servicebus.exceptions import (
    MessageSizeExceededError,
    OperationTimeoutError,
    ServiceBusError,
)

logger = logging.getLogger(__name__)

MAX_SERVICE_BUS_RETRIES = 3

class MessageSenderClient:
    def __init__(self, sender: ServiceBusSender, message_destination: str, session_id: Optional[str] = None):
        self.sender = sender
        self.session_id = session_id
        self.message_destination = message_destination
        self._lock = Lock()

    def send_message(self, message_data: bytes, custom_properties: Optional[Dict[str, str]] = None) -> None:
        message = ServiceBusMessage(
            body=message_data,
            application_properties=custom_properties.copy() if custom_properties else {}, # type: ignore
            session_id=self.session_id,
        )

        last_error = None
        for _ in range(MAX_SERVICE_BUS_RETRIES):
            try:
                # Acquire lock to ensure thread-safe access to the sender
                with self._lock:
                    self.sender.send_messages(message)
                logger.debug("Message sent successfully to: %s", self.message_destination)
                return
            except OperationTimeoutError:
                continue
            except MessageSizeExceededError:
                raise
            except ServiceBusError as e:
                last_error = e
                continue
        if last_error:
            raise last_error

    def send_text_message(self, message_text: str, custom_properties: Optional[Dict[str, str]] = None) -> None:
        self.send_message(message_text.encode('utf-8'), custom_properties)

    def __enter__(self) -> "MessageSenderClient":
        return self

    def close(self) -> None:
        if self.sender:
            # Acquire lock to ensure thread-safe access to the sender during close
            with self._lock:
                self.sender.close()
        logger.debug("ServiceBusSenderClient closed.")

    def __exit__(
        self, exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None
    ) -> None:
        self.close()
