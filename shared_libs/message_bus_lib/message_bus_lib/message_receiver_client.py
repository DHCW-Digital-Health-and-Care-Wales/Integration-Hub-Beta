import logging
import time
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Callable, Optional

import opentelemetry.context as otel_context
from azure.servicebus import (
    AutoLockRenewer,
    ServiceBusClient,
    ServiceBusMessage,
    ServiceBusReceivedMessage,
    ServiceBusReceiveMode,
    ServiceBusReceiver,
)
from azure.servicebus.exceptions import ServiceBusError, SessionCannotBeLockedError
from otel_lib import extract_trace_context

logger = logging.getLogger(__name__)


class MessageReceiverClient:
    MAX_DELAY_SECONDS = 15 * 60  # 15 minutes
    INITIAL_DELAY_SECONDS = 5
    MAX_WAIT_TIME_SECONDS = 60
    LOCK_RENEWAL_DURATION_SECONDS = 5 * 60  # default AutoLockRenewer limit

    def __init__(
        self,
        sb_client: ServiceBusClient,
        queue_name: str,
        session_id: Optional[str] = None,
        propagate_trace_context: bool = True,
    ):
        self.sb_client = sb_client
        self.queue_name = queue_name
        self.session_id = session_id
        self.propagate_trace_context = propagate_trace_context
        self.retry_attempt = 0
        self.delay = self.INITIAL_DELAY_SECONDS
        self.next_retry_time: Optional[float] = None

    def receive_messages(self, num_of_messages: int, message_processor: Callable[[ServiceBusMessage], bool]) -> None:
        """Process messages one at a time, stopping and abandoning on the first failure."""

        def per_message_adapter(receiver: ServiceBusReceiver, messages: list[ServiceBusReceivedMessage]) -> bool:
            for i, msg in enumerate(messages):
                try:
                    is_success = self._invoke_with_trace_context(message_processor, msg)
                except Exception:
                    logger.exception("Unexpected error processing message: %s", msg.message_id)
                    self._abort_message_processing(receiver, messages[i:])
                    return False
                if is_success:
                    receiver.complete_message(msg)
                    logger.debug("Message processed and completed: %s", msg.message_id)
                else:
                    logger.error("Message processing failed, abandoning subsequent messages: %s", msg.message_id)
                    self._abort_message_processing(receiver, messages[i:])
                    return False
            return True

        self._receive_and_process(num_of_messages, per_message_adapter)

    def receive_messages_batch(
        self, num_of_messages: int, batch_processor: Callable[[list[ServiceBusReceivedMessage]], bool]
    ) -> None:
        """Process all received messages together as a single batch."""

        def batch_adapter(receiver: ServiceBusReceiver, messages: list[ServiceBusReceivedMessage]) -> bool:
            is_success = batch_processor(messages)
            if is_success:
                for msg in messages:
                    receiver.complete_message(msg)
                    logger.debug("Message completed: %s", msg.message_id)
                logger.debug("Batch of %d message(s) completed", len(messages))
            else:
                logger.error("Batch processing failed, abandoning %d message(s)", len(messages))
                self._abort_message_processing(receiver, messages)
            return is_success

        self._receive_and_process(num_of_messages, batch_adapter)

    def _invoke_with_trace_context(
        self, handler: Callable[[ServiceBusReceivedMessage], bool], msg: ServiceBusReceivedMessage
    ) -> bool:
        """Call handler, restoring the W3C trace context from the message properties first."""
        if not self.propagate_trace_context:
            return handler(msg)

        try:
            props = dict(msg.application_properties or {})
            # Service Bus stores string keys as bytes in some SDK versions; normalise them.
            normalised = {k.decode() if isinstance(k, bytes) else k: v for k, v in props.items()}
            ctx = extract_trace_context(normalised)
            token = otel_context.attach(ctx)
            try:
                return handler(msg)
            finally:
                otel_context.detach(token)
        except ImportError:
            return handler(msg)

    def _receive_and_process(
        self,
        num_of_messages: int,
        processor: Callable[[ServiceBusReceiver, list[ServiceBusReceivedMessage]], bool],
    ) -> None:
        """
        Shared scaffolding for both receive_messages and receive_messages_batch.

        Handles receiver lifecycle, auto-lock renewal, empty-queue short-circuit,
        retry scheduling, and SessionCannotBeLockedError recovery. The caller
        supplies a `processor` that performs the actual complete/abandon logic and
        returns True on success or False on failure.
        """
        if not self._apply_delay_and_check_if_its_retry_time():
            return

        autolock_renewer = None
        try:
            if self.session_id:
                autolock_renewer = AutoLockRenewer()
            with self._get_receiver(autolock_renewer) as receiver:
                messages = receiver.receive_messages(
                    max_message_count=num_of_messages, max_wait_time=self.MAX_WAIT_TIME_SECONDS
                )

                if messages:
                    try:
                        is_success = processor(receiver, messages)
                        if is_success:
                            self._clear_retry_state()
                        else:
                            self._set_delay_before_retry()
                    except Exception:
                        logger.exception("Unexpected error processing %d message(s)", len(messages))
                        self._abort_message_processing(receiver, messages)
                        self._set_delay_before_retry()
        except SessionCannotBeLockedError:
            logger.warning("Session %s cannot be locked currently. Will retry later.", self.session_id)
            time.sleep(self.MAX_WAIT_TIME_SECONDS)
        except ServiceBusError as exc:
            # Transient AMQP-level errors (e.g. session not yet established, connection dropped)
            # are surfaced as ServiceBusError. Treat them as recoverable and retry after a delay.
            logger.warning("Transient Service Bus error, will retry later: %s", exc)
            self._set_delay_before_retry()
        except Exception as exc:
            # Catch unexpected SDK-internal errors such as AttributeError when the underlying
            # AMQP session is None after a dropped connection (pyamqp transport bug). The receiver
            # is created fresh on each call so there is no stale state — just schedule a retry.
            logger.warning("Unexpected error during Service Bus receive, will retry: %s", exc)
            self._set_delay_before_retry()
        finally:
            if autolock_renewer:
                autolock_renewer.close()

    def _get_receiver(
        self, autolock_renewer: AutoLockRenewer | None
    ) -> AbstractContextManager[ServiceBusReceiver]:
        return self.sb_client.get_queue_receiver(
            queue_name=self.queue_name,
            session_id=self.session_id,
            receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
            auto_lock_renewer=autolock_renewer,
            max_wait_time=self.MAX_WAIT_TIME_SECONDS,
        )

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
        self, receiver: ServiceBusReceiver, messages_to_abandon: list[ServiceBusReceivedMessage]
    ) -> None:

        for msg in messages_to_abandon:
            receiver.abandon_message(msg)
            logger.debug("Message abandoned: %s", msg.message_id)

    def _set_delay_before_retry(self) -> None:
        self.next_retry_time = time.time() + self.delay
        logger.info(
            "Scheduled waiting for %d seconds before next attempt (%d) to retry failed message",
            self.delay,
            self.retry_attempt,
        )
        self.delay = min(self.delay * 2, self.MAX_DELAY_SECONDS)
        self.retry_attempt += 1

    def close(self) -> None:
        logger.debug("ServiceBusReceiverClient closed.")

    def __enter__(self) -> "MessageReceiverClient":
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None
    ) -> None:
        self.close()
