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

from db_sender_trrr.app_config import AppConfig
from db_sender_trrr.db_client import DatabaseClient, FatalDatabaseError, TransientDatabaseError
from db_sender_trrr.identifier_mapper import map_trrr_identifiers
from db_sender_trrr.msh_extractor import extract_msh_for_logging

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
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    metadata = extract_metadata(message)
    meta = get_metadata_log_values(metadata)
    correlation_id_opt = correlation_id_for_logger(meta)

    # Extract MSH ONLY for Information Governance compliant logging
    msh_info = extract_msh_for_logging(message_body)

    logger.info(
        "TRRR message received for identifier update - CorrelationId: %s, MessageControlId: %s, "
        "MessageType: %s, WorkflowID: %s, TargetProcedure: %s",
        meta["correlation_id"],
        msh_info.control_id,
        msh_info.message_type,
        meta["workflow_id"],
        app_config.db_stored_procedure,
    )

    event_logger.log_message_received(
        msh_info.msh_text,
        f"Message received for TRRR identifier update via {app_config.db_stored_procedure}",
        correlation_id=correlation_id_opt,
    )

    # ------------------------------------------------------------------
    # Mapping gate: a message that cannot be mapped (unsupported trigger,
    # missing LIMS authority/identifier, missing NHS identifier) can never
    # succeed on redelivery, so dead-letter immediately instead of retrying.
    # ------------------------------------------------------------------
    try:
        mapping = map_trrr_identifiers(message_body)
    except ValueError as mapping_err:
        event_logger.log_message_failed(
            msh_info.msh_text,
            f"TRRR identifier mapping failed: {mapping_err}",
            correlation_id=correlation_id_opt,
        )
        logger.error(
            "TRRR mapping failed (%s). Dead-lettering. MessageControlId: %s, MessageType: %s, MSH: %s",
            mapping_err,
            msh_info.control_id,
            msh_info.message_type,
            msh_info.msh_text,
        )
        raise DeadLetterMessage(
            reason="MappingFailed",
            description=str(mapping_err),
        ) from mapping_err

    try:
        db_client.execute_identifier_update(mapping)

        _send_metric_best_effort(
            lambda: metric_sender.send_metric(
                "messages_sent",
                1,
                attributes={
                    "database": app_config.db_name,
                    "stored_procedure": app_config.db_stored_procedure,
                },
            ),
            "messages_sent",
        )

        # Post-commit logging is best effort: the stored procedure has already committed,
        # so any logging failure must not cause redelivery of an already-written message.
        try:
            event_logger.log_message_processed(
                msh_info.msh_text,
                f"TRRR identifier update {app_config.db_stored_procedure} executed successfully",
                correlation_id=correlation_id_opt,
            )
        except Exception:
            logger.exception(
                "Failed to log message processed event for %s - continuing delivery success "
                "as database execution has already committed",
                app_config.db_stored_procedure,
            )

        logger.info(
            "TRRR identifier update %s executed successfully. MessageControlId: %s, MSH: %s",
            app_config.db_stored_procedure,
            msh_info.control_id,
            msh_info.msh_text,
        )
        return True

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

    logger.info(
        "Starting db_sender_trrr for subscription %s/%s -> DB %s (%s)",
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
                    ),
                )


if __name__ == "__main__":
    main()
