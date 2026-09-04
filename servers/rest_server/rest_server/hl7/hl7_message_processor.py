import logging
from typing import NoReturn

from event_logger_lib.event_logger import EventLogger
from field_utils_lib import get_hl7_field_value
from hl7_validation import (
    XmlValidationError,
    convert_er7_to_xml,
    validate_and_convert_parsed_message_with_flow_schema,
    validate_parsed_message_with_standard,
)
from hl7apy.core import Message
from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message
from message_bus_lib.message_sender_client import MessageSenderClient
from message_bus_lib.message_store_client import MessageStoreClient
from message_bus_lib.metadata_utils import (
    CORRELATION_ID_KEY,
    MESSAGE_RECEIVED_AT_KEY,
    SOURCE_SYSTEM_KEY,
    WORKFLOW_ID_KEY,
    get_metadata_log_values,
)
from metric_sender_lib.metric_sender import MetricSender

from rest_server.hl7.custom_message_properties import FLOW_PROPERTY_BUILDERS, build_common_properties
from rest_server.hl7.errors import Hl7ParseError, Hl7ValidationError
from rest_server.hl7.hl7_ack_builder import HL7AckBuilder
from rest_server.hl7.hl7_validator import HL7Validator, ValidationException
from rest_server.hl7.risp_routing import RispFlowRouter, RoutingTarget

logger = logging.getLogger(__name__)


class Hl7MessageProcessor:
    """Transport-agnostic HL7 processing pipeline.

    Mirrors ``hl7_server``'s ``GenericHandler.reply()`` so the REST receiver
    validates, stores and forwards messages identically to the MLLP server. The
    only difference is that failures raise typed exceptions (carrying a built
    NACK) instead of relying on the MLLP error handler.
    """

    def __init__(
        self,
        sender_client: MessageSenderClient,
        event_logger: EventLogger,
        metric_sender: MetricSender,
        validator: HL7Validator,
        message_store_client: MessageStoreClient,
        ack_builder: HL7AckBuilder,
        workflow_id: str,
        egress_session_id: str,
        flow_name: str | None = None,
        standard_version: str | None = None,
        risp_router: RispFlowRouter | None = None,
        destination_senders: dict[str, MessageSenderClient] | None = None,
        destination_workflow_ids: dict[str, str] | None = None,
    ) -> None:
        self.sender_client = sender_client
        self.event_logger = event_logger
        self.metric_sender = metric_sender
        self.validator = validator
        self.message_store_client = message_store_client
        self.ack_builder = ack_builder
        self.workflow_id = workflow_id
        self.egress_session_id = egress_session_id
        self.flow_name = flow_name
        self.standard_version = standard_version
        self.risp_router = risp_router
        self.destination_senders = destination_senders or {}
        self.destination_workflow_ids = destination_workflow_ids or {}

    def process(self, raw_message: str) -> str:
        """Validate, store and forward an ER7 message, returning the HL7 ACK.

        Raises:
            Hl7ParseError: The message could not be parsed (maps to HTTP 500).
            Hl7ValidationError: The message failed validation (maps to HTTP 422).
            Exception: Any other failure (e.g. Service Bus send) — maps to HTTP 500.
        """
        self.event_logger.log_message_received(raw_message)
        self.metric_sender.send_message_received_metric()

        msg = self._parse(raw_message)

        message_control_id = msg.msh.msh_10.value
        message_type = msg.msh.msh_9.to_er7()
        logger.info("Received message type: %s, Control ID: %s", message_type, message_control_id)

        self._run_common_validation(raw_message, msg, message_type)

        message_sending_app = get_hl7_field_value(msg.msh, "msh_3") or None
        tracking_metadata_properties = build_common_properties(self.workflow_id, message_sending_app)
        correlation_id = tracking_metadata_properties.get(CORRELATION_ID_KEY, "")

        routing_targets: list[RoutingTarget] | None = None
        if self.risp_router is not None:
            # RISP messages may fan out to more than one destination/format (see risp_routing.py);
            # any XML target's payload doubles as the message-store XML copy.
            routing_targets = self._resolve_risp_targets(raw_message, msg, correlation_id)
            xml_payload = next((target.payload for target in routing_targets if target.is_xml), None)
        else:
            xml_payload = self._run_flow_schema_validation(
                raw_message, msg, tracking_metadata_properties, correlation_id
            )

        if xml_payload is None:
            xml_payload = self._generate_store_xml(raw_message, correlation_id)

        self._run_standard_validation(raw_message, msg, correlation_id)

        self._apply_flow_properties(msg, tracking_metadata_properties)

        # Non-blocking: attempt to store first so there is a persisted copy before forwarding.
        self._send_to_message_store(raw_message, tracking_metadata_properties, xml_payload)

        if routing_targets is not None:
            self._send_to_destinations(message_control_id, tracking_metadata_properties, routing_targets)
        else:
            self._send_to_service_bus(raw_message, message_control_id, tracking_metadata_properties)

        ack_message = self.ack_builder.build_success_ack(msg)
        self.event_logger.log_message_processed(raw_message, "ACK generated successfully")
        logger.info("ACK generated successfully")
        return ack_message

    def _parse(self, raw_message: str) -> Message:
        try:
            return parse_message(raw_message, find_groups=False)
        except (HL7apyException, ValueError) as e:
            error_msg = f"HL7 parsing error: {e}"
            logger.error(error_msg)
            self.event_logger.log_validation_result(raw_message, error_msg, is_success=False)
            self.event_logger.log_message_failed(raw_message, error_msg)
            raise Hl7ParseError(str(e)) from e

    def _run_common_validation(self, raw_message: str, msg: Message, message_type: str) -> None:
        try:
            self.validator.validate(msg)
        except ValidationException as e:
            self._raise_validation_failure(raw_message, msg, str(e))

        self.event_logger.log_validation_result(
            raw_message, f"Valid HL7 message - Type: {message_type}", is_success=True
        )

    def _run_flow_schema_validation(
        self,
        raw_message: str,
        msg: Message,
        tracking_metadata_properties: dict[str, str],
        correlation_id: str,
    ) -> str | None:
        # Flow validation also generates XML, used for the message store.
        # 'mpi' has no XSD schema; 'risp' is routed/validated via RispFlowRouter instead (process()).
        if not self.flow_name or self.flow_name in ("mpi", "risp"):
            return None

        try:
            validation_result = validate_and_convert_parsed_message_with_flow_schema(
                msg, raw_message, self.flow_name
            )
            if not validation_result.is_valid:
                raise XmlValidationError(validation_result.error_message or "Unknown XML validation error")

            self.event_logger.log_validation_result(
                raw_message, f"XML validation passed for flow '{self.flow_name}'", is_success=True
            )
            return validation_result.xml_string
        except XmlValidationError as e:
            reason = f"XML validation failed for flow '{self.flow_name}': {e}"
            # Persist a copy (without XML) before failing, mirroring the MLLP server.
            self._send_to_message_store(raw_message, tracking_metadata_properties, xml_payload=None)
            self._raise_validation_failure(raw_message, msg, reason, correlation_id)

    def _generate_store_xml(self, raw_message: str, correlation_id: str) -> str | None:
        # For flows without schema-aware XML (e.g. MPI) or no flow, try to generate basic XML.
        try:
            return convert_er7_to_xml(raw_message)
        except Exception as e:
            error_msg = f"Failed to generate XML payload for message store: {e} (CorrelationId: {correlation_id})"
            logger.error(error_msg)
            self.event_logger.log_validation_result(
                raw_message, error_msg, is_success=False, correlation_id=correlation_id
            )
            return None

    def _run_standard_validation(self, raw_message: str, msg: Message, correlation_id: str) -> None:
        if not self.standard_version:
            return

        try:
            validate_parsed_message_with_standard(msg, self.standard_version)
            self.event_logger.log_validation_result(
                raw_message, f"Standard HL7 v{self.standard_version} validation passed", is_success=True
            )
        except XmlValidationError as e:
            reason = f"Standard validation error: {e}"
            self._raise_validation_failure(raw_message, msg, reason, correlation_id)

    def _apply_flow_properties(self, msg: Message, tracking_metadata_properties: dict[str, str]) -> None:
        flow_property_builder = FLOW_PROPERTY_BUILDERS.get(self.flow_name or "")
        if flow_property_builder:
            try:
                tracking_metadata_properties.update(flow_property_builder(msg))
            except Exception as e:
                logger.warning("Failed to build flow-specific routing properties: %s", e)

    def _raise_validation_failure(
        self,
        raw_message: str,
        msg: Message,
        reason: str,
        correlation_id: str | None = None,
    ) -> NoReturn:
        logger.error("HL7 validation error: %s", reason)
        self.event_logger.log_validation_result(raw_message, reason, is_success=False, correlation_id=correlation_id)
        self.event_logger.log_message_failed(raw_message, reason, correlation_id=correlation_id)
        nack = self.ack_builder.build_validation_nack(msg, reason)
        raise Hl7ValidationError(nack, reason)

    def _resolve_risp_targets(self, raw_message: str, msg: Message, correlation_id: str) -> list[RoutingTarget]:
        assert self.risp_router is not None  # nosec B101 - only called when risp_router is configured
        try:
            return self.risp_router.resolve_targets(msg, raw_message)
        except ValidationException as e:
            self._raise_validation_failure(raw_message, msg, str(e), correlation_id)

    def _send_to_message_store(
        self, raw_message: str, tracking_metadata_properties: dict[str, str], xml_payload: str | None
    ) -> None:
        """Send a copy to the message store. Non-blocking: failures are logged, not raised."""
        try:
            self.message_store_client.send_to_store(
                message_received_at=tracking_metadata_properties.get(MESSAGE_RECEIVED_AT_KEY, ""),
                correlation_id=tracking_metadata_properties.get(CORRELATION_ID_KEY, ""),
                source_system=tracking_metadata_properties.get(SOURCE_SYSTEM_KEY, ""),
                raw_payload=raw_message,
                session_id=self.egress_session_id,
                xml_payload=xml_payload,
            )
        except Exception as e:
            logger.error("Failed to send to message store: %s", e)

    def _send_to_service_bus(
        self, raw_message: str, message_control_id: str, tracking_metadata_properties: dict[str, str]
    ) -> None:
        try:
            self.sender_client.send_text_message(
                raw_message, tracking_metadata_properties, message_id=message_control_id
            )
            logger.info("Message %s sent to Service Bus queue successfully", message_control_id)
            meta = get_metadata_log_values(tracking_metadata_properties)
            logger.info(
                "Message metadata attached - CorrelationId: %s, WorkflowID: %s, "
                "SourceSystem: %s, MessageReceivedAt: %s",
                meta["correlation_id"],
                meta["workflow_id"],
                meta["source_system"],
                meta["message_received_at"],
            )
        except Exception as e:
            logger.error("Failed to send message %s to Service Bus: %s", message_control_id, str(e))
            raise

    def _send_to_destinations(
        self,
        message_control_id: str,
        tracking_metadata_properties: dict[str, str],
        targets: list[RoutingTarget],
    ) -> None:
        """Send a RISP message to each of its resolved destinations, sequentially.

        Each destination gets its own copy of the tracking properties with WORKFLOW_ID overridden
        to that destination's configured workflow id. If a send fails partway through, the
        exception propagates (mirroring ``_send_to_service_bus``) and no ACK is returned; any
        destination(s) already sent successfully are not rolled back.
        """
        for target in targets:
            sender = self.destination_senders.get(target.destination)
            if sender is None:
                raise RuntimeError(f"No sender client configured for destination '{target.destination}'")

            properties = dict(tracking_metadata_properties)
            workflow_id = self.destination_workflow_ids.get(target.destination)
            if workflow_id:
                properties[WORKFLOW_ID_KEY] = workflow_id

            try:
                sender.send_text_message(target.payload, properties, message_id=message_control_id)
                logger.info(
                    "Message %s sent to '%s' destination successfully", message_control_id, target.destination
                )
            except Exception as e:
                logger.error(
                    "Failed to send message %s to '%s' destination: %s", message_control_id, target.destination, e
                )
                raise
