"""Parsing of inbound PROMS/WPAS XML into a flat field mapping.

The PROMS payload is a bespoke XML schema (NOT HL7v2-XML), so none of the HL7
tooling used by the other transformers - `hl7_validation.xml_to_er7`, `hl7apy`,
`field_utils_lib` - applies here. Fields are simple leaf elements such as
`<nhsNumber>1234567890</nhsNumber>`.

Two field-name dialects appear across the specification workbook:

* the PROMS clinical event messages use camelCase (`nhsNumber`, `patientSurname`)
* the WPAS MPA/MPR demographics messages use upper snake case (`NHS_NUMBER`,
  `SURNAME`)

Rather than maintaining two parsers, leaf elements are indexed under a
normalised key (lower-cased, separators stripped) so a single lookup serves
both dialects. Original tag names are preserved too, so exact-match lookups
still work if a payload ever uses a name that normalises ambiguously.
"""

from __future__ import annotations

import logging
import re
from typing import Iterator, Optional

# ElementTree is imported for its types only; all parsing goes through defusedxml.
from xml.etree.ElementTree import Element, ParseError  # nosec B405

from defusedxml.ElementTree import fromstring

logger = logging.getLogger(__name__)

_NAMESPACE_PATTERN = re.compile(r"^\{[^}]*\}")
_NORMALISE_PATTERN = re.compile(r"[^a-z0-9]")


def _strip_namespace(tag: str) -> str:
    """Remove any `{namespace}` prefix from an ElementTree tag name."""
    return _NAMESPACE_PATTERN.sub("", tag)


def normalise_key(field_name: str) -> str:
    """Normalise a field name so dialect differences collapse to one key.

    `nhsNumber`, `NHS_NUMBER` and `nhs-number` all normalise to `nhsnumber`.
    """
    return _NORMALISE_PATTERN.sub("", field_name.lower())


class PromsMessage:
    """Read-only, dialect-tolerant view over a parsed PROMS/WPAS XML payload."""

    def __init__(self, fields: dict[str, str], root_tag: str = "") -> None:
        self._fields = fields
        self.root_tag = root_tag

    def get(self, *field_names: str, default: str = "") -> str:
        """Return the first non-empty value among the given field name aliases.

        Accepting aliases lets a single mapper serve both payload dialects, e.g.
        `message.get("nhsNumber", "NHS_NUMBER")`.
        """
        for field_name in field_names:
            value = self._fields.get(normalise_key(field_name), "")
            if value:
                return value
        return default

    def has(self, *field_names: str) -> bool:
        return bool(self.get(*field_names))

    def as_dict(self) -> dict[str, str]:
        """Return a copy of the normalised field mapping (mainly for debugging/tests)."""
        return dict(self._fields)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic helper only
        return f"PromsMessage(root_tag={self.root_tag!r}, fields={len(self._fields)})"


def _iter_leaf_elements(element: Element) -> Iterator[Element]:
    """Yield every leaf (childless) element in document order."""
    children = list(element)
    if not children:
        yield element
        return
    for child in children:
        yield from _iter_leaf_elements(child)


def parse_proms_xml(xml_payload: str) -> PromsMessage:
    """Parse a PROMS/WPAS XML payload into a PromsMessage.

    Raises ValueError on malformed XML so `process_message` records it as a
    transformation failure rather than an unexpected error.
    """
    if not xml_payload or not xml_payload.strip():
        raise ValueError("PROMS payload is empty")

    try:
        root = fromstring(xml_payload)
    except ParseError as parse_error:
        raise ValueError(f"PROMS payload is not well-formed XML: {parse_error}") from parse_error

    fields: dict[str, str] = {}
    for leaf in _iter_leaf_elements(root):
        text = (leaf.text or "").strip()
        if not text:
            continue
        key = normalise_key(_strip_namespace(leaf.tag))
        # First occurrence wins - repeated leaf names are not used by the
        # specification, and silently overwriting would hide payload problems.
        if key in fields:
            logger.debug("Duplicate PROMS field %r ignored (keeping first value)", leaf.tag)
            continue
        fields[key] = text

        # Attributes occasionally carry values in XML dialects; index them under
        # `<tag>_<attribute>` so they remain reachable without special-casing.
        for attribute_name, attribute_value in leaf.attrib.items():
            attribute_key = normalise_key(f"{_strip_namespace(leaf.tag)}_{attribute_name}")
            fields.setdefault(attribute_key, attribute_value.strip())

    return PromsMessage(fields, root_tag=_strip_namespace(root.tag))


def get_message_type(message: PromsMessage) -> Optional[str]:
    """Extract the WPAS routing event code from a parsed message.

    Actual WPAS payloads always carry <eventCode> (e.g. REFERRAL, SURGERY,
    PREOP, INPATIENT, CANCELLED, PREREAD). The MESSAGE_TYPE / messageType
    aliases are retained as a fallback for legacy or alternative payload shapes.
    Returns None when no routing field is found; resolve_message_type() then
    falls back to the root tag.
    """
    event_code = message.get(
        "eventCode", "event_code", "EVENT_CODE",
        "MESSAGE_TYPE", "messageType", "MSG_TYPE", "msgType",
    )
    return event_code.strip().upper() or None
