import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.dead_letter import DeadLetterMessage
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.subscription_receiver_client import SubscriptionReceiverClient
from metric_sender_lib.metric_sender import MetricSender
from processor_manager_lib import ProcessorManager

from hl7_subscription_sender.ack_processor import AckOutcome, get_ack_result
from hl7_subscription_sender.app_config import AppConfig
from hl7_subscription_sender.hl7_subscription_sender_client import HL7SubscriptionSenderClient
from hl7_subscription_sender.message_throttler import MessageThrottler

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

    # Number of messages that fit into the renewal window, accounting for intervals between sends.
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
        f"Connecting to Azure Service Bus subscription: "
        f"{app_config.ingress_topic_name}/{app_config.ingress_subscription_name}, "
        f"MLLP Receiver: {app_config.receiver_mllp_hostname}:{app_config.receiver_mllp_port}"
    )
    with (
        factory.create_subscription_receiver_client(
            app_config.ingress_topic_name,
            app_config.ingress_subscription_name,
            app_config.ingress_session_id,
        ) as subscription_receiver_client,
        HL7SubscriptionSenderClient(
            app_config.receiver_mllp_hostname,
            app_config.receiver_mllp_port,
            app_config.ack_timeout_seconds,
        ) as hl7_subscription_sender_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("Subscription processor started.")
        health_check_server.start()

        batch_size = _calculate_batch_size(throttler)

        while processor_manager.is_running:
            subscription_receiver_client.receive_messages(
                batch_size,
                lambda message: _process_message(
                    message,
                    hl7_subscription_sender_client,
                    event_logger,
                    metric_sender,
                    throttler,
                ),
            )


def _process_message(
    message: ServiceBusMessage,
    hl7_subscription_sender_client: HL7SubscriptionSenderClient,
    event_logger: EventLogger,
    metric_sender: MetricSender,
    throttler: MessageThrottler,
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
        ack_response = hl7_subscription_sender_client.send_message(message_body)

        ack_result = get_ack_result(ack_response)

        nack_attributes = {
            "ack_code": ack_result.ack_code or "UNKNOWN",
            "correlation_id": meta["correlation_id"],
            "message_id": message_id,
            "endpoint": (
                f"{hl7_subscription_sender_client.receiver_mllp_hostname}:"
                f"{hl7_subscription_sender_client.receiver_mllp_port}"
            ),
        }

        if ack_result.outcome == AckOutcome.SUCCESS:
            metric_sender.send_message_sent_metric()

            event_logger.log_message_processed(
                message_body,
                f"Message sent successfully, received ACK: {ack_response}",
                correlation_id=correlation_id_opt,
            )
            logger.info(f"Sent message: {message_id}")

            return True

        if ack_result.outcome == AckOutcome.AR:
            error_msg = (
                f"Application Reject ACK (AR) received for message {message_id} "
                f"from {nack_attributes['endpoint']}, full ACK: {ack_response}"
            )
            logger.error(error_msg)
            event_logger.log_message_failed(
                message_body,
                error_msg,
                "Non-recoverable NACK (AR) - message routed to dead-letter/escalation path",
                correlation_id=correlation_id_opt,
            )
            metric_sender.send_message_nack_ar_metric(attributes=nack_attributes)

            raise DeadLetterMessage(
                reason="AR",
                description=(
                    f"Application Reject ACK (AR) for message_id={message_id}, "
                    f"correlation_id={meta['correlation_id']}"
                ),
            )

        # AckOutcome.AE or AckOutcome.INVALID - recoverable failure, will be abandoned and retried
        # according to the queue's configured retry policy.
        reason_code = ack_result.outcome.value
        error_msg = (
            f"Negative ACK ({reason_code}) received for message {message_id} "
            f"from {nack_attributes['endpoint']}, full ACK: {ack_response}"
        )
        logger.error(error_msg)
        event_logger.log_message_failed(
            message_body,
            error_msg,
            f"Recoverable NACK ({reason_code}) - message will be retried",
            correlation_id=correlation_id_opt,
        )
        if ack_result.outcome == AckOutcome.AE:
            metric_sender.send_message_nack_ae_metric(attributes=nack_attributes)
            metric_sender.send_message_retry_attempt_metric(attributes=nack_attributes)

        return False

    except DeadLetterMessage:
        # Propagate so SubscriptionReceiverClient dead-letters the message instead of retrying it.
        raise

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
