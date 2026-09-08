"""Multi-destination routing for RISP-sourced messages (plan §3a).

Unlike every other flow (single destination, one payload format), RISP messages can fan out to
more than one destination and format from a single inbound request:

- ``A28``/``A31``/``A40`` -> ``risp-hl7-transformer`` -> MPI, as ER7.
- ``A40`` -> additionally WRRS, as HL7 v2 XML (no transformer involved).
- ``ORU_R01``/``OMG_O19`` -> WRRS only, as HL7 v2 XML, after custom XSD schema validation.

Both the A40->WRRS conversion and the ORU_R01/OMG_O19 validation use ``hl7_message_processor``
(``shared_libs/hl7_message_processor``) rather than ``hl7_validation``: it resolves the structure
XSD itself from the message's own MSH-12.1/MSH-9 (no per-structure schema-file mapping needed here)
and fixes the arbitrary-depth group-nesting defects documented in
``notes/hl7-message-processor-design-report.md``.
"""

from dataclasses import dataclass

from hl7_message_processor import MessageNotProcessableError, XmlValidationError, process_er7, validate_xml
from hl7apy.core import Message

from hl7_rest_server.custom_validation.risp_validation import (
    ADT_TRIGGERS_TO_MPI,
    ORU_OMG_STRUCTURES,
    WRRS_DIRECT_ADT_TRIGGERS,
    resolve_structure,
    resolve_trigger,
    validate_risp_message,
)
from hl7_rest_server.exceptions.validation_exception import ValidationException

MPI_TRANSFORMER_DESTINATION = "mpi_transformer"
WRRS_DESTINATION = "wrrs"


@dataclass(frozen=True)
class RoutingTarget:
    """A resolved send target: destination name, payload, and whether it is HL7 v2 XML."""

    destination: str
    payload: str
    is_xml: bool


class RispFlowRouter:
    """Validates RISP sender/message-type rules and resolves send destination(s)."""

    def resolve_targets(self, msg: Message, raw_message: str) -> list[RoutingTarget]:
        """Validate the message and resolve its send target(s).

        Raises:
            ValidationException: the message fails RISP's sender/version/message-type rules
                (see ``validate_risp_message``), or — for ``ORU_R01``/``OMG_O19`` — fails custom
                XSD schema validation. In either case no destination should be sent to.
        """
        validate_risp_message(msg)

        trigger = resolve_trigger(msg)
        structure = resolve_structure(msg)

        targets: list[RoutingTarget] = []

        if trigger in ADT_TRIGGERS_TO_MPI:
            targets.append(RoutingTarget(MPI_TRANSFORMER_DESTINATION, raw_message, is_xml=False))

        if trigger in WRRS_DIRECT_ADT_TRIGGERS:
            xml_payload = self._convert_for_wrrs(raw_message, trigger)
            targets.append(RoutingTarget(WRRS_DESTINATION, xml_payload, is_xml=True))
        elif structure in ORU_OMG_STRUCTURES:
            xml_payload = self._validate_and_convert_for_wrrs(raw_message, structure)
            targets.append(RoutingTarget(WRRS_DESTINATION, xml_payload, is_xml=True))

        return targets

    @staticmethod
    def _convert_for_wrrs(raw_message: str, trigger: str) -> str:
        """Convert a pipe-and-hat ``trigger`` message (e.g. ``A40``) to HL7 v2 XML for WRRS.

        Uses ``hl7_message_processor.process_er7``, which resolves the structure XSD from the
        message's own MSH-12.1/MSH-9 before converting — this correctly nests the message's group(s)
        (e.g. ``ADT_A39.PATIENT``), unlike a schema-less conversion.
        """
        try:
            return process_er7(raw_message).xml
        except MessageNotProcessableError as error:
            raise ValidationException(
                f"Failed to convert '{trigger}' message to HL7 v2 XML for WRRS: {error}"
            ) from error

    @staticmethod
    def _validate_and_convert_for_wrrs(raw_message: str, structure: str) -> str:
        """Validate a ``structure`` message (``ORU_R01``/``OMG_O19``) against its custom XSD and
        convert it to HL7 v2 XML for WRRS, using ``hl7_message_processor``.
        """
        try:
            result = process_er7(raw_message)
            validate_xml(result.xml, str(result.xsd_path))
        except (MessageNotProcessableError, XmlValidationError) as error:
            raise ValidationException(f"XSD schema validation failed for '{structure}': {error}") from error
        return result.xml
