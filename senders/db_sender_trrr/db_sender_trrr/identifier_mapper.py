from __future__ import annotations

import re


def map_adt_a05_identifiers(message: str) -> dict[str, str]:
    """Map a WLIMS ADT_A05 PID-3 identifier pair into the TRRR association payload.

    The service preserves identifier text exactly as received and rejects any message whose
    PID-3 does not include both assigning authorities: 328 (WLIMS/LIMS) and NHS.
    """
    values: dict[str, str] = {}

    for segment in message.splitlines():
        if not segment or not segment.startswith("PID|"):
            continue

        repetitions = segment.split("|")[3].split("~") if len(segment.split("|")) > 3 else []
        for repetition in repetitions:
            component_parts = repetition.split("^")
            if len(component_parts) < 2:
                continue

            identifier_value = component_parts[0].strip()
            if not identifier_value:
                continue

            authority = _extract_authority(component_parts)
            if authority == "328" and "LIMSIdentifier" not in values:
                values["LIMSIdentifier"] = identifier_value
            elif authority == "NHS" and "NewIdentifier" not in values:
                values["NewIdentifier"] = identifier_value
                values["NewIdentifierAssigningAuthority"] = "NHS"

    if "LIMSIdentifier" not in values:
        raise ValueError("Missing LIMS identifier")
    if "NewIdentifier" not in values:
        raise ValueError("Missing NHS identifier")

    return {
        "LIMSIdentifier": values["LIMSIdentifier"],
        "NewIdentifier": values["NewIdentifier"],
        "NewIdentifierAssigningAuthority": values["NewIdentifierAssigningAuthority"],
    }


def _extract_authority(parts: list[str]) -> str | None:
    for index in (3, 2, 1):
        if index < len(parts):
            authority = parts[index].strip()
            if authority in {"328", "NHS"}:
                return authority
    return None
