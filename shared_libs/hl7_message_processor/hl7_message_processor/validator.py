"""XSD schema validation, PII-safe.

``str(xmlschema error)`` embeds an ``Instance:`` block containing the full XML document being
validated - for HL7 messages that includes patient-identifiable information (PII). This module only
ever surfaces the schema-level ``reason`` and structural ``path`` of each violation (design report
section 5.4) - never the raw instance.
"""

from __future__ import annotations

from functools import lru_cache

import xmlschema

from .exceptions import XmlValidationError


@lru_cache(maxsize=32)
def _get_compiled_schema(xsd_path: str) -> xmlschema.XMLSchema:
    return xmlschema.XMLSchema(xsd_path)


def _format_schema_validation_error(error: "xmlschema.validators.exceptions.XMLSchemaValidationError") -> str:
    reason = getattr(error, "reason", None)
    path = getattr(error, "path", None)
    parts = []
    if reason:
        parts.append(str(reason))
    if path:
        parts.append(f"(path: {path})")
    return " ".join(parts) if parts else "XML schema validation failed"


def validate_xml(xml_string: str, xsd_path: str) -> None:
    """Validate ``xml_string`` against ``xsd_path``, raising ``XmlValidationError`` on any violation."""
    schema = _get_compiled_schema(xsd_path)
    errors = list(schema.iter_errors(xml_string))
    if errors:
        raise XmlValidationError("\n".join(_format_schema_validation_error(error) for error in errors))
