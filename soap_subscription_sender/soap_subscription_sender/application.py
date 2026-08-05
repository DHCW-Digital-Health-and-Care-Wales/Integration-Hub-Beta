"""SOAP Subscription Sender — application entry point.

Mirrors ``hl7_subscription_sender/application.py`` exactly except:
- Uses ``SOAPSubscriptionSenderClient`` (HTTP/SOAP) instead of ``HL7SubscriptionSenderClient`` (MLLP)
- Calls ``get_ack_result(status_code, body)`` instead of ``get_ack_result(ack_response)``
- No ``MessageStoreClient`` — consistent with ``hl7_subscription_sender``
- No ``convert_er7_to_xml`` / ``hl7apy`` parsing beyond metadata extraction
"""
import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.subscription_receiver_client import SubscriptionReceiverClient
from metric_sender_lib.metric_sender import MetricSender
from processor_manager_lib import ProcessorManager

from soap_subscription_sender.app_config import AppConfig
from soap_subscription_sender.message_throttler import MessageThrottler
from soap_subscription_sender.soap_ack_processor import get_ack_result
from soap_subscription_sender.soap_subscription_sender_client import SOAPSubscriptionSenderClient

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

    max_processing_window = SubscriptionReceiverClient.LOCK_RENEWAL_DURATION_SECONDS - LOCK_RENEWAL_BUFFER_SECONDS
    if max_processing_window <= 0:
        return 1

    allowable_messages = int(max_processing_window // interval) + 1
    batch_size = max(1, min(MAX_BATCH_SIZE, allowable_messages))

    if batch_size < MAX_BATCH_SIZE:
        logger.warning(
            "Reducing batch size from %d to %d to stay within the lock renewal window (%ds limit, %.2fs interval).",
            MAX_BATCH_SIZE,
            batch_size,
            SubscriptionReceiverClient.LOCK_RENEWAL_DURATION_SECONDS,
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

    logger.info(
        "Connecting to Azure Service Bus subscription: %s/%s, SOAP endpoint: %s",
        app_config.ingress_topic_name,
        app_config.ingress_subscription_name,
        app_config.soap_endpoint_url,
    )
    with (
        factory.create_subscription_receiver_client(
            app_config.ingress_topic_name,
            app_config.ingress_subscription_name,
            app_config.ingress_session_id,
        ) as subscription_receiver_client,
        SOAPSubscriptionSenderClient(
            app_config.soap_endpoint_url,
            app_config.soap_timeout_seconds,
            app_config.soap_api_key,
            app_config.soap_client_cert_path,
        ) as soap_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("SOAP subscription sender started.")
        health_check_server.start()

        batch_size = _calculate_batch_size(throttler)

        while processor_manager.is_running:
            subscription_receiver_client.receive_messages(
                batch_size,
                lambda message: _process_message(
                    message,
                    soap_client,
                    event_logger,
                    metric_sender,
                    throttler,
                ),
            )


def _process_message(
    message: ServiceBusMessage,
    soap_client: SOAPSubscriptionSenderClient,
    event_logger: EventLogger,
    metric_sender: MetricSender,
    throttler: MessageThrottler,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    metadata: dict[str, str] | None = extract_metadata(message)
    meta = get_metadata_log_values(metadata)
    correlation_id_opt = correlation_id_for_logger(meta)
    logger.info(
        "Message received for SOAP sending - CorrelationId: %s, WorkflowID: %s, "
        "SourceSystem: %s, MessageReceivedAt: %s",
        meta["correlation_id"],
        meta["workflow_id"],
        meta["source_system"],
        meta["message_received_at"],
    )

    message_id = "UNKNOWN"
    try:
        event_logger.log_message_received(
            message_body, "Message received for SOAP sending", correlation_id=correlation_id_opt
        )

        # Extract message ID from MSH-10 for logging — no hl7apy dependency.
        segments = message_body.splitlines()
        if segments:
            msh_fields = segments[0].split("|")
            message_id = msh_fields[9] if len(msh_fields) > 9 else "UNKNOWN"
        logger.info("Message ID: %s", message_id)

        throttler.wait_if_needed()
        status_code, response_body = soap_client.send_message(message_body)
        ack_success = get_ack_result(status_code, response_body)

        if ack_success:
            metric_sender.send_message_sent_metric()

        event_logger.log_message_processed(
            message_body,
            f"Message sent successfully, HTTP status: {status_code}",
            correlation_id=correlation_id_opt,
        )
        logger.info("Sent message: %s", message_id)

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


if __name__ == "__main__":
    main()
