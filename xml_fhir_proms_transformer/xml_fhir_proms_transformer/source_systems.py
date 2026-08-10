"""Health board lookups keyed on the WPAS `SYSTEM_ID` field.

Ported from the `PAS_Identifier_Url` JavaScript function on the INSE wiki
(`.../PROMS/WPAS_To_PROMS/Javascript Functions`) and the `MessageHeader.source`
rows of the Mapping Tables page.

The wiki's `ROUTING_RULES_WPAS` table routes eight `SYSTEM_ID`s to the PROMS
queue, so all eight are represented here. Only Swansea Bay (108) has a documented
`MessageHeader.source.name`/`endpoint`; the rest are left unset rather than
guessed, and the endpoint is environment-overridable so deployments can supply
the real values without a code change.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSystem:
    """A WPAS source health board."""

    system_id: str
    # MessageHeader.source.name / .endpoint. None where the wiki does not state them.
    name: Optional[str]
    endpoint: Optional[str]
    # Patient.identifier[1].system - the health board's local PAS identifier URL.
    pas_identifier_system: str


_SOURCE_SYSTEMS: dict[str, SourceSystem] = {
    "108": SourceSystem(
        system_id="108",
        name="Swansea Bay Health Board",
        endpoint="https://nhspsom.swanseabayhealthboard.com",
        pas_identifier_system="https://fhir.sbuhb.nhs.wales/Id/pas-identifier",
    ),
    "109": SourceSystem(
        system_id="109",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.bcuhb.nhs.wales/Id/central-pas-identifier",
    ),
    "139": SourceSystem(
        system_id="139",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.abuhb.nhs.wales/Id/pas-identifier",
    ),
    "149": SourceSystem(
        system_id="149",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.hduhb.nhs.wales/Id/pas-identifier",
    ),
    "170": SourceSystem(
        system_id="170",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.pthb.nhs.wales/Id/pas-identifier",
    ),
    "126": SourceSystem(
        system_id="126",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.ctmuhb.nhs.wales/Id/pas-identifier",
    ),
    "310": SourceSystem(
        system_id="310",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.vunhst.nhs.wales/Id/pas-identifier",
    ),
    "140": SourceSystem(
        system_id="140",
        name=None,
        endpoint=None,
        pas_identifier_system="https://fhir.cavuhb.nhs.wales/Id/pas-identifier",
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
        logger.warning("Unknown WPAS system_id/hbCode %r - MessageHeader.source and PAS identifier will be omitted", key)
        return None

    # Deployments can supply the per-health-board endpoint the mapping omits.
    override = os.getenv(f"WPAS_SOURCE_ENDPOINT_{key}")
    if override:
        return SourceSystem(
            system_id=source_system.system_id,
            name=source_system.name,
            endpoint=override,
            pas_identifier_system=source_system.pas_identifier_system,
        )

    return source_system


def get_pas_identifier_system(system_id: Optional[str]) -> Optional[str]:
    """Return the health board's PAS identifier URL, or None if unknown."""
    source_system = get_source_system(system_id)
    return source_system.pas_identifier_system if source_system else None
