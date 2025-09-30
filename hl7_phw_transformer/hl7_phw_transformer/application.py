import configparser
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from hl7apy.core import Field
from hl7apy.parser import parse_message
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from processor_manager_lib import ProcessorManager

from .app_config import AppConfig
from .date_of_death_transformer import transform_date_of_death
from .datetime_transformer import transform_datetime

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
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

    with (
        factory.create_queue_sender_client(
            app_config.egress_queue_name, app_config.egress_session_id
        ) as sender_client,
        factory.create_message_receiver_client(
            app_config.ingress_queue_name, app_config.ingress_session_id
        ) as receiver_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info("Processor started.")
        health_check_server.start()

        while processor_manager.is_running:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_message(message, sender_client, event_logger),
            )


def _process_message(
    message: ServiceBusMessage,
    sender_client: MessageSenderClient,
    event_logger: EventLogger,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    logger.debug("Received message")

    try:
        event_logger.log_message_received(message_body, "Message received for transformation")

        hl7_msg = parse_message(message_body)
        msh_segment = hl7_msg.msh
        message_id = msh_segment.msh_10.value
        logger.debug(f"Message ID: {message_id}")

        transformations_applied = []

        created_datetime = msh_segment.msh_7.value

        transformed_datetime = transform_datetime(created_datetime)
        msh_segment.msh_7.value = transformed_datetime

        transformations_applied.append(
                f"DateTime transformed from {created_datetime} to {transformed_datetime}"
            )

        pid_segment = getattr(hl7_msg, "pid", None)
        if pid_segment:
            dod_field = getattr(pid_segment, "pid_29", None)
            original_dod = getattr(dod_field, "value", dod_field)

            if original_dod is not None:
                transformed_dod = transform_date_of_death(original_dod)

                if isinstance(dod_field, Field) and hasattr(dod_field, "value"):
                    dod_field.value = transformed_dod
                else:
                    pid_segment.pid_29 = transformed_dod

                if original_dod != transformed_dod:
                    transformations_applied.append(
                        f"Date of death transformed from {original_dod} to {transformed_dod}"
                    )

                    if original_dod and original_dod.strip().upper() == "RESURREC":
                        logger.info(f"Converted RESURREC date of death for message {message_id}")

        updated_message = hl7_msg.to_er7()
        sender_client.send_message(updated_message)

        if transformations_applied:
            transformation_summary = "; ".join(transformations_applied)
            audit_message = f"HL7 transformations applied: {transformation_summary}"
        else:
            audit_message = "HL7 message processed successfully with no transformations required"

        event_logger.log_message_processed(message_body, audit_message)

        return True

    except ValueError as e:
        error_msg = f"Failed to transform datetime: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "DateTime transformation failed")

        return False

    except Exception as e:
        error_msg = f"Unexpected error during message processing: {e}"
        logger.error(error_msg)

        event_logger.log_message_failed(message_body, error_msg, "Unexpected processing error")

        return False


if __name__ == "__main__":
    main()
