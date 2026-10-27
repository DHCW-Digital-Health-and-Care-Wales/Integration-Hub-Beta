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
    GMC_NUMBER_SYSTEM,
    ODS_ORGANISATION_CODE_SYSTEM,
    ORGANIZATION_PROFILE,
    PRACTITIONER_PROFILE,
    WPAS_PRACTITIONER_SYSTEM,
)
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from ..reference_data import dha_code_name
from ..source_systems import get_source_system
from .mapping_utils import profile_meta


def map_practitioner(
    message: PromsMessage,
    practitioner_uuid: str,
    message_type: MessageType,
) -> Optional[Practitioner]:
    """Build the Practitioner resource for the bundle type.

    Base identifier is consultant_code under the WPAS practitioner system. Referral
    bundles add a second GMC-system identifier from referrer_code, and take the
    name from referrer_name; other bundles use clinicianName. The name is kept as
    free text (HumanName.text) rather than parsed.

    Returns None when no identifier or name is available.
    """
    is_referral = message_type.name == "REFERRAL"

    consultant_code = message.get("consultant_code", "consultantCode")
    if is_referral:
        name_source = message.get("referrer_name", "referrerName")
    else:
        name_source = message.get("clinicianName", "clinician_name", "CONS_NAME")

    identifiers: List[Identifier] = []
    if consultant_code:
        identifiers.append(Identifier(system=WPAS_PRACTITIONER_SYSTEM, value=consultant_code))
    if is_referral:
        referrer_code = message.get("referrer_code", "referrerCode")
        if referrer_code:
            identifiers.append(Identifier(system=GMC_NUMBER_SYSTEM, value=referrer_code))

    if not identifiers and not name_source:
        return None

    practitioner = Practitioner(id=practitioner_uuid, meta=profile_meta(PRACTITIONER_PROFILE))
    if identifiers:
        practitioner.identifier = identifiers
    if name_source:
        practitioner.name = [HumanName(text=name_source)]

    return practitioner


def map_organization(message: PromsMessage, organization_uuid: str) -> Optional[Organization]:
    """Build the Organization resource as the sending health board.

    Promptly asked for the health board (not the practice): identifier.value is
    the ODS code from hb_code and the name is the health board's name, taken from
    the system_id lookup and falling back to the ODS code lookup. Returns None
    when hb_code is absent.
    """
    hb_code = message.get("hb_code", "hbCode", "HB_CODE")
    if not hb_code:
        return None

    organization = Organization(
        id=organization_uuid,
        meta=profile_meta(ORGANIZATION_PROFILE),
        active=True,
        identifier=[Identifier(system=ODS_ORGANISATION_CODE_SYSTEM, value=hb_code)],
    )

    source_system = get_source_system(message.get("system_id", "SYSTEM_ID", "systemId"))
    name = source_system.name if source_system else dha_code_name(hb_code)
    if name and name != hb_code:
        organization.name = name

    return organization
