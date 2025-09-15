import configparser
import logging
import os
from typing import Any

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from .app_config import AppConfig
from .death_date_filter import DeathDateFilter

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "config.ini")
config.read(config_path)

MAX_BATCH_SIZE = config.getint("DEFAULT", "max_batch_size")


def main() -> None:
    processor_manager = ProcessorManager()

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)

    # Initialize the death date filter
    death_date_filter = DeathDateFilter()

    with (
        factory.create_queue_sender_client(app_config.egress_queue_name) as sender_client,
        factory.create_message_receiver_client(app_config.ingress_queue_name) as receiver_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("WIS Filter Service started.")
        health_check_server.start()

        while processor_manager.is_running:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, sender_client, event_logger, death_date_filter),
            )


def _process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
    death_date_filter: DeathDateFilter,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    logger.debug("Received message for WIS filtering")

    try:
        event_logger.log_message_received(message_body, "Message received for WIS filtering")

        hl7_msg = parse_message(message_body)
        message_id = hl7_msg.msh.msh_10.value
        message_type = hl7_msg.msh.msh_9.to_er7()

        logger.info("Received message type: %s, Control ID: %s", message_type, message_id)

        # Apply death date filter
        filter_result = death_date_filter.should_forward_message(hl7_msg)
        _log_filter_decision(event_logger, message_body, filter_result, message_type, message_id)

        if filter_result.should_forward:
            # Forward message to WIS mapper queue
            sender_client.send_message(message_body)
            logger.info(f"Message {message_id} forwarded to WIS mapper queue")

            event_logger.log_message_processed(
                message_body,
                f"Message forwarded to WIS: {filter_result.reason}"
            )
        else:
            # Message dropped - log but don't forward
            logger.info(f"Message {message_id} dropped: {filter_result.reason}")

            event_logger.log_message_processed(
                message_body,
                f"Message dropped: {filter_result.reason}"
            )

        return True

    except HL7apyException as e:
        error_msg = f"HL7 parsing error: {e}"
        logger.error(error_msg)
        event_logger.log_message_failed(message_body, error_msg, "HL7 parsing failed")
        return False

    except Exception as e:
        error_msg = f"Unexpected error during message filtering: {e}"
        logger.error(error_msg)
        event_logger.log_message_failed(message_body, error_msg, "Unexpected filtering error")
        return False


def _log_filter_decision(
    event_logger: EventLogger,
    message_body: str,
    filter_result: Any,
    message_type: str,
    message_id: str,
) -> None:

    pid_29_ts1_populated = (filter_result.pid_29_ts1_value is not None and
                           filter_result.pid_29_ts1_value.strip() != "")
    pid_30_populated = (filter_result.pid_30_value is not None and
                       filter_result.pid_30_value.strip() != "")

    log_details = {
        "message_type": message_type,
        "message_id": message_id,
        "should_forward": filter_result.should_forward,
        "reason": filter_result.reason,
        "pid_29_ts1_populated": pid_29_ts1_populated,
        "pid_30_populated": pid_30_populated,
    }

    if filter_result.pid_29_ts1_value:
        log_details["pid_29_ts1_value"] = filter_result.pid_29_ts1_value
    if filter_result.pid_30_value:
        log_details["pid_30_value"] = filter_result.pid_30_value

    audit_message = f"WIS Filter Decision - {filter_result.reason}"
    if filter_result.should_forward:
        event_logger.log_validation_result(message_body, audit_message, is_success=True)
    else:
        event_logger.log_validation_result(message_body, audit_message, is_success=False)


if __name__ == "__main__":
    main()
