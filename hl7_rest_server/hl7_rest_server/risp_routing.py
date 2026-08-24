"""Multi-destination routing for RISP-sourced messages (plan §3a).

Unlike every other flow (single destination, one payload format), RISP messages can fan out to
more than one destination and format from a single inbound request:

- ``A28``/``A31``/``A40`` -> ``risp-hl7-transformer`` -> MPI, as ER7.
- ``A40`` -> additionally WRRS, as HL7 v2 XML (no transformer involved).
- ``ORU_R01``/``OMG_O19`` -> WRRS only, as HL7 v2 XML, after custom XSD schema validation.
"""

from dataclasses import dataclass

from hl7_validation import convert_er7_to_xml, validate_and_convert_parsed_message_with_structure_schema
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

# Maps a message structure (MSH.9.3) to its XSD file stem, both looked up under the structure's
# own directory in shared_libs/hl7_validation/hl7_validation/resources/ (e.g. "ORU_R01/ORU_R01_2_5_1.xsd")
# — keyed by structure + HL7 version rather than by flow, so multiple flows sharing the same
# message structure/version reuse a single schema instead of duplicating it per flow.
ORU_OMG_SCHEMA_FILES: dict[str, str] = {
    "2_5_1": "ORU_R01_2_5_1",
    "2_5_1": "OMG_O19_2_5_1",
}


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
            targets.append(RoutingTarget(WRRS_DESTINATION, convert_er7_to_xml(raw_message), is_xml=True))
        elif structure in ORU_OMG_STRUCTURES:
            xml_payload = self._validate_and_convert_for_wrrs(msg, raw_message, structure)
            targets.append(RoutingTarget(WRRS_DESTINATION, xml_payload, is_xml=True))

        return targets

    @staticmethod
    def _validate_and_convert_for_wrrs(msg: Message, raw_message: str, structure: str) -> str:
        schema_file_name = ORU_OMG_SCHEMA_FILES[structure]
        result = validate_and_convert_parsed_message_with_structure_schema(
            msg, raw_message, structure, schema_file_name
        )
        if not result.is_valid:
            raise ValidationException(
                f"XSD schema validation failed for '{structure}': "
                f"{result.error_message or 'Unknown XML validation error'}"
            )
        return result.xml_string
