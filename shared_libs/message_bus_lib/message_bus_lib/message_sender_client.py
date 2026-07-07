import logging
from threading import Lock
from types import TracebackType
from typing import Any, Callable, Dict, Optional, Sequence

from azure.servicebus import ServiceBusMessage, ServiceBusSender
from azure.servicebus.exceptions import (
    MessageSizeExceededError,
    OperationTimeoutError,
    ServiceBusError,
)
from otel_lib import inject_trace_context

logger = logging.getLogger(__name__)

MAX_SERVICE_BUS_RETRIES = 3


class MessageSenderClient:
    def __init__(
        self,
        sender: ServiceBusSender,
        message_destination: str,
        session_id: Optional[str] = None,
        propagate_trace_context: bool = True,
        recreate_sender: Optional[Callable[[], ServiceBusSender]] = None,
    ):
        self.sender = sender
        self.session_id = session_id
        self.message_destination = message_destination
        self.propagate_trace_context = propagate_trace_context
        self._recreate_sender = recreate_sender
        self._lock = Lock()

    @staticmethod
    def _is_stale_amqp_sender_error(exc: Exception) -> bool:
        """Detect known transient SDK-internal stale AMQP link/session errors."""
        return isinstance(exc, AttributeError) and (
            "create_receiver_link" in str(exc) or "client_ready" in str(exc)
        )

    def _try_recreate_sender(self) -> bool:
        if not self._recreate_sender:
            return False

        try:
            with self._lock:
                try:
                    if self.sender:
                        self.sender.close()
                except Exception as close_exc:
                    logger.warning("Failed to close stale Service Bus sender during recovery: %s", close_exc)
                self.sender = self._recreate_sender()
            logger.info("Service Bus sender recreated for destination '%s'", self.message_destination)
            return True
        except Exception as recreate_exc:
            logger.warning("Failed to recreate Service Bus sender for '%s': %s", self.message_destination, recreate_exc)
            return False

    def send_message(
        self,
        message_data: bytes,
        custom_properties: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> None:
        props: Dict[str, Any] = dict(custom_properties) if custom_properties else {}

        if self.propagate_trace_context:
            try:
                props = inject_trace_context(props)
            except ImportError:
                pass  # otel_lib not installed — skip trace propagation

        message = ServiceBusMessage(
            body=message_data,
            application_properties=props if props else None,  # type: ignore[arg-type]
            session_id=self.session_id,
            message_id=message_id,
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
            except Exception as e:
                if self._is_stale_amqp_sender_error(e):
                    logger.warning(
                        "Detected stale AMQP sender state for '%s'. Attempting sender recreation.",
                        self.message_destination,
                    )
                    last_error = e
                    if self._try_recreate_sender():
                        continue
                raise
        if last_error:
            raise last_error

    def send_text_message(
        self,
        message_text: str,
        custom_properties: Optional[Dict[str, Any]] = None,
        message_id: Optional[str] = None,
    ) -> None:
        self.send_message(message_text.encode('utf-8'), custom_properties, message_id=message_id)

    def send_message_batch(self, messages: Sequence[ServiceBusMessage]) -> int:
        """Send pre-built ServiceBusMessages using SDK-level batching with auto-split.

        Creates a ServiceBusMessageBatch and adds messages one by one. When a message
        would exceed the batch size limit, the current batch is flushed and a new one
        is started. If a single message exceeds the max size on an empty batch, a
        ValueError is raised (unrecoverable).

        Args:
            messages: Pre-constructed ServiceBusMessage objects to send.

        Returns:
            The total number of messages sent.

        Raises:
            ValueError: If a single message exceeds the Service Bus max message size.
        """
        with self._lock:
            batch = self.sender.create_message_batch()
            messages_in_batch = 0
            total_sent = 0

            for message in messages:
                try:
                    batch.add_message(message)
                    messages_in_batch += 1
                except MessageSizeExceededError:
                    if messages_in_batch == 0:
                        raise ValueError(
                            f"Single message exceeds Service Bus max message size for '{self.message_destination}'"
                        )
                    # Flush current batch and start a new one
                    self.sender.send_messages(batch)
                    total_sent += messages_in_batch
                    logger.debug("Sent sub-batch of %d messages to '%s'", messages_in_batch, self.message_destination)
                    batch = self.sender.create_message_batch()
                    batch.add_message(message)
                    messages_in_batch = 1

            if messages_in_batch > 0:
                self.sender.send_messages(batch)
                total_sent += messages_in_batch
                logger.debug("Sent final sub-batch of %d messages to '%s'", messages_in_batch, self.message_destination)

            return total_sent

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
