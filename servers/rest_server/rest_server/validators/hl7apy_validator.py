"""Validates a payload using hl7apy's reference-driven ER7 validation (TOLERANT level).

Unlike ``Hl7XsdValidator``, which validates the XML payload against an HL7 v2.xml XSD (where every
composite datatype sub-element must be structurally present, regardless of its HL7 usage code),
this validator converts the payload back to ER7 and validates it against hl7apy's own HL7 v2
reference structures - cardinality, child presence and datatypes - which do respect HL7's ER7
usage-code semantics (O/C fields/components may be entirely absent). ``VALIDATION_LEVEL.TOLERANT``
is used so hl7apy always finishes parsing and reports every structural violation it finds, rather
than failing fast on the first one (see ``hl7_message_processor.validate_hl7_message``).
"""
from __future__ import annotations

from typing import Set

from hl7_message_processor import Hl7MessageValidationError, validate_hl7_message
from hl7_validation import xml_to_er7
from hl7apy.consts import VALIDATION_LEVEL

from rest_server.errors import ValidationError


class Hl7ApyValidator:
    def __init__(self, allowed_structures: Set[str]) -> None:
        self.allowed_structures = allowed_structures

    def validate(self, payload_xml: str, structure_id: str | None) -> None:
        if not structure_id:
            raise ValidationError("Unable to determine HL7 message structure from payload.")

        if self.allowed_structures and structure_id not in self.allowed_structures:
            raise ValidationError(
                f"Unsupported HL7 message structure '{structure_id}'. "
                f"Allowed values: {', '.join(sorted(self.allowed_structures))}"
            )

        try:
            er7_message = xml_to_er7(payload_xml)
        except Exception as exc:
            raise ValidationError("Unable to convert XML payload to ER7 format for validation.") from exc

        try:
            validate_hl7_message(er7_message, validation_level=VALIDATION_LEVEL.TOLERANT)
        except Hl7MessageValidationError as exc:
            raise ValidationError(f"Payload validation failed: {exc}") from exc
