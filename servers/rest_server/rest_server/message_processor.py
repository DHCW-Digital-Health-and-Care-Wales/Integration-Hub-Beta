"""Orchestrates the generic ingestion pipeline: extract -> validate -> allow-list -> format -> publish.

This mirrors ``SoapMessageProcessor`` in ``hl7_soap_server`` but delegates the transport-specific
envelope unwrap/response building to a pluggable ``ContentAdapter`` and the schema/business
validation to a pluggable ``Validator``, so the same orchestration serves every content profile.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from event_logger_lib.event_logger import EventLogger
from hl7_validation import xml_to_er7
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.metadata_utils import (
    CORRELATION_ID_KEY,
    MESSAGE_RECEIVED_AT_KEY,
    SOURCE_SYSTEM_KEY,
)
from metric_sender_lib.metric_sender import MetricSender

from rest_server.content_adapters.base import ContentAdapter
from rest_server.custom_message_properties import build_common_properties
from rest_server.errors import RequestError, ValidationError
from rest_server.validators.base import Validator

logger = logging.getLogger(__name__)


class RestMessageProcessor:
    def __init__(
        self,
        content_adapter: ContentAdapter,
        validator: Validator,
        sender_client: MessageSenderClient,
        event_logger: EventLogger,
        metric_sender: MetricSender,
        message_store_client: MessageStoreClient,
        workflow_id: str,
        egress_session_id: str,
        allowed_source_identifiers: List[str],
        output_format: str,
    ) -> None:
        self.content_adapter = content_adapter
        self.validator = validator
        self.sender_client = sender_client
        self.event_logger = event_logger
        self.metric_sender = metric_sender
        self.message_store_client = message_store_client
        self.workflow_id = workflow_id
        self.egress_session_id = egress_session_id
        self.allowed_source_identifiers = set(allowed_source_identifiers)
        self.output_format = output_format

    @property
    def content_type(self) -> str:
        return self.content_adapter.content_type

    def process(self, raw_body: str) -> tuple[int, str]:
        self.event_logger.log_message_received(raw_body)
        self.metric_sender.send_message_received_metric()

        try:
            extracted = self.content_adapter.extract(raw_body)

            self.validator.validate(extracted.payload_xml, extracted.structure_id)
            self.event_logger.log_validation_result(
                raw_body,
                f"Schema validation passed for structure '{extracted.structure_id}'",
                is_success=True,
            )

            if self.allowed_source_identifiers and extracted.source_identifier not in self.allowed_source_identifiers:
                raise RequestError(
                    "Client.Authorization",
                    (
                        f"Source identifier '{extracted.source_identifier}' is not authorised. "
                        f"Allowed values: {', '.join(sorted(self.allowed_source_identifiers))}"
                    ),
                    403,
                )

            output_payload = self._format_output(extracted.payload_xml)

            tracking_metadata_properties = build_common_properties(self.workflow_id, extracted.source_identifier)
            correlation_id = tracking_metadata_properties.get(CORRELATION_ID_KEY)
            message_control_id = extracted.message_control_id or ""

            self._send_to_message_store(
                tracking_metadata_properties=tracking_metadata_properties,
                raw_payload=raw_body,
                xml_payload=extracted.payload_xml,
            )

            self.sender_client.send_text_message(
                output_payload,
                tracking_metadata_properties,
                message_id=message_control_id or None,
            )
            self.metric_sender.send_message_sent_metric()

            self.event_logger.log_message_processed(
                raw_body,
                f"Payload validated and forwarded (structure: {extracted.structure_id})",
                correlation_id=correlation_id,
            )

            return 200, self.content_adapter.build_success_response(message_control_id)
        except RequestError as fault:
            logger.warning("Request rejected: %s", fault.message)
            self.event_logger.log_validation_result(raw_body, fault.message, is_success=False)
            self.event_logger.log_message_failed(raw_body, fault.message, "Request rejected")
            return fault.http_status, self.content_adapter.build_error_response(fault.code, fault.message)
        except ValidationError as exc:
            logger.warning("Payload validation failed: %s", exc.message)
            self.event_logger.log_validation_result(raw_body, exc.message, is_success=False)
            self.event_logger.log_message_failed(raw_body, exc.message, "Payload validation failed")
            return 400, self.content_adapter.build_error_response("Client.Validation", exc.message)
        except Exception as exc:
            logger.exception("Unexpected error while processing request: %s", exc)
            error_message = "Unexpected server error while processing request."
            self.event_logger.log_message_failed(raw_body, error_message, "Unhandled server error")
            return 500, self.content_adapter.build_error_response("Server", error_message)

    def _format_output(self, payload_xml: str) -> str:
        if self.output_format == "raw":
            return payload_xml
        try:
            return xml_to_er7(payload_xml)
        except Exception as exc:
            raise RequestError("Client.Validation", "Unable to convert XML payload to ER7 format.", 400) from exc

    def _send_to_message_store(
        self,
        tracking_metadata_properties: Dict[str, str],
        raw_payload: str,
        xml_payload: str,
    ) -> None:
        # Store failures must not block sender acknowledgements.
        try:
            self.message_store_client.send_to_store(
                message_received_at=tracking_metadata_properties.get(MESSAGE_RECEIVED_AT_KEY, ""),
                correlation_id=tracking_metadata_properties.get(CORRELATION_ID_KEY, ""),
                source_system=tracking_metadata_properties.get(SOURCE_SYSTEM_KEY, ""),
                raw_payload=raw_payload,
                session_id=self.egress_session_id,
                xml_payload=xml_payload,
            )
        except Exception as exc:
            logger.error("Failed to send message to message store: %s", exc)
