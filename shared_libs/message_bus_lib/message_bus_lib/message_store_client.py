import json
import logging
from types import TracebackType

from .message_sender_client import MessageSenderClient

logger = logging.getLogger(__name__)


class MessageStoreClient:
    """Client for sending messages to the message store queue for persistence.

    Wraps a MessageSenderClient to send structured JSON events containing
    the raw (and optionally XML) message payload along with tracking metadata.

    When sender_client is None the instance is in disabled mode: send_to_store
    becomes a no-op that logs a warning per call, and close() is a no-op. Disabled
    instances are created by ServiceBusClientFactory.create_message_store_client
    when MESSAGE_STORE_ENABLED=false.
    """

    def __init__(self, sender_client: MessageSenderClient | None, microservice_id: str, peer_service: str):
        self.sender_client = sender_client
        self.microservice_id = microservice_id
        self.peer_service = peer_service

    def send_to_store(
        self,
        message_received_at: str,
        correlation_id: str,
        source_system: str,
        raw_payload: str,
        session_id: str,
        xml_payload: str | None = None,
        target_system: str | None = None,
    ) -> None:
        """Send a message to the message store queue for persistence.

        Args:
            message_received_at: ISO timestamp for when the message was received.
            correlation_id: Unique ID to track the message through the Integration Hub.
            source_system: The system that sent the message (MSH.3).
            raw_payload: The raw HL7 message.
            session_id: The Service Bus session ID of the component that stored the message.
            xml_payload: XML representation of the HL7 message (optional).
            target_system: The target system. Defaults to peer_service if not provided.
        """
        # No-op when the message store is disabled (sender_client is None).
        if self.sender_client is None:
            logger.debug("Message store is disabled — message not stored (CorrelationId: %s)", correlation_id)
            return

        store_event = {
            "MessageReceivedAt": message_received_at,
            "CorrelationId": correlation_id,
            "SourceSystem": source_system,
            "ProcessingComponent": self.microservice_id,
            "TargetSystem": target_system if target_system is not None else self.peer_service,
            "RawPayload": raw_payload,
            "XmlPayload": xml_payload,
            "SessionId": session_id,
        }
        try:
            self.sender_client.send_text_message(json.dumps(store_event))
            logger.info("Message store event sent - CorrelationId: %s", correlation_id)
        except Exception as e:
            logger.error("Failed to send message store event: %s", e)
            raise

    def close(self) -> None:
        if self.sender_client:
            self.sender_client.close()
            logger.debug("MessageStoreClient closed.")

    def __enter__(self) -> "MessageStoreClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.close()
