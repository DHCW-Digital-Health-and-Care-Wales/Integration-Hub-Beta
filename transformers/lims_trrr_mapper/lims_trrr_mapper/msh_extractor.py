from __future__ import annotations

import re
import xml.etree.ElementTree as ET  # nosec B405
from dataclasses import dataclass


@dataclass(frozen=True)
class MshInfo:
    """Contains sanitized MSH details for Information Governance compliant logging."""

    msh_text: str
    control_id: str
    message_type: str


def extract_msh_for_logging(message_body: str) -> MshInfo:
    """Extract strictly the MSH portion of an HL7 message (ER7 or XML) for safe logging.

    Guarantees no PID, OBX, OBR, or other clinical/patient segments are leaked into logs.
    """
    if not message_body or not message_body.strip():
        return MshInfo(msh_text="[Empty message body]", control_id="UNKNOWN", message_type="UNKNOWN")

    cleaned = message_body.strip()

    # 1. HL7 v2 XML Format
    if cleaned.startswith("<") or "<MSH" in cleaned:
        try:
            root = ET.fromstring(cleaned)  # nosec B314
            msh_elem: ET.Element | None = None
            if root.tag.endswith("MSH"):
                msh_elem = root
            else:
                for elem in root.iter():
                    if elem.tag.endswith("MSH"):
                        msh_elem = elem
                        break

            if msh_elem is not None:
                control_id = _extract_xml_text(msh_elem, ["MSH.10.1", "MSH.10"]) or "UNKNOWN"
                msg_type = _extract_xml_msg_type(msh_elem) or "UNKNOWN"
                # Strip all namespaces or prefixes when serializing if necessary, or just serialize the element
                serialized_msh = ET.tostring(msh_elem, encoding="unicode").strip()
                return MshInfo(msh_text=serialized_msh, control_id=control_id, message_type=msg_type)
        except ET.ParseError:
            # Fallback regex to isolate <MSH>...</MSH> block if XML is partial
            match = re.search(r"(<MSH\b[^>]*>.*?</MSH>)", cleaned, re.DOTALL | re.IGNORECASE)
            if match:
                msh_raw = match.group(1).strip()
                cid_match = re.search(r"<MSH\.10[^>]*>(?:<[^>]+>)*([^<]+)", msh_raw)
                control_id = cid_match.group(1).strip() if cid_match else "UNKNOWN"
                return MshInfo(msh_text=msh_raw, control_id=control_id, message_type="UNKNOWN")
        return MshInfo(
            msh_text="[XML MSH extraction failed - structure malformed]",
            control_id="UNKNOWN",
            message_type="UNKNOWN",
        )

    # 2. ER7 Pipe-Delimited Format
    for line in cleaned.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("MSH"):
            sep = line_clean[3] if len(line_clean) > 3 else "|"
            fields = line_clean.split(sep)
            # In ER7:
            # fields[0] = 'MSH'
            # fields[1] = encoding characters (MSH-2)
            # fields[8] = message type (MSH-9)
            # fields[9] = message control ID (MSH-10)
            msg_type = fields[8] if len(fields) > 8 and fields[8] else "UNKNOWN"
            control_id = fields[9] if len(fields) > 9 and fields[9] else "UNKNOWN"
            return MshInfo(msh_text=line_clean, control_id=control_id, message_type=msg_type)

    return MshInfo(msh_text="[No MSH segment identified]", control_id="UNKNOWN", message_type="UNKNOWN")


def _extract_xml_text(parent: ET.Element, tag_names: list[str]) -> str | None:
    for tag_name in tag_names:
        for elem in parent.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == tag_name and elem.text and elem.text.strip():
                return elem.text.strip()
    return None


def _extract_xml_msg_type(msh_elem: ET.Element) -> str | None:
    # Check for MSH.9 components: MSH.9.1, MSH.9.2, MSH.9.3
    code = _extract_xml_text(msh_elem, ["MSG.1", "MSH.9.1"])
    trigger = _extract_xml_text(msh_elem, ["MSG.2", "MSH.9.2"])
    structure = _extract_xml_text(msh_elem, ["MSG.3", "MSH.9.3"])

    parts = [p for p in [code, trigger, structure] if p]
    if parts:
        return "^".join(parts)
    direct = _extract_xml_text(msh_elem, ["MSH.9"])
    return direct
