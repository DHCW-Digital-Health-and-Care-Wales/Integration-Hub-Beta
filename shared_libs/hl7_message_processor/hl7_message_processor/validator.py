"""XSD schema validation and hl7apy-native ER7 validation, both PII-safe.

``str(xmlschema error)`` embeds an ``Instance:`` block containing the full XML document being
validated - for HL7 messages that includes patient-identifiable information (PII). This module only
ever surfaces the schema-level ``reason`` and structural ``path`` of each violation (design report
section 5.4) - never the raw instance.

``validate_hl7_message`` applies the same PII-safety rule to hl7apy's own reference-driven
validation: only its error-level messages (element/child names, cardinality, datatype) are raised,
never its warning-level messages (e.g. table-value checks), which embed the raw field value. See
notes/hl7apy-native-validation-design-report.md for the full design rationale.
"""

from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache
from typing import Any

import xmlschema
from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.exceptions import HL7apyException
from hl7apy.parser import parse_message

from .exceptions import Hl7MessageValidationError, XmlValidationError

logger = logging.getLogger(__name__)


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


def _collect_hl7apy_validation_results(message: Any) -> tuple[list[str], list[str]]:
    """Run hl7apy's own Validator against ``message``, returning ``(errors, warnings)``.

    hl7apy's public API (``Element.validate()``) only ever raises the FIRST violation it finds - the
    ``report_file`` parameter is the only supported way to retrieve the full list without
    reimplementing hl7apy's private validation-tree walk (``hl7apy.validation.Validator.validate``).
    """
    fd, report_path = tempfile.mkstemp(prefix="hl7apy_validate_", suffix=".txt")
    os.close(fd)
    try:
        try:
            message.validate(report_file=report_path)
        except HL7apyException:
            pass  # the full list is in the report file regardless of which error was raised first

        errors = []
        warnings = []
        with open(report_path, encoding="utf-8") as report:
            for raw_line in report:
                stripped_line = raw_line.rstrip("\n")
                if stripped_line.startswith("Error: "):
                    errors.append(stripped_line[len("Error: ") :])
                elif stripped_line.startswith("Warning: "):
                    warnings.append(stripped_line[len("Warning: ") :])
        return errors, warnings
    finally:
        os.remove(report_path)


def validate_hl7_message(er7_message: str, validation_level: int = VALIDATION_LEVEL.TOLERANT) -> None:
    """Validate ``er7_message`` using hl7apy's reference-driven structural/value validation.

    Unlike ``validate_xml``, this checks the ER7 message directly against hl7apy's own HL7 v2
    reference structures (children names/cardinality, datatypes, value length) rather than an XSD.

    STRICT mode enforces most rules at parse time and fails on the FIRST hard violation (hl7apy
    limitation - the message tree is never fully built, so no further errors can be collected for
    malformed input). TOLERANT mode always parses successfully; either way, a follow-up
    ``Element.validate()`` pass is run to also catch cardinality violations (e.g. a missing required
    segment), which aren't detected at parse time under either level.

    hl7apy's warning-level findings (e.g. a value absent from its HL7 table) are logged but never
    included in the raised exception, since they embed the raw field value (PII).

    Raises:
        Hl7MessageValidationError: on any error-level violation, message is every error joined with
            "\\n" (PII-safe - never includes raw field values).
    """
    try:
        message = parse_message(er7_message, validation_level=validation_level, find_groups=True)
    except (HL7apyException, ValueError) as error:
        logger.error("HL7 message failed validation: %s", error)
        raise Hl7MessageValidationError(str(error)) from error

    errors, warnings = _collect_hl7apy_validation_results(message)

    for warning_text in warnings:
        logger.warning("HL7 message validation warning: %s", warning_text)

    if errors:
        for error_text in errors:
            logger.error("HL7 message failed validation: %s", error_text)
        raise Hl7MessageValidationError("\n".join(errors))

    logger.info("HL7 message passed hl7apy validation (validation_level=%s)", validation_level)
