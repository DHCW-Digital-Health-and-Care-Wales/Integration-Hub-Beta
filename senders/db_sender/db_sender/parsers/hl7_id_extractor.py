from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET  # nosec B405

from db_sender.msh_extractor import extract_msh_for_logging

logger = logging.getLogger(__name__)


def get_trigger_event(message_body: str) -> str:
    """Extract HL7 trigger event (e.g. 'A31', 'A40') from message body."""
    msh_info = extract_msh_for_logging(message_body)
    return msh_info.trigger_event


def extract_mrg_identifiers(message_body: str) -> tuple[str | None, str | None]:
    """Extract old patient identifier and assigning authority from MRG segment.

    Returns:
        tuple of (old_identifier, old_assigning_authority).
        Both are None if MRG segment is absent or fields cannot be parsed.
    """
    if not message_body or not message_body.strip():
        return None, None

    cleaned = message_body.strip()

    if cleaned.startswith("<") or "<MRG" in cleaned:
        return _extract_mrg_from_xml(cleaned)
    return _extract_mrg_from_er7(cleaned)


def extract_pid_identifier_by_authority(message_body: str, authority: str) -> str | None:
    """Extract the patient identifier (CX.1) from PID-3 matching the specified assigning authority.

    Args:
        message_body: Raw HL7 message (XML or ER7).
        authority: Target assigning authority (e.g. '328', 'NHS').

    Returns:
        The matched patient identifier string, or None if no match is found.
    """
    if not message_body or not message_body.strip() or not authority:
        return None

    cleaned = message_body.strip()

    if cleaned.startswith("<") or "<PID" in cleaned:
        return _extract_pid_by_authority_xml(cleaned, authority)
    return _extract_pid_by_authority_er7(cleaned, authority)


# ---------------------------------------------------------------------------
# ER7 Extraction Helpers
# ---------------------------------------------------------------------------


def _extract_mrg_from_er7(cleaned: str) -> tuple[str | None, str | None]:
    for line in cleaned.splitlines():
        line_clean = line.strip()
        if not line_clean.startswith("MRG"):
            continue

        sep = line_clean[3] if len(line_clean) > 3 else "|"
        fields = line_clean.split(sep)
        if len(fields) < 2 or not fields[1].strip():
            return None, None

        mrg_1 = fields[1].strip()
        repetitions = mrg_1.split("~")
        for repetition in repetitions:
            rep_clean = repetition.strip()
            if not rep_clean:
                continue

            components = rep_clean.split("^")
            old_id = components[0].strip() if components[0].strip() else None

            old_auth: str | None = None
            if len(components) > 3:
                # Standard ER7: CX.4 is component index 3
                if components[3].strip():
                    old_auth = components[3].split("&")[0].strip() or None
            elif len(components) in (2, 3):
                # Compacted ER7: ID^AUTH or ID^AUTH^TYPE
                if components[1].strip():
                    old_auth = components[1].split("&")[0].strip() or None

            if old_id or old_auth:
                return old_id, old_auth

        return None, None

    return None, None


def _extract_pid_by_authority_er7(cleaned: str, authority: str) -> str | None:
    target_auth = authority.strip()

    for line in cleaned.splitlines():
        line_clean = line.strip()
        if not line_clean.startswith("PID"):
            continue

        sep = line_clean[3] if len(line_clean) > 3 else "|"
        fields = line_clean.split(sep)
        if len(fields) < 4 or not fields[3].strip():
            continue

        pid_3 = fields[3].strip()
        repetitions = pid_3.split("~")

        for repetition in repetitions:
            rep_clean = repetition.strip()
            if not rep_clean:
                continue

            components = rep_clean.split("^")
            ident = components[0].strip()
            if not ident:
                continue

            auth_code: str | None = None
            if len(components) > 3:
                # Standard ER7: CX.4 is index 3
                if components[3].strip():
                    auth_code = components[3].split("&")[0].strip()
            elif len(components) in (2, 3):
                # Compacted ER7: ID^AUTH or ID^AUTH^TYPE
                if components[1].strip():
                    auth_code = components[1].split("&")[0].strip()

            if auth_code and _authority_matches(auth_code, target_auth):
                return ident

    return None


def _authority_matches(actual: str, expected: str) -> bool:
    return actual.strip().lower() == expected.strip().lower()


# ---------------------------------------------------------------------------
# XML Extraction Helpers
# ---------------------------------------------------------------------------


def _local_tag(element: ET.Element) -> str:
    tag = element.tag
    return tag.split("}")[-1] if "}" in tag else tag


def _extract_mrg_from_xml(cleaned: str) -> tuple[str | None, str | None]:
    try:
        root = ET.fromstring(cleaned)  # nosec B314
    except ET.ParseError:
        return _regex_fallback_mrg(cleaned)

    # Find MRG segment
    mrg_elem: ET.Element | None = None
    for elem in root.iter():
        if _local_tag(elem) == "MRG":
            mrg_elem = elem
            break

    if mrg_elem is None:
        return None, None

    # Check MRG.1 repetition elements first, else fall back to mrg_elem
    mrg1_list = [child for child in mrg_elem if _local_tag(child) == "MRG.1"]
    if not mrg1_list:
        mrg1_list = [mrg_elem]

    for mrg1 in mrg1_list:
        old_id: str | None = None
        old_auth: str | None = None

        for child in mrg1.iter():
            tag = _local_tag(child)
            if tag in ("CX.1", "MRG.1.1") and child.text and child.text.strip():
                if old_id is None:
                    old_id = child.text.strip()
            elif tag in ("CX.4", "MRG.1.4"):
                for hd in child.iter():
                    hd_tag = _local_tag(hd)
                    if hd_tag in ("HD.1", "MRG.1.4.1", "CX.4.1") and hd.text and hd.text.strip():
                        if old_auth is None:
                            old_auth = hd.text.strip()
                        break

        if old_id or old_auth:
            return old_id, old_auth

    return None, None


def _extract_pid_by_authority_xml(cleaned: str, authority: str) -> str | None:
    try:
        root = ET.fromstring(cleaned)  # nosec B314
    except ET.ParseError:
        return _regex_fallback_pid_by_authority(cleaned, authority)

    # Find all PID elements (including inside ADT_A39.PATIENT)
    for elem in root.iter():
        if _local_tag(elem) != "PID":
            continue

        # Look for PID.3 repetitions under this PID
        for pid3 in elem:
            if _local_tag(pid3) != "PID.3":
                continue

            ident_val: str | None = None
            auth_val: str | None = None

            for child in pid3.iter():
                tag = _local_tag(child)
                if tag in ("CX.1", "PID.3.1") and child.text and child.text.strip():
                    if ident_val is None:
                        ident_val = child.text.strip()
                elif tag in ("CX.4", "PID.3.4"):
                    for hd in child.iter():
                        hd_tag = _local_tag(hd)
                        if hd_tag in ("HD.1", "PID.3.4.1", "CX.4.1") and hd.text and hd.text.strip():
                            if auth_val is None:
                                auth_val = hd.text.strip()
                            break

            if ident_val and auth_val and _authority_matches(auth_val, authority):
                return ident_val

    return None


def _regex_fallback_mrg(cleaned: str) -> tuple[str | None, str | None]:
    match = re.search(r"<MRG\b[^>]*>(.*?)</MRG>", cleaned, re.DOTALL | re.IGNORECASE)
    if not match:
        return None, None

    mrg_content = match.group(1)
    mrg1_matches = re.findall(r"<MRG\.1\b[^>]*>(.*?)</MRG\.1>", mrg_content, re.DOTALL | re.IGNORECASE)
    targets = mrg1_matches if mrg1_matches else [mrg_content]

    for target_block in targets:
        id_match = re.search(r"<(?:CX\.1|MRG\.1\.1)[^>]*>(?:<[^>]+>)*([^<]+)", target_block)
        old_id = id_match.group(1).strip() if id_match else None

        auth_match = re.search(
            r"<(?:CX\.4|MRG\.1\.4)\b[^>]*>.*?<(?:HD\.1|MRG\.1\.4\.1)[^>]*>(?:<[^>]+>)*([^<]+)",
            target_block,
            re.DOTALL | re.IGNORECASE,
        )
        if not auth_match:
            auth_match = re.search(r"<MRG\.1\.4\.1[^>]*>(?:<[^>]+>)*([^<]+)", target_block)
        old_auth = auth_match.group(1).strip() if auth_match else None

        if old_id or old_auth:
            return old_id, old_auth

    return None, None


def _regex_fallback_pid_by_authority(cleaned: str, authority: str) -> str | None:
    pid3_matches = re.findall(r"<PID\.3\b[^>]*>(.*?)</PID\.3>", cleaned, re.DOTALL | re.IGNORECASE)
    for pid3 in pid3_matches:
        auth_match = re.search(
            r"<(?:CX\.4|PID\.3\.4)\b[^>]*>.*?<(?:HD\.1|PID\.3\.4\.1)[^>]*>(?:<[^>]+>)*([^<]+)",
            pid3,
            re.DOTALL | re.IGNORECASE,
        )
        if not auth_match:
            auth_match = re.search(r"<PID\.3\.4\.1[^>]*>(?:<[^>]+>)*([^<]+)", pid3)

        if auth_match and _authority_matches(auth_match.group(1), authority):
            id_match = re.search(r"<(?:CX\.1|PID\.3\.1)[^>]*>(?:<[^>]+>)*([^<]+)", pid3)
            if id_match:
                return id_match.group(1).strip()
    return None
