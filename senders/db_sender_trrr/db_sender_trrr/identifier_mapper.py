"""TRRR identifier mapping for LIMS-to-NHS association.

Supports two classified message variants, both of which link a sending-LIMS local identifier to a
patient's NHS number and preserve identifier text exactly as received (leading zeroes included):

* ``ADT_A05`` / ``A31`` (WLIMS NHS-ID update): the LIMS identifier is the PID-3 repetition whose
  assigning authority is the fixed WLIMS code ``328``.
* ``ADT^A40`` classified as ``ADT_A39_LIMS_NHS``: the LIMS identifier is determined dynamically from
  the sending application in ``MSH-3.1``; the PID-3 repetition whose assigning authority equals that
  value is used as the LIMS identifier. This lets a single mapping support multiple sending systems.

Both variants take the NHS number from the PID-3 repetition whose assigning authority is ``NHS``.

Messages are accepted as HL7 v2 pipe-delimited (ER7) or HL7 v2 XML. No identifier value is converted,
reformatted, or interpreted as numeric data.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass

# Fixed WLIMS assigning authority used by the A05/A31 NHS-ID update variant.
LIMS_A05_ASSIGNING_AUTHORITY = "328"
# Assigning authority of the patient NHS number, for both variants.
NHS_ASSIGNING_AUTHORITY = "NHS"

TRIGGER_A05 = "A05"
TRIGGER_A31 = "A31"
TRIGGER_A40 = "A40"
_A05_TRIGGERS = frozenset({TRIGGER_A05, TRIGGER_A31})


@dataclass(frozen=True)
class Pid3Identifier:
    """A single PID-3 repetition: the CX.1 value and its CX.4.1 (HD.1) assigning authority."""

    value: str
    authority: str


@dataclass(frozen=True)
class ParsedTrrrMessage:
    """Normalised view of the fields the TRRR mapping needs, parsed from ER7 or XML."""

    sending_application: str
    trigger_event: str
    identifiers: tuple[Pid3Identifier, ...]


def map_trrr_identifiers(message: str) -> dict[str, str]:
    """Map a classified LIMS message to the TRRR update payload, routing on the MSH-9.2 trigger.

    ``A40`` uses the dynamic sending-LIMS rule; ``A05``/``A31`` use the fixed WLIMS (328) rule.
    """
    parsed = _parse_message(message)
    trigger = parsed.trigger_event.upper()

    if trigger == TRIGGER_A40:
        return _map_dynamic_lims(parsed)
    if trigger in _A05_TRIGGERS:
        return _build_mapping(parsed, LIMS_A05_ASSIGNING_AUTHORITY)

    raise ValueError(f"Unsupported trigger event: {parsed.trigger_event or 'UNKNOWN'}")


def map_adt_a05_identifiers(message: str) -> dict[str, str]:
    """Map a WLIMS ADT_A05/A31 message, using the fixed assigning authority ``328`` for the LIMS ID.

    Preserves identifier text exactly and rejects any message whose PID-3 does not include both the
    ``328`` and ``NHS`` assigning authorities.
    """
    parsed = _parse_message(message)
    return _build_mapping(parsed, LIMS_A05_ASSIGNING_AUTHORITY)


def map_adt_a40_identifiers(message: str) -> dict[str, str]:
    """Map an ADT^A40 (ADT_A39_LIMS_NHS) message, resolving the LIMS authority from ``MSH-3.1``.

    The PID-3 repetition whose assigning authority equals the sending application (MSH-3.1) is used as
    the LIMS identifier; the ``NHS`` repetition supplies the NHS number. Identifier text is preserved
    exactly as received.
    """
    parsed = _parse_message(message)
    return _map_dynamic_lims(parsed)


def _map_dynamic_lims(parsed: ParsedTrrrMessage) -> dict[str, str]:
    if not parsed.sending_application:
        raise ValueError("Missing sending LIMS authority")
    return _build_mapping(parsed, parsed.sending_application)


def _build_mapping(parsed: ParsedTrrrMessage, lims_authority: str) -> dict[str, str]:
    lims_identifier = _first_identifier_for_authority(parsed.identifiers, lims_authority)
    if lims_identifier is None:
        raise ValueError("Missing LIMS identifier")

    nhs_identifier = _first_identifier_for_authority(parsed.identifiers, NHS_ASSIGNING_AUTHORITY)
    if nhs_identifier is None:
        raise ValueError("Missing NHS identifier")

    return {
        "LIMSIdentifier": lims_identifier,
        "NewIdentifier": nhs_identifier,
        "NewIdentifierAssigningAuthority": NHS_ASSIGNING_AUTHORITY,
    }


def _first_identifier_for_authority(identifiers: tuple[Pid3Identifier, ...], authority: str) -> str | None:
    for identifier in identifiers:
        if identifier.authority == authority:
            return identifier.value
    return None


def _parse_message(message: str) -> ParsedTrrrMessage:
    if not message or not message.strip():
        raise ValueError("Empty message body")

    cleaned = message.strip()
    if cleaned.startswith("<") or "<MSH" in cleaned:
        return _parse_xml(cleaned)
    return _parse_er7(cleaned)


def _parse_er7(message: str) -> ParsedTrrrMessage:
    sending_application = ""
    trigger_event = ""
    identifiers: list[Pid3Identifier] = []

    # HL7 segments are carriage-return delimited; tolerate CRLF/LF from varied producers.
    segments = message.replace("\r\n", "\r").replace("\n", "\r").split("\r")
    for segment in segments:
        if segment.startswith("MSH"):
            fields = segment.split("|")
            # MSH-3 is fields[2], MSH-9 is fields[8] (MSH-1 is the field separator itself).
            if len(fields) > 2:
                sending_application = fields[2].split("^")[0].strip()
            if len(fields) > 8:
                msh9_components = fields[8].split("^")
                if len(msh9_components) > 1:
                    trigger_event = msh9_components[1].strip()
        elif segment.startswith("PID"):
            fields = segment.split("|")
            if len(fields) <= 3:
                continue
            for repetition in fields[3].split("~"):
                components = repetition.split("^")
                value = components[0]  # CX.1 - preserved exactly, never stripped
                if not value.strip():
                    continue
                authority = ""
                if len(components) > 3:
                    # CX.4 is an HD; HD.1 is its first sub-component (& delimited).
                    authority = components[3].split("&")[0].strip()
                identifiers.append(Pid3Identifier(value=value, authority=authority))

    return ParsedTrrrMessage(sending_application, trigger_event, tuple(identifiers))


def _parse_xml(message: str) -> ParsedTrrrMessage:
    try:
        root = ET.fromstring(message)  # nosec B314 - trusted internal HL7 payload, no DTD/entity use
    except ET.ParseError as exc:
        raise ValueError("Malformed XML message") from exc

    msh = root if _local_name(root.tag) == "MSH" else _first_descendant(root, "MSH")

    sending_application = ""
    trigger_event = ""
    if msh is not None:
        msh3 = _first_child(msh, "MSH.3")
        if msh3 is not None:
            sending_application = _hd1_text(msh3)
        msh9 = _first_child(msh, "MSH.9")
        if msh9 is not None:
            msg2 = _first_child(msh9, "MSG.2")
            if msg2 is not None and msg2.text and msg2.text.strip():
                trigger_event = msg2.text.strip()

    identifiers: list[Pid3Identifier] = []
    for pid3 in _all_descendants(root, "PID.3"):
        cx1 = _first_child(pid3, "CX.1")
        value = cx1.text if cx1 is not None and cx1.text is not None else ""
        if not value.strip():
            continue
        cx4 = _first_child(pid3, "CX.4")
        authority = _hd1_text(cx4) if cx4 is not None else ""
        identifiers.append(Pid3Identifier(value=value, authority=authority))

    return ParsedTrrrMessage(sending_application, trigger_event, tuple(identifiers))


def _hd1_text(element: ET.Element) -> str:
    """Return HD.1 text, accepting either a nested ``<HD.1>`` child or direct element text."""
    hd1 = _first_child(element, "HD.1")
    if hd1 is not None and hd1.text and hd1.text.strip():
        return hd1.text.strip()
    if element.text and element.text.strip():
        return element.text.strip()
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    for descendant in element.iter():
        if _local_name(descendant.tag) == name:
            return descendant
    return None


def _all_descendants(element: ET.Element, name: str) -> list[ET.Element]:
    return [descendant for descendant in element.iter() if _local_name(descendant.tag) == name]
