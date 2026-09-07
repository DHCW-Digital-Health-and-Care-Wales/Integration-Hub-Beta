"""SOAP Sender — main application entry point.

Mirrors ``hl7_sender/application.py`` exactly in structure.  The only
meaningful differences are:
  - ``SOAPSenderClient`` replaces ``HL7SenderClient``
  - ``get_ack_result(status_code, body)`` replaces ``get_ack_result(mllp_response)``
  - App config reads ``SOAP_ENDPOINT_URL`` instead of MLLP host/port

Everything else — Service Bus queue consumption, message store integration,
batch sizing, throttling, event logging, metrics, health check — is identical.
"""
from __future__ import annotations

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
from otel_lib import configure_otel
from processor_manager_lib import ProcessorManager

from soap_sender.app_config import AppConfig
from soap_sender.message_throttler import MessageThrottler
from soap_sender.soap_ack_processor import get_ack_result
from soap_sender.soap_sender_client import SOAPSenderClient

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
    configure_otel("soap-sender")
    processor_manager = ProcessorManager()

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
    metric_sender = MetricSender(
        app_config.workflow_id, app_config.microservice_id, app_config.health_board, app_config.peer_service
    )
    throttler = MessageThrottler(app_config.max_messages_per_minute)

    message_store_client = factory.create_message_store_client(
        app_config.message_store_queue_name, app_config.microservice_id, app_config.peer_service
    )

    logger.info(
        "SOAP Sender starting — endpoint: %s, queue: %s, ws_security: %s",
        app_config.soap_endpoint_url,
        app_config.ingress_queue_name,
        app_config.ws_security_enabled,
    )

    with (
        factory.create_message_receiver_client(
            app_config.ingress_queue_name, app_config.ingress_session_id
        ) as receiver_client,
        SOAPSenderClient(
            app_config.soap_endpoint_url,
            app_config.soap_timeout_seconds,
            app_config.soap_api_key,
            app_config.soap_client_cert_path,
        ) as soap_sender_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
        message_store_client,
    ):
        logger.info("SOAP Sender processor started.")
        health_check_server.start()

        batch_size = _calculate_batch_size(throttler)

        def message_processor(message: ServiceBusMessage) -> bool:
            return _process_message(
                message, soap_sender_client, event_logger, metric_sender,
                throttler, message_store_client, app_config.ingress_session_id,
            )

        wrapped_processor = processor_manager.wrap_handler(
            message_processor, "soap-sender", app_config.ingress_queue_name
        )
        while processor_manager.is_running:
            receiver_client.receive_messages(batch_size, wrapped_processor)


def _process_message(
    message: ServiceBusMessage,
    soap_sender_client: SOAPSenderClient,
    event_logger: EventLogger,
    metric_sender: MetricSender,
    throttler: MessageThrottler,
    message_store_client: MessageStoreClient,
    session_id: str,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    metadata: dict[str, str] | None = extract_metadata(message)
    meta = get_metadata_log_values(metadata)
    correlation_id_opt = correlation_id_for_logger(meta)

    logger.info(
        "Message received for SOAP sending — CorrelationId: %s, WorkflowID: %s, SourceSystem: %s",
        meta["correlation_id"],
        meta["workflow_id"],
        meta["source_system"],
    )

    try:
        event_logger.log_message_received(
            message_body, "Message received for SOAP sending", correlation_id=correlation_id_opt
        )

        hl7_msg = parse_message(message_body)
        message_id = hl7_msg.msh.msh_10.value
        logger.info("Message ID: %s", message_id)

        if _is_first_delivery_attempt(message):
            _send_to_message_store(message_store_client, event_logger, message_body, metadata, session_id)
        else:
            logger.info(
                "Skipping message store on retry — CorrelationId: %s, DeliveryCount: %s",
                meta["correlation_id"],
                getattr(message, "delivery_count", "N/A"),
            )

        throttler.wait_if_needed()
        status_code, response_body = soap_sender_client.send_message(message_body)

        ack_success = get_ack_result(status_code, response_body)

        if ack_success:
            metric_sender.send_message_sent_metric()

        event_logger.log_message_processed(
            message_body,
            f"SOAP send result: HTTP {status_code}, success={ack_success}",
            correlation_id=correlation_id_opt,
        )
        logger.info("SOAP send complete — message_id=%s, success=%s", message_id, ack_success)
        return ack_success

    except (TimeoutError, ConnectionError) as e:
        error_msg = f"Failed to send message via SOAP: {e}"
        logger.error(error_msg)
        event_logger.log_message_failed(
            message_body, error_msg, "SOAP send failed — connection/timeout error",
            correlation_id=correlation_id_opt,
        )
        return False

    except Exception as e:
        error_msg = f"Unexpected error while processing message: {e}"
        logger.error(error_msg)
        event_logger.log_message_failed(
            message_body, error_msg, "Unexpected processing error",
            correlation_id=correlation_id_opt,
        )
        return False


def _is_first_delivery_attempt(message: ServiceBusMessage) -> bool:
    delivery_count = getattr(message, "delivery_count", 0)
    try:
        return int(delivery_count) <= 0
    except (TypeError, ValueError):
        return True


def _send_to_message_store(
    message_store_client: MessageStoreClient,
    event_logger: EventLogger,
    message_body: str,
    metadata: dict[str, str] | None,
    session_id: str,
) -> None:
    try:
        incoming_metadata = metadata or {}
        xml_payload: str | None = None
        try:
            xml_payload = convert_er7_to_xml(message_body)
        except Exception as e:
            logger.error("Failed to generate XML payload for message store: %s", e)
            event_logger.log_validation_result(
                message_body, f"XML conversion failed: {e}", is_success=False,
                correlation_id=incoming_metadata.get(CORRELATION_ID_KEY, ""),
            )
        message_store_client.send_to_store(
            message_received_at=incoming_metadata.get(MESSAGE_RECEIVED_AT_KEY, ""),
            correlation_id=incoming_metadata.get(CORRELATION_ID_KEY, ""),
            source_system=incoming_metadata.get(SOURCE_SYSTEM_KEY, ""),
            raw_payload=message_body,
            session_id=session_id,
            xml_payload=xml_payload,
        )
    except Exception as e:
        logger.error("Failed to send to message store: %s", e)


if __name__ == "__main__":
    main()
