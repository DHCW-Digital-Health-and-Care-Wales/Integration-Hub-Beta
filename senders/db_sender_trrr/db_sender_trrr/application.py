from __future__ import annotations

import logging
import os
from dataclasses import dataclass
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
from db_sender_trrr.request_payload import parse_trrr_request

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)

# Application properties set by lims_trrr_mapper; used for logging so the payload (NHS number) is never logged.
MESSAGE_CONTROL_ID_KEY = "MessageControlId"
MESSAGE_TYPE_KEY = "MessageType"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RequestLogInfo:
    """Non-identifiable details of a TRRR request, safe for Information Governance compliant logging."""

    control_id: str
    message_type: str

    @property
    def summary(self) -> str:
        return f"MessageControlId={self.control_id}, MessageType={self.message_type}"


def _request_log_info(metadata: dict[str, str] | None) -> RequestLogInfo:
    metadata = metadata or {}
    return RequestLogInfo(
        control_id=metadata.get(MESSAGE_CONTROL_ID_KEY) or UNKNOWN,
        message_type=metadata.get(MESSAGE_TYPE_KEY) or UNKNOWN,
    )


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
    request_info = _request_log_info(metadata)

    logger.info(
        "TRRR request received - CorrelationId: %s, MessageControlId: %s, "
        "MessageType: %s, WorkflowID: %s, TargetProcedure: %s",
        meta["correlation_id"],
        request_info.control_id,
        request_info.message_type,
        meta["workflow_id"],
        app_config.db_stored_procedure,
    )

    event_logger.log_message_received(
        request_info.summary,
        f"TRRR request received for {app_config.db_stored_procedure}",
        correlation_id=correlation_id_opt,
    )

    # ------------------------------------------------------------------
    # lims_trrr_mapper has already mapped the HL7 message; the body holds the stored
    # procedure parameters. One sender handles both NHS-ID updates and merges, and the
    # request type is identified from the body. A payload that is not a valid request
    # can never succeed on redelivery, so dead-letter it immediately.
    # ------------------------------------------------------------------
    try:
        request_type, mapping = parse_trrr_request(message_body)
    except ValueError as payload_err:
        event_logger.log_message_failed(
            request_info.summary,
            f"Invalid TRRR request: {payload_err}",
            correlation_id=correlation_id_opt,
        )
        logger.error(
            "Invalid TRRR request (%s). Dead-lettering. MessageControlId: %s, MessageType: %s",
            payload_err,
            request_info.control_id,
            request_info.message_type,
        )
        raise DeadLetterMessage(
            reason="InvalidPayload",
            description=str(payload_err),
        ) from payload_err

    procedure_name = app_config.db_stored_procedure

    try:
        db_client.execute_identifier_update(mapping)

        _send_metric_best_effort(
            lambda: metric_sender.send_metric(
                "messages_sent",
                1,
                attributes={
                    "database": app_config.db_name,
                    "stored_procedure": procedure_name,
                    "request_type": request_type,
                },
            ),
            "messages_sent",
        )

        # Post-commit logging is best effort: the stored procedure has already committed,
        # so any logging failure must not cause redelivery of an already-written message.
        try:
            event_logger.log_message_processed(
                request_info.summary,
                f"TRRR {request_type} {procedure_name} executed successfully",
                correlation_id=correlation_id_opt,
            )
        except Exception:
            logger.exception(
                "Failed to log message processed event for %s - continuing delivery success "
                "as database execution has already committed",
                procedure_name,
            )

        logger.info(
            "TRRR %s %s executed successfully. MessageControlId: %s, MessageType: %s",
            request_type,
            procedure_name,
            request_info.control_id,
            request_info.message_type,
        )
        return True

    except FatalDatabaseError as fatal_err:
        event_logger.log_message_failed(
            request_info.summary,
            f"Non-recoverable database error executing {procedure_name}: {fatal_err.error_message}",
            correlation_id=correlation_id_opt,
        )
        logger.error(
            "Fatal database error executing %s (SQLState: %s, Code: %s): %s. MessageControlId: %s, MessageType: %s",
            procedure_name,
            fatal_err.sql_state,
            fatal_err.error_code,
            fatal_err.error_message,
            request_info.control_id,
            request_info.message_type,
        )
        error_desc = f"SQLState: {fatal_err.sql_state}, Code: {fatal_err.error_code}: {fatal_err.error_message}"
        raise DeadLetterMessage(
            reason="StoredProcedureExecutionFailed",
            description=error_desc,
        ) from fatal_err

    except TransientDatabaseError as transient_err:
        logger.warning(
            "Transient database error executing %s (SQLState: %s, Code: %s): %s. "
            "Abandoning message for retry. MessageControlId: %s, MessageType: %s",
            procedure_name,
            transient_err.sql_state,
            transient_err.error_code,
            transient_err.error_message,
            request_info.control_id,
            request_info.message_type,
        )
        return False

    except Exception:
        logger.exception(
            "Unexpected error executing stored procedure %s. "
            "Abandoning message for retry. MessageControlId: %s, MessageType: %s",
            procedure_name,
            request_info.control_id,
            request_info.message_type,
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
        "Starting db_sender_trrr for subscription %s/%s -> DB %s (%s, NHS_ID_UPDATE and MERGE requests)",
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
