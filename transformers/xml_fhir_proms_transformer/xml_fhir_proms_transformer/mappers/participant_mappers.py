"""Practitioner and Organization mappers — Bundle.entry[n] for Practitioner and Organization.

Handles both referral-context (referrer_code / referrer_name) and
clinical-context (consultant_code / clinicianName) field variants from the
actual WPAS PromsEventRequest payload.

split_person_name() in mapping_utils.py handles both comma-first format
("Jones, Hannah") and prefix-first format ("ARDERN-JONES L").
"""

from __future__ import annotations

from typing import List, Optional

from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.organization import Organization
from fhir.resources.R4B.practitioner import Practitioner

from ..fhir_constants import (
    ODS_ORGANISATION_CODE_SYSTEM,
    ORGANIZATION_PROFILE,
    PRACTITIONER_PROFILE,
    WPAS_IG_PRACTITIONER_PROFILE,
    WPAS_PRACTITIONER_SYSTEM,
)
from ..proms_parser import PromsMessage
from ..reference_data import dha_code_name
from ..source_systems import SourceSystem, get_source_system
from .mapping_utils import profile_meta


def _resolve_source_system(message: PromsMessage) -> Optional[SourceSystem]:
    """Resolve the sending health board from system_id, falling back to hbCode.

    Matches the lookup in the Patient and MessageHeader mappers, so every resource
    agrees on the board when a payload carries only hbCode.
    """
    return get_source_system(
        message.get("system_id", "SYSTEM_ID", "systemId") or message.get("hbCode", "hb_code", "HB_CODE")
    )


def map_practitioner(message: PromsMessage, practitioner_uuid: str) -> Optional[Practitioner]:
    """Build the Practitioner resource for the non-Referral bundles.

    Identifier is consultant_code under the WPAS practitioner system; the name is
    clinicianName kept as free text (HumanName.text) rather than parsed.

    Returns None when no identifier or name is available.
    """
    consultant_code = message.get("consultant_code", "consultantCode")
    name_source = message.get("clinicianName", "clinician_name", "CONS_NAME")

    identifiers: List[Identifier] = []
    if consultant_code:
        identifiers.append(Identifier(system=WPAS_PRACTITIONER_SYSTEM, value=consultant_code))
    if not identifiers and not name_source:
        return None

    practitioner = Practitioner(id=practitioner_uuid, meta=profile_meta(PRACTITIONER_PROFILE))
    if identifiers:
        practitioner.identifier = identifiers
    if name_source:
        practitioner.name = [HumanName(text=name_source)]

    return practitioner


def map_referrer_practitioner(message: PromsMessage, practitioner_uuid: str) -> Optional[Practitioner]:
    """Build the referring GP Practitioner for a Referral bundle.

    DHCW (Amy) decided the referrer_code goes under the sending health board's own
    wpas-referrer-code system, as WPAS sends no GMC or GMP numbers. When the board is
    unknown there is no valid system, so the identifier is omitted; the name is
    referrer_name kept as free text.
    """
    code = message.get("referrer_code", "referrerCode")
    name = message.get("referrer_name", "referrerName")
    source_system = _resolve_source_system(message)
    has_identifier = bool(code and source_system)
    if not has_identifier and not name:
        return None

    practitioner = Practitioner(id=practitioner_uuid, meta=profile_meta(WPAS_IG_PRACTITIONER_PROFILE))
    if has_identifier and source_system:
        practitioner.identifier = [Identifier(system=source_system.referrer_code_system, value=code)]
    if name:
        practitioner.name = [HumanName(text=name)]
    return practitioner


def map_consultant_practitioner(message: PromsMessage, practitioner_uuid: str) -> Optional[Practitioner]:
    """Build the consultant Practitioner for a Referral bundle.

    The consultant_code identifier uses the sending health board's own system; when
    the board is unknown there is no valid system, so the identifier is omitted.
    """
    code = message.get("consultant_code", "consultantCode")
    name = message.get("clinicianName", "clinician_name", "CONS_NAME")
    source_system = _resolve_source_system(message)
    has_identifier = bool(code and source_system)
    if not has_identifier and not name:
        return None

    practitioner = Practitioner(id=practitioner_uuid, meta=profile_meta(WPAS_IG_PRACTITIONER_PROFILE))
    if has_identifier and source_system:
        practitioner.identifier = [Identifier(system=source_system.consultant_code_system, value=code)]
    if name:
        practitioner.name = [HumanName(text=name)]
    return practitioner


def map_organization(
    message: PromsMessage, organization_uuid: str, profile: str = ORGANIZATION_PROFILE
) -> Optional[Organization]:
    """Build the Organization resource as the sending health board.

    Promptly asked for the health board (not the practice): identifier.value is
    the board's ODS code, resolved from the system_id lookup (hbCode carries
    placeholders such as X98) and falling back to hb_code. The name is the health
    board's name. Returns None when neither yields an ODS code.
    """
    source_system = _resolve_source_system(message)
    hb_code = message.get("hb_code", "hbCode", "HB_CODE")
    ods_code = source_system.ods_code if source_system else hb_code
    if not ods_code:
        return None

    organization = Organization(
        id=organization_uuid,
        meta=profile_meta(profile),
        active=True,
        identifier=[Identifier(system=ODS_ORGANISATION_CODE_SYSTEM, value=ods_code)],
    )

    name = health_board_name(message)
    if name:
        organization.name = name

    return organization


def health_board_name(message: PromsMessage) -> Optional[str]:
    """Return the sending health board's name, or None when it can't be resolved."""
    source_system = _resolve_source_system(message)
    if source_system:
        return source_system.name
    hb_code = message.get("hb_code", "hbCode", "HB_CODE")
    name = dha_code_name(hb_code)
    return name if name and name != hb_code else None
