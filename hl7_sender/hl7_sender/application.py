import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7_validation import convert_er7_to_xml
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_receiver_client import MessageReceiverClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.metadata_utils import (
    CORRELATION_ID_KEY,
    MESSAGE_RECEIVED_AT_KEY,
    SOURCE_SYSTEM_KEY,
    correlation_id_for_logger,
    extract_metadata,
    get_metadata_log_values,
)
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender
from processor_manager_lib import ProcessorManager

from hl7_sender.ack_processor import get_ack_result
from hl7_sender.app_config import AppConfig
from hl7_sender.hl7_sender_client import HL7SenderClient
from hl7_sender.message_throttler import MessageThrottler

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "config.ini")
config.read(config_path)

MAX_BATCH_SIZE = config.getint("DEFAULT", "max_batch_size")
LOCK_RENEWAL_BUFFER_SECONDS = 30


def _calculate_batch_size(throttler: MessageThrottler) -> int:
    interval = throttler.interval_seconds
    if interval is None:
        return MAX_BATCH_SIZE

    max_processing_window = MessageReceiverClient.LOCK_RENEWAL_DURATION_SECONDS - LOCK_RENEWAL_BUFFER_SECONDS
    if max_processing_window <= 0:
        return 1

    # Number of messages that fit into the renewal window, accounting for intervals between sends.
    allowable_messages = int(max_processing_window // interval) + 1
    batch_size = max(1, min(MAX_BATCH_SIZE, allowable_messages))

    if batch_size < MAX_BATCH_SIZE:
        logger.warning(
            "Reducing batch size from %d to %d to stay within the lock renewal window (%ds limit, %.2fs interval).",
            MAX_BATCH_SIZE,
            batch_size,
            MessageReceiverClient.LOCK_RENEWAL_DURATION_SECONDS,
            interval,
        )

    return batch_size


def main() -> None:
    processor_manager = ProcessorManager()

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
    metric_sender = MetricSender(
        app_config.workflow_id, app_config.microservice_id, app_config.health_board, app_config.peer_service
    )
    throttler = MessageThrottler(app_config.max_messages_per_minute)

    message_store_sender = factory.create_queue_sender_client(app_config.message_store_queue_name)
    message_store_client = MessageStoreClient(message_store_sender, app_config.microservice_id, app_config.peer_service)
    logger.info(f"Configured message store queue: {app_config.message_store_queue_name}")

    with (
        factory.create_message_receiver_client(
            app_config.ingress_queue_name, app_config.ingress_session_id
        ) as receiver_client,
        HL7SenderClient(
            app_config.receiver_mllp_hostname, app_config.receiver_mllp_port, app_config.ack_timeout_seconds
        ) as hl7_sender_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
        message_store_client,
    ):
        logger.info("Processor started.")
        health_check_server.start()

        batch_size = _calculate_batch_size(throttler)

        while processor_manager.is_running:
            receiver_client.receive_messages(
                batch_size,
                lambda message: _process_message(
                    message, hl7_sender_client, event_logger, metric_sender, throttler, message_store_client
                ),
            )


def _process_message(
    message: ServiceBusMessage,
    hl7_sender_client: HL7SenderClient,
    event_logger: EventLogger,
    metric_sender: MetricSender,
    throttler: MessageThrottler,
    message_store_client: MessageStoreClient,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    metadata: dict[str, str] | None = extract_metadata(message)
    meta = get_metadata_log_values(metadata)
    correlation_id_opt = correlation_id_for_logger(meta)
    logger.info(
        "Message received for HL7 sending - CorrelationId: %s, WorkflowID: %s, SourceSystem: %s, MessageReceivedAt: %s",
        meta["correlation_id"],
        meta["workflow_id"],
        meta["source_system"],
        meta["message_received_at"],
    )

    try:
        event_logger.log_message_received(
            message_body, "Message received for HL7 sending", correlation_id=correlation_id_opt
        )

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        message_id = msh_segment.msh_10.value
        logger.info(f"Message ID: {message_id}")

        throttler.wait_if_needed()
        ack_response = hl7_sender_client.send_message(message_body)

        ack_success = get_ack_result(ack_response)

        if ack_success:
            metric_sender.send_message_sent_metric()

        _send_to_message_store(message_store_client, message_body, metadata)

        event_logger.log_message_processed(
            message_body,
            f"Message sent successfully, received ACK: {ack_response}",
            correlation_id=correlation_id_opt,
        )
        logger.info(f"Sent message: {message_id}")

        return ack_success

    except (TimeoutError, ConnectionError) as e:
        error_msg = f"Failed to send message {message_id}: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(
            message_body,
            error_msg,
            "Message sending failed - connection/timeout error",
            correlation_id=correlation_id_opt,
        )

        return False

    except Exception as e:
        error_msg = f"Unexpected error while processing message: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(
            message_body,
            error_msg,
            "Unexpected processing error",
            correlation_id=correlation_id_opt,
        )

        return False


def _send_to_message_store(
    message_store_client: MessageStoreClient,
    message_body: str,
    metadata: dict[str, str] | None,
) -> None:
    """Send a message to the message store queue with XML payload."""
    try:
        xml_payload: str | None = None
        try:
            xml_payload = convert_er7_to_xml(message_body)
        except Exception as e:
            logger.warning("Failed to generate XML payload for message store: %s", e)

        incoming_metadata = metadata or {}
        message_store_client.send_to_store(
            message_received_at=incoming_metadata.get(MESSAGE_RECEIVED_AT_KEY, ""),
            correlation_id=incoming_metadata.get(CORRELATION_ID_KEY, ""),
            source_system=incoming_metadata.get(SOURCE_SYSTEM_KEY, ""),
            raw_payload=message_body,
            xml_payload=xml_payload,
        )
    except Exception as e:
        logger.error("Failed to send to message store: %s", e)


if __name__ == "__main__":
    main()
