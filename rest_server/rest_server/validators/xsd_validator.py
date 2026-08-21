"""Validates a payload against an arbitrary, configured XSD file."""
from __future__ import annotations

from hl7_validation import XmlValidationError, validate_xml

from rest_server.errors import ValidationError


class XsdValidator:
    def __init__(self, schema_path: str) -> None:
        self.schema_path = schema_path

    def validate(self, payload_xml: str, structure_id: str | None) -> None:
        try:
            validate_xml(payload_xml, self.schema_path)
        except XmlValidationError as exc:
            raise ValidationError(f"Payload schema validation failed: {exc}") from exc
        except OSError as exc:
            raise ValidationError(f"Configured schema file '{self.schema_path}' could not be read: {exc}") from exc
