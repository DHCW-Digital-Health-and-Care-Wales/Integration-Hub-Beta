import json
import logging
import os
import signal
import configparser
from typing import Any

from azure.servicebus import ServiceBusMessage
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from message_bus_lib.processing_result import ProcessingResult
from health_check_lib.health_check_server import TCPHealthCheckServer

from .app_config import MonitoringAppConfig
from .database_client import MonitoringDatabaseClient

# Configure logging
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "config.ini")
config.read(config_path)

MAX_BATCH_SIZE = config.getint("DEFAULT", "max_batch_size", fallback=10)
PROCESSOR_RUNNING = True


def shutdown_handler(signum: int, frame: Any) -> None:
    global PROCESSOR_RUNNING
    logger.info("Shutting down the monitoring service")
    PROCESSOR_RUNNING = False


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


def main() -> None:
    global PROCESSOR_RUNNING
    
    app_config = MonitoringAppConfig.read_env_config()
    client_config = ConnectionConfig(
        app_config.connection_string,
        app_config.service_bus_namespace
    )
    factory = ServiceBusClientFactory(client_config)

    db_client = MonitoringDatabaseClient(
        app_config.database_connection_string,
        app_config.stored_procedure_name
    )
    
    with (
        factory.create_message_receiver_client(app_config.audit_queue_name) as receiver_client,
        db_client,
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
    ):
        logger.info(f"Monitoring service started with stored procedure: {app_config.stored_procedure_name}")
        health_check_server.start()
        
        while PROCESSOR_RUNNING:
            receiver_client.receive_messages(
                MAX_BATCH_SIZE,
                lambda message: _process_audit_message(message, db_client),
            )
        
        logger.info("Monitoring service stopped.")


def _process_audit_message(
    message: ServiceBusMessage,
    db_client: MonitoringDatabaseClient
) -> ProcessingResult:
    try:
        message_body = b"".join(message.body).decode("utf-8")
        logger.debug(f"Received audit message: {message_body}")
        
        # Parse the audit event JSON
        audit_event = json.loads(message_body)
        
        # Determine if this is an error event or regular event
        event_type = audit_event.get("event_type", "")
        is_error = event_type in ["MESSAGE_FAILED", "VALIDATION_FAILED"]
        
        if is_error:
            db_client.insert_exception_event(audit_event)
            logger.debug(f"Stored exception event: {event_type}")
        else:
            db_client.insert_audit_event(audit_event)
            logger.debug(f"Stored audit event: {event_type}")
        
        return ProcessingResult.successful()
        
    except json.JSONDecodeError as e:
        error_msg = f"Failed to parse audit message JSON: {e}"
        logger.error(error_msg)
        return ProcessingResult.failed(error_msg)
        
    except Exception as e:
        error_msg = f"Unexpected error processing audit message: {e}"
        logger.exception(error_msg)
        return ProcessingResult.failed(error_msg, retry=True)


if __name__ == "__main__":
    main()