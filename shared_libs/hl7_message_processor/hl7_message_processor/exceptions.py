"""Exceptions raised by hl7_message_processor."""


class SchemaNotFoundError(Exception):
    """Raised when no schema (standard or custom) can be resolved for a (version, structure) pair.

    Confirmed fallback behaviour (see notes/hl7-message-processor-design-report.md, section 7.3):
    there is no flat/best-effort conversion mode - an unresolved schema is always reported as an
    error, never silently guessed.
    """


class MessageNotProcessableError(Exception):
    """Raised when a message cannot be safely converted/validated.

    Covers: the HL7 version/structure could not be determined from the message, no schema could be
    resolved for the determined (version, structure) (see SchemaNotFoundError, which this wraps), or
    the message's segments do not fit the resolved schema's grammar (see matcher.py) - in every case
    the caller gets a clear, loud failure rather than partially-converted or structurally-invalid XML.
    """


class XmlValidationError(Exception):
    """Raised when generated XML fails XSD schema validation.

    The message is built from only the schema-level ``reason``/``path`` of each xmlschema violation -
    never the raw instance XML, which for HL7 messages would embed patient-identifiable information.
    """
