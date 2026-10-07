"""Validates a payload using hl7apy's reference-driven ER7 validation (TOLERANT level).

Unlike ``Hl7XsdValidator``, which validates the XML payload against an HL7 v2.xml XSD (where every
composite datatype sub-element must be structurally present, regardless of its HL7 usage code),
this validator converts the payload back to ER7 and validates it against hl7apy's own HL7 v2
reference structures - cardinality, child presence and datatypes - which do respect HL7's ER7
usage-code semantics (O/C fields/components may be entirely absent). ``VALIDATION_LEVEL.TOLERANT``
is used so hl7apy always finishes parsing and reports every structural violation it finds, rather
than failing fast on the first one (see ``hl7_message_processor.validate_hl7_message``).

``structure_id`` here is only the content adapter's declared value (e.g. the SOAP Body's XML root
element name). ``xml_to_er7`` converts whatever HL7 segments are nested under that root regardless
of the root's own tag, so a payload could declare an allowed root while its MSH.9 names a different,
disallowed structure. The allow-list is therefore enforced against the structure hl7apy itself
derives from the converted message's MSH.9 - not the caller-declared value - after confirming the
two agree (see notes/hl7apy-native-validation-design-report.md).
"""
from __future__ import annotations

from typing import Set

from hl7_message_processor import Hl7MessageValidationError, validate_hl7_message
from hl7_message_processor.message_fields import get_structure_id, parse_er7_message
from hl7_validation import xml_to_er7
from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.exceptions import HL7apyException

from rest_server.errors import ValidationError


class Hl7ApyValidator:
    def __init__(self, allowed_structures: Set[str]) -> None:
        self.allowed_structures = allowed_structures

    def validate(self, payload_xml: str, structure_id: str | None) -> None:
        if not structure_id:
            raise ValidationError("Unable to determine HL7 message structure from payload.")

        try:
            er7_message = xml_to_er7(payload_xml)
        except Exception as exc:
            raise ValidationError("Unable to convert XML payload to ER7 format for validation.") from exc

        try:
            parsed_message = parse_er7_message(er7_message)
        except (HL7apyException, ValueError) as exc:
            raise ValidationError("Unable to parse converted ER7 payload for structure verification.") from exc

        actual_structure_id = get_structure_id(parsed_message)
        if actual_structure_id != structure_id:
            raise ValidationError(
                f"Declared message structure '{structure_id}' does not match the structure "
                f"'{actual_structure_id or 'unknown'}' specified in MSH.9 of the payload."
            )

        if self.allowed_structures and actual_structure_id not in self.allowed_structures:
            raise ValidationError(
                f"Unsupported HL7 message structure '{actual_structure_id}'. "
                f"Allowed values: {', '.join(sorted(self.allowed_structures))}"
            )

        try:
            validate_hl7_message(er7_message, validation_level=VALIDATION_LEVEL.TOLERANT)
        except Hl7MessageValidationError as exc:
            raise ValidationError(f"Payload validation failed: {exc}") from exc
