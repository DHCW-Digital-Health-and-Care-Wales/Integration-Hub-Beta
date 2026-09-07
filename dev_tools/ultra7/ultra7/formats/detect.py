"""Sniff whether a message is HL7 v2.x ER7, XML, or JSON."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from ultra7.models import MessageFormat


def detect_format(content: str) -> MessageFormat:
    """Best-effort detection of the message format from its raw text.

    Order of preference: JSON, then XML, then fall back to HL7 (the default
    for anything that isn't valid JSON/XML, since ER7 has no strict "starts
    with" marker once MSH field separators vary).
    """
    stripped = content.strip()
    if not stripped:
        return "hl7"

    if stripped[0] in "{[":
        try:
            json.loads(stripped)
        except (ValueError, TypeError):
            pass
        else:
            return "json"

    if stripped.startswith("<"):
        try:
            ET.fromstring(stripped)
        except ET.ParseError:
            pass
        else:
            return "xml"

    return "hl7"
