"""Normalise inbound ``messageContent`` into an ER7 (pipe-and-hat) HL7 string.

The REST endpoint accepts either a raw ER7 message or an HL7 v2 XML document
(namespace ``urn:hl7-org:v2xml``). This adapter detects which form was supplied,
converts XML to ER7 via the shared ``hl7_validation`` library, and normalises
segment terminators to ``\\r`` (the HL7 segment separator that the downstream
processing pipeline relies on).
"""

from hl7_validation import xml_to_er7


def _normalise_line_endings(content: str) -> str:
    # Windows (\r\n) first, then any remaining Unix (\n) newlines → HL7 segment terminator.
    return content.replace("\r\n", "\r").replace("\n", "\r")


def to_er7(message_content: str) -> str:
    """Convert raw ``messageContent`` to a normalised ER7 HL7 message.

    Args:
        message_content: Raw request content — either ER7 or HL7 v2 XML.

    Returns:
        The message as an ER7 string with ``\\r`` segment terminators.
    """
    if message_content.lstrip().startswith("<"):
        # XML detected — convert to ER7 (xml_to_er7 emits \r-terminated segments).
        return xml_to_er7(message_content)

    return _normalise_line_endings(message_content)
