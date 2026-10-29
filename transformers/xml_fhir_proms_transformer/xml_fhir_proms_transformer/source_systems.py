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
from dataclasses import dataclass
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
    # MessageHeader.source.endpoint; derived from the system_id unless overridden.
    endpoint: Optional[str] = None


_SOURCE_SYSTEMS: dict[str, SourceSystem] = {
    "108": SourceSystem(
        system_id="108",
        name="Swansea Bay Health Board",
        pas_identifier_system="https://fhir.sbuhb.nhs.wales/Id/pas-identifier",
    ),
    "109": SourceSystem(
        system_id="109",
        name="Betsi Cadwaladr University Health Board",
        pas_identifier_system="https://fhir.bcuhb.nhs.wales/Id/central-pas-identifier",
    ),
    "139": SourceSystem(
        system_id="139",
        name="Aneurin Bevan University Health Board",
        pas_identifier_system="https://fhir.abuhb.nhs.wales/Id/pas-identifier",
    ),
    "149": SourceSystem(
        system_id="149",
        name="Hywel Dda University Health Board",
        pas_identifier_system="https://fhir.hduhb.nhs.wales/Id/pas-identifier",
    ),
    "170": SourceSystem(
        system_id="170",
        name="Powys Teaching Health Board",
        pas_identifier_system="https://fhir.pthb.nhs.wales/Id/pas-identifier",
    ),
    "126": SourceSystem(
        system_id="126",
        name="Cwm Taf Morgannwg University Health Board",
        pas_identifier_system="https://fhir.ctmuhb.nhs.wales/Id/pas-identifier",
    ),
    "310": SourceSystem(
        system_id="310",
        name="Velindre University NHS Trust",
        pas_identifier_system="https://fhir.vunhst.nhs.wales/Id/pas-identifier",
    ),
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
    return SourceSystem(
        system_id=source_system.system_id,
        name=source_system.name,
        pas_identifier_system=source_system.pas_identifier_system,
        endpoint=endpoint,
    )


def get_pas_identifier_system(system_id: Optional[str]) -> Optional[str]:
    """Return the health board's PAS identifier URL, or None if unknown."""
    source_system = get_source_system(system_id)
    return source_system.pas_identifier_system if source_system else None
