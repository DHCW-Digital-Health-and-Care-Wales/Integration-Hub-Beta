"""Health board lookups keyed on the WPAS `SYSTEM_ID` field.

PAS identifier URLs were ported from the `PAS_Identifier_Url` JavaScript function
on the INSE wiki (`.../PROMS/WPAS_To_PROMS/Javascript Functions`). The
`MessageHeader.source` name and endpoint follow the "WPAS PROMS Mapping -
Amy_Questions" spreadsheet: the endpoint is `WPAS_SOURCE_ENDPOINT_BASE` plus the
system_id, and the name is the health board name.

Only the seven WPAS health boards are listed. 103 (Princess of Wales, PIMS) and
140 (Cardiff and Vale) do not use WPAS, and Velindre is 310 (not 131).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from typing import Optional

from .fhir_constants import WPAS_SOURCE_ENDPOINT_BASE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSystem:
    """A WPAS source health board."""

    system_id: str
    name: str
    # Patient.identifier[1].system - the health board's local PAS identifier URL.
    pas_identifier_system: str
    # ODS code of the health board (Organization.identifier).
    ods_code: str
    # Board-specific identifier system for the WPAS consultant code.
    consultant_code_system: str
    # Board-specific identifier system for the WPAS referrer code.
    referrer_code_system: str
    # MessageHeader.source.endpoint; derived from the system_id unless overridden.
    endpoint: Optional[str] = None


def _board(
    system_id: str,
    name: str,
    domain: str,
    ods_code: str,
    pas_path: str = "pas-identifier",
    code_path: Optional[str] = None,
) -> SourceSystem:
    """Build a board entry; code_path, when set, replaces the wpas-*-code identifier paths (Betsi exception)."""
    base = f"https://fhir.{domain}.nhs.wales/Id"
    return SourceSystem(
        system_id=system_id,
        name=name,
        pas_identifier_system=f"{base}/{pas_path}",
        ods_code=ods_code,
        consultant_code_system=f"{base}/{code_path or 'wpas-consultant-code'}",
        referrer_code_system=f"{base}/{code_path or 'wpas-referrer-code'}",
    )


_SOURCE_SYSTEMS: dict[str, SourceSystem] = {
    "108": _board("108", "Swansea Bay University Health Board", "sbuhb", "7A3"),
    "109": _board(
        "109",
        "Betsi Cadwaladr University Health Board",
        "bcuhb",
        "7A1",
        "central-pas-identifier",
        "central-pas-identifier",
    ),
    "139": _board("139", "Aneurin Bevan University Health Board", "abuhb", "7A6"),
    "149": _board("149", "Hywel Dda University Health Board", "hduhb", "7A2"),
    "170": _board("170", "Powys Teaching Health Board", "pthb", "7A7"),
    "126": _board("126", "Cwm Taf Morgannwg University Health Board", "ctmuhb", "7A5"),
    "310": _board("310", "Velindre University NHS Trust", "vunhst", "RQF"),
}


def get_source_system(system_id: Optional[str]) -> Optional[SourceSystem]:
    """Look up a health board by WPAS system_id or hbCode.

    Both system_id and hbCode appear in real payloads and identify the same
    health board; both are tried so a single lookup covers both dialects.
    Returns None (and logs) for an unknown or missing identifier.
    """
    if not system_id:
        logger.warning("No system_id/hbCode in payload - MessageHeader.source and PAS identifier will be omitted")
        return None

    key = system_id.strip()
    source_system = _SOURCE_SYSTEMS.get(key)
    if source_system is None:
        logger.warning(
            "Unknown WPAS system_id/hbCode %r - MessageHeader.source and PAS identifier will be omitted",
            key,
        )
        return None

    # The endpoint is derived from the system_id; deployments can still override it.
    override = os.getenv(f"WPAS_SOURCE_ENDPOINT_{key}")
    endpoint = override or f"{WPAS_SOURCE_ENDPOINT_BASE}/{key}"
    return replace(source_system, endpoint=endpoint)


def get_pas_identifier_system(system_id: Optional[str]) -> Optional[str]:
    """Return the health board's PAS identifier URL, or None if unknown."""
    source_system = get_source_system(system_id)
    return source_system.pas_identifier_system if source_system else None
