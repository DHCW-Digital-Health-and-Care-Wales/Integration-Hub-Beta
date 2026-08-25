"""Validates a payload against a per-flow HL7 v2.xml structure schema (same rule-set as hl7_soap_server)."""
from __future__ import annotations

from typing import Set

from hl7_validation import XmlValidationError, validate_xml
from hl7_validation.schemas import get_schema_xsd_path_for

from rest_server.errors import RequestError, ValidationError


class Hl7XsdValidator:
    def __init__(self, schema_group: str, allowed_structures: Set[str]) -> None:
        self.schema_group = schema_group
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
            xsd_path = get_schema_xsd_path_for(self.schema_group, structure_id)
        except ValueError as exc:
            # A deployment misconfiguration (structure allowed but not mapped in the schema
            # group), not a payload failure - reported distinctly from ValidationError below.
            raise RequestError(
                "Server.Configuration",
                f"Schema mapping is not configured for group '{self.schema_group}' and structure '{structure_id}'.",
                500,
            ) from exc

        try:
            validate_xml(payload_xml, xsd_path)
        except XmlValidationError as exc:
            raise ValidationError(f"Payload schema validation failed: {exc}") from exc
