"""HL7 payload redaction utilities.

Removes patient-identifiable information (PII) from HL7 v2 message payloads before
they are emitted to logs or Azure Monitor. The full raw payload is still persisted
to the message store (Azure SQL) for replay; only the logging path is redacted.

Redaction strategy:
  - The MSH header retains a fixed allow-list of routing/metadata fields (encoding
    characters, sending/receiving application and facility, message date/time,
    message type, control ID, processing ID and version). All other MSH fields are
    masked.
  - Every other segment keeps its segment identifier and field positions, but all
    field values are masked. Empty fields are left empty so the field structure
    remains visible for debugging without leaking data.
  - Anything that is not a recognisable HL7 v2 ER7 message (no MSH header) is fully
    masked, since its content is unknown and may contain PII.

Future format support (JSON / XML):
  This function only handles HL7 v2 ER7 (pipe-delimited) format. If future services
  log raw JSON or XML payloads *before* conversion to ER7, extend this module with
  format detection and dedicated handlers:

      def redact_message(content: str) -> str:
          stripped = content.lstrip()
          if stripped.startswith("MSH"):
              return redact_hl7_message(content)   # ER7 — handled today
          if stripped.startswith("<"):
              return _redact_xml(content)           # HL7 v2 XML / CDA — TODO
          if stripped.startswith("{"):
              return _redact_json(content)          # FHIR JSON — TODO
          return REDACTION_MASK

  If messages are always normalised to ER7 before reaching EventLogger (the current
  architecture), no change is needed and this function covers all formats implicitly.
"""

from __future__ import annotations

REDACTION_MASK = "***"

# MSH field numbers (HL7 1-based) that are safe routing/metadata and are retained.
# MSH.1 (field separator) is structural and reconstructed on join; MSH.2 (encoding
# characters) is always kept as it is required to parse the message.
_SAFE_MSH_FIELDS = frozenset({2, 3, 4, 5, 6, 7, 9, 10, 11, 12})


def _mask_field(value: str) -> str:
    """Mask a populated field value, preserving empty fields to keep positions visible."""
    return REDACTION_MASK if value else value


def _redact_msh_segment(segment: str, field_separator: str) -> str:
    # fields[0] == "MSH"; fields[1] == MSH.2 (encoding chars); fields[i] == MSH.(i + 1)
    fields = segment.split(field_separator)
    redacted = [fields[0]]
    for index in range(1, len(fields)):
        field_number = index + 1
        if field_number in _SAFE_MSH_FIELDS:
            redacted.append(fields[index])
        else:
            redacted.append(_mask_field(fields[index]))
    return field_separator.join(redacted)


def _redact_generic_segment(segment: str, field_separator: str) -> str:
    fields = segment.split(field_separator)
    redacted = [fields[0]] + [_mask_field(field) for field in fields[1:]]
    return field_separator.join(redacted)


def redact_hl7_message(message_content: str) -> str:
    """Return a redacted copy of an HL7 payload safe for logging.

    Args:
        message_content: The raw message content (HL7 ER7 string) to redact.

    Returns:
        The redacted message, or the fully masked marker for non-HL7 content.
        Empty or whitespace-only input is returned unchanged.
    """
    if not message_content or not message_content.strip():
        return message_content

    segments = [seg for seg in message_content.replace("\n", "\r").split("\r") if seg]
    if not segments or not segments[0].startswith("MSH") or len(segments[0]) < 4:
        # Not a parseable HL7 message — mask entirely rather than risk leaking PII.
        return REDACTION_MASK

    field_separator = segments[0][3]
    redacted_segments = [
        _redact_msh_segment(segment, field_separator)
        if segment.startswith("MSH")
        else _redact_generic_segment(segment, field_separator)
        for segment in segments
    ]
    return "\r".join(redacted_segments)
