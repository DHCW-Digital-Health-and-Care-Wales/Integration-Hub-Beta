from __future__ import annotations

import logging
import os
from typing import Callable

from azure.servicebus import ServiceBusReceivedMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.dead_letter import DeadLetterMessage
from message_bus_lib.metadata_utils import correlation_id_for_logger, extract_metadata, get_metadata_log_values
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender
from processor_manager_lib import ProcessorManager

from db_sender.app_config import AppConfig
from db_sender.db_client import DatabaseClient, FatalDatabaseError, TransientDatabaseError
from db_sender.handlers import BaseDatabaseHandler, create_handler
from db_sender.msh_extractor import extract_msh_for_logging

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)


def _send_metric_best_effort(send_fn: Callable[[], None], metric_name: str) -> None:
    try:
        send_fn()
    except Exception:
        logger.exception("Failed to send metric '%s' - continuing without blocking message processing", metric_name)


def process_message(
    message: ServiceBusReceivedMessage,
    db_client: DatabaseClient,
    app_config: AppConfig,
    event_logger: EventLogger,
    metric_sender: MetricSender,
    handler: BaseDatabaseHandler | None = None,
) -> bool:
    if handler is None:
        handler = create_handler(app_config)

    message_body = b"".join(message.body).decode("utf-8")
    metadata = extract_metadata(message)
    meta = get_metadata_log_values(metadata)
    correlation_id_opt = correlation_id_for_logger(meta)

    # Extract MSH ONLY for Information Governance compliant logging
    msh_info = extract_msh_for_logging(message_body)

    logger.info(
        "Message received for DB execution - CorrelationId: %s, MessageControlId: %s, "
        "WorkflowID: %s, TargetProcedure: %s, ProcedureType: %s",
        meta["correlation_id"],
        msh_info.control_id,
        meta["workflow_id"],
        app_config.db_stored_procedure,
        app_config.db_procedure_type,
    )

    try:
        event_logger.log_message_received(
            msh_info.msh_text,
            f"Message received for execution of {app_config.db_stored_procedure}",
            correlation_id=correlation_id_opt,
        )

        handler.handle_message(
            message_body=message_body,
            metadata=metadata,
            msh_info=msh_info,
            db_client=db_client,
        )

        _send_metric_best_effort(
            lambda: metric_sender.send_metric(
                "messages_sent",
                1,
                attributes={
                    "database": app_config.db_name,
                    "stored_procedure": app_config.db_stored_procedure,
                    "procedure_type": app_config.db_procedure_type,
                },
            ),
            "messages_sent",
        )

        # Post-commit logging is best effort: the stored procedure has already committed,
        # so any logging failure must not cause redelivery of an already-written message.
        try:
            event_logger.log_message_processed(
                msh_info.msh_text,
                f"Stored procedure {app_config.db_stored_procedure} executed successfully",
                correlation_id=correlation_id_opt,
            )
        except Exception:
            logger.exception(
                "Failed to log message processed event for stored procedure %s - "
                "continuing delivery success as database execution has already committed",
                app_config.db_stored_procedure,
            )

        logger.info(
            "Stored procedure %s executed successfully. MessageControlId: %s, MSH: %s",
            app_config.db_stored_procedure,
            msh_info.control_id,
            msh_info.msh_text,
        )
        return True

    except DeadLetterMessage as dlq_err:
        event_logger.log_message_failed(
            msh_info.msh_text,
            f"Message rejected for {app_config.db_stored_procedure}: {dlq_err.reason} - {dlq_err.description}",
            correlation_id=correlation_id_opt,
        )
        logger.error(
            "Dead-lettering message for %s (Reason: %s, Description: %s). MessageControlId: %s",
            app_config.db_stored_procedure,
            dlq_err.reason,
            dlq_err.description,
            msh_info.control_id,
        )
        raise

    except FatalDatabaseError as fatal_err:
        event_logger.log_message_failed(
            msh_info.msh_text,
            f"Non-recoverable database error executing {app_config.db_stored_procedure}: {fatal_err.error_message}",
            correlation_id=correlation_id_opt,
        )
        logger.error(
            "Fatal database error executing %s (SQLState: %s, Code: %s): %s. MessageControlId: %s, MSH: %s",
            app_config.db_stored_procedure,
            fatal_err.sql_state,
            fatal_err.error_code,
            fatal_err.error_message,
            msh_info.control_id,
            msh_info.msh_text,
        )
        error_desc = f"SQLState: {fatal_err.sql_state}, Code: {fatal_err.error_code}: {fatal_err.error_message}"
        raise DeadLetterMessage(
            reason="StoredProcedureExecutionFailed",
            description=error_desc,
        ) from fatal_err

    except TransientDatabaseError as transient_err:
        logger.warning(
            "Transient database error executing %s (SQLState: %s, Code: %s): %s. "
            "Abandoning message for retry. MessageControlId: %s, MSH: %s",
            app_config.db_stored_procedure,
            transient_err.sql_state,
            transient_err.error_code,
            transient_err.error_message,
            msh_info.control_id,
            msh_info.msh_text,
        )
        return False

    except Exception:
        logger.exception(
            "Unexpected error executing stored procedure %s. "
            "Abandoning message for retry. MessageControlId: %s, MSH: %s",
            app_config.db_stored_procedure,
            msh_info.control_id,
            msh_info.msh_text,
        )
        return False


def main() -> None:
    processor_manager = ProcessorManager()
    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)

    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
    metric_sender = MetricSender(
        app_config.workflow_id,
        app_config.microservice_id,
        app_config.health_board,
        app_config.peer_service,
    )
    handler = create_handler(app_config)

    logger.info(
        "Starting db_sender (%s) for subscription %s/%s -> DB %s (%s)",
        app_config.db_procedure_type,
        app_config.ingress_topic_name,
        app_config.ingress_subscription_name,
        app_config.db_name,
        app_config.db_stored_procedure,
    )

    with (
        TCPHealthCheckServer(app_config.health_check_hostname, app_config.health_check_port) as health_check_server,
        DatabaseClient(app_config) as db_client,
    ):
        health_check_server.start()

        with factory.create_subscription_receiver_client(
            app_config.ingress_topic_name,
            app_config.ingress_subscription_name,
            app_config.ingress_session_id,
        ) as subscription_receiver_client:
            logger.info("Subscription receiver client initialized. Processing messages...")

            while processor_manager.is_running:
                subscription_receiver_client.receive_messages(
                    app_config.max_batch_size,
                    lambda msg: process_message(
                        msg,
                        db_client,
                        app_config,
                        event_logger,
                        metric_sender,
                        handler=handler,
                    ),
                )


if __name__ == "__main__":
    main()
