"""FHIR Sender — consumes FHIR message Bundles from Service Bus and delivers them to Promptly.

Outcome mapping per message:
  - delivered                      -> complete
  - permanent rejection / bad body -> dead-letter (400, 404, 409, error OperationOutcome, invalid Bundle)
  - 401 / 403                      -> alert and abandon (no blind retry; redrive once credentials are fixed)
  - transient failure (retries exhausted in the client) -> abandon, so Service Bus redelivers later
"""
from __future__ import annotations

import json
import logging
import os

from azure.servicebus import ServiceBusMessage
from event_logger_lib import EventLogger
from health_check_lib.health_check_server import TCPHealthCheckServer
from message_bus_lib.connection_config import ConnectionConfig
from message_bus_lib.dead_letter import DeadLetterMessage
from message_bus_lib.metadata_utils import (
    correlation_id_for_logger,
    extract_metadata,
    get_metadata_log_values,
)
from message_bus_lib.servicebus_client_factory import ServiceBusClientFactory
from metric_sender_lib.metric_sender import MetricSender
from otel_lib import configure_otel
from processor_manager_lib import ProcessorManager

from fhir_sender.app_config import AUTH_MODE_OAUTH2, AppConfig
from fhir_sender.auth import ApiKeyAuth, AuthProvider, OAuth2ClientCredentialsAuth
from fhir_sender.errors import (
    AuthorizationDeliveryError,
    PermanentDeliveryError,
    TransientDeliveryError,
)
from fhir_sender.fhir_sender_client import FhirSenderClient

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "ERROR").upper())
azure_log_level_str = os.environ.get("AZURE_LOG_LEVEL", "WARN").upper()
azure_log_level = getattr(logging, azure_log_level_str, logging.WARN)
logging.getLogger("azure").setLevel(azure_log_level)
logger = logging.getLogger(__name__)

MAX_DEAD_LETTER_DESCRIPTION = 1000


def _build_auth(app_config: AppConfig) -> AuthProvider:
    if app_config.auth_mode == AUTH_MODE_OAUTH2:
        if not (
            app_config.oauth_token_url
            and app_config.oauth_client_id
            and app_config.oauth_client_secret
            and app_config.oauth_scope
        ):
            raise RuntimeError("OAuth2 configuration is incomplete")
        return OAuth2ClientCredentialsAuth(
            app_config.oauth_token_url,
            app_config.oauth_client_id,
            app_config.oauth_client_secret,
            app_config.oauth_scope,
            app_config.request_timeout_seconds,
        )
    if not app_config.api_key:
        raise RuntimeError("API key configuration is missing")
    return ApiKeyAuth(app_config.api_key)


def _build_client(app_config: AppConfig) -> FhirSenderClient:
    return FhirSenderClient(
        app_config.fhir_endpoint_url,
        _build_auth(app_config),
        timeout_seconds=app_config.request_timeout_seconds,
        max_attempts=app_config.max_attempts,
        backoff_seconds=app_config.backoff_seconds,
        max_retry_after_seconds=app_config.max_retry_after_seconds,
        poll_interval_seconds=app_config.poll_interval_seconds,
        poll_timeout_seconds=app_config.poll_timeout_seconds,
        allow_insecure_http=app_config.allow_insecure_http,
    )


def main() -> None:
    configure_otel("fhir-sender")
    processor_manager = ProcessorManager()

    app_config = AppConfig.read_env_config()
    client_config = ConnectionConfig(app_config.connection_string, app_config.service_bus_namespace)
    factory = ServiceBusClientFactory(client_config)
    event_logger = EventLogger(app_config.workflow_id, app_config.microservice_id)
    metric_sender = MetricSender(
        app_config.workflow_id, app_config.microservice_id, app_config.health_board, app_config.peer_service
    )

    logger.info(
        "FHIR Sender starting — endpoint: %s, queue: %s, auth: %s",
        app_config.fhir_endpoint_url,
        app_config.ingress_queue_name,
        app_config.auth_mode,
    )

    # Bind the health probe first so the container reports healthy even if Promptly is briefly unreachable.
    with TCPHealthCheckServer(
        app_config.health_check_hostname, app_config.health_check_port
    ) as health_check_server:
        health_check_server.start()

        with (
            factory.create_message_receiver_client(
                app_config.ingress_queue_name, app_config.ingress_session_id
            ) as receiver_client,
            _build_client(app_config) as fhir_client,
        ):
            logger.info("FHIR Sender processor started.")

            def message_processor(message: ServiceBusMessage) -> bool:
                return _process_message(message, fhir_client, event_logger, metric_sender)

            wrapped_processor = processor_manager.wrap_handler(
                message_processor, "fhir-sender", app_config.ingress_queue_name
            )
            while processor_manager.is_running:
                receiver_client.receive_messages(app_config.max_batch_size, wrapped_processor)


def _validate_bundle(message_body: str) -> None:
    """Reject anything that is not a FHIR message Bundle before spending a request on it."""
    try:
        bundle = json.loads(message_body)
    except ValueError as exc:
        raise ValueError(f"Message body is not valid JSON: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle" or bundle.get("type") != "message":
        raise ValueError("Message body is not a FHIR Bundle of type 'message'")


def _process_message(
    message: ServiceBusMessage,
    fhir_client: FhirSenderClient,
    event_logger: EventLogger,
    metric_sender: MetricSender,
) -> bool:
    message_body = b"".join(message.body).decode("utf-8")
    metadata = extract_metadata(message)
    meta = get_metadata_log_values(metadata)
    correlation_id = correlation_id_for_logger(meta)

    logger.info(
        "Message received for FHIR sending — CorrelationId: %s, WorkflowID: %s, SourceSystem: %s",
        meta["correlation_id"],
        meta["workflow_id"],
        meta["source_system"],
    )
    event_logger.log_message_received(message_body, "Message received for FHIR sending", correlation_id=correlation_id)

    try:
        _validate_bundle(message_body)
    except ValueError as exc:
        event_logger.log_message_failed(
            message_body, str(exc), "Invalid FHIR Bundle — dead-lettered", correlation_id=correlation_id
        )
        raise DeadLetterMessage("InvalidFhirBundle", str(exc)) from exc

    try:
        fhir_client.send_bundle(message_body)
    except PermanentDeliveryError as exc:
        logger.error("Promptly rejected message — CorrelationId: %s: %s", meta["correlation_id"], exc)
        event_logger.log_message_failed(
            message_body, str(exc), "Promptly rejected the message — dead-lettered", correlation_id=correlation_id
        )
        raise DeadLetterMessage("PromptlyRejected", str(exc)[:MAX_DEAD_LETTER_DESCRIPTION]) from exc
    except AuthorizationDeliveryError as exc:
        logger.error("ALERT: Promptly credential/authorisation failure — %s", exc)
        event_logger.log_message_failed(
            message_body, str(exc), "ALERT: Promptly credential/authorisation failure", correlation_id=correlation_id
        )
        return False
    except TransientDeliveryError as exc:
        logger.error("Delivery to Promptly failed — CorrelationId: %s: %s", meta["correlation_id"], exc)
        event_logger.log_message_failed(
            message_body, str(exc), "Delivery to Promptly failed", correlation_id=correlation_id
        )
        return False

    metric_sender.send_message_sent_metric()
    event_logger.log_message_processed(
        message_body, "Message delivered to Promptly", correlation_id=correlation_id
    )
    logger.info("Message delivered to Promptly — CorrelationId: %s", meta["correlation_id"])
    return True


if __name__ == "__main__":
    main()
