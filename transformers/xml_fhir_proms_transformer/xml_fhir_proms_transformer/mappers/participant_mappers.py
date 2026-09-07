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
)
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from ..reference_data import dha_code_name
from .mapping_utils import profile_meta, split_person_name


def map_practitioner(
    message: PromsMessage,
    practitioner_uuid: str,
    message_type: MessageType,
) -> Optional[Practitioner]:
    """Build the Practitioner resource for the bundle type.

    For Referral bundles: identifies the referring clinician via referrer_code
    and referrer_name (format: "ARDERN-JONES L").

    For all other bundle types: identifies the consultant via consultant_code
    and clinicianName (format: "Jones, Hannah" — comma-separated surname, given).

    Returns None when neither an identifier nor a name is available, so the
    bundle omits the entry rather than carrying an empty resource.

    Note: consultant_code values (e.g. "HANJO") may not be GMC numbers; the
    GMC system URL is used as the best available option pending spec clarification.
    """
    is_referral = message_type.name == "REFERRAL"

    if is_referral:
        identifier_value = message.get("referrer_code", "referrerCode")
        name_source = message.get("referrer_name", "referrerName")
    else:
        identifier_value = message.get("consultant_code", "consultantCode")
        name_source = message.get("clinicianName", "clinician_name", "CONS_NAME")

    if not identifier_value and not name_source:
        return None

    practitioner = Practitioner(id=practitioner_uuid, meta=profile_meta(PRACTITIONER_PROFILE))

    if identifier_value:
        practitioner.identifier = [Identifier(system=GMC_NUMBER_SYSTEM, value=identifier_value)]

    if name_source:
        prefixes, given, family = split_person_name(name_source)
        if family or given or prefixes:
            given_parts: Optional[List[Optional[str]]] = list(given) or None
            prefix_parts: Optional[List[Optional[str]]] = list(prefixes) or None
            practitioner.name = [
                HumanName(
                    family=family or None,
                    given=given_parts,
                    prefix=prefix_parts,
                )
            ]

    return practitioner


def map_organization(message: PromsMessage, organization_uuid: str) -> Optional[Organization]:
    """Build the Organization resource for the sending health board.

    Prefers the referrer_org field from the WPAS payload. Falls back to the
    DHA code lookup table when referrer_org is empty (as seen in real SIT payloads).

    Returns None when neither source yields a usable value.
    """
    # Try referrer_org from payload first — present but often empty in real messages
    referrer_org = message.get("referrer_org", "referrerOrg")
    # Fallback: ODS code from dhaCode / DHA_CODE with lookup table
    dha_code = message.get("dhaCode", "DHA_CODE", "dha_code")

    if not referrer_org and not dha_code:
        return None

    organization = Organization(
        id=organization_uuid,
        meta=profile_meta(ORGANIZATION_PROFILE),
    )

    if dha_code:
        organization.identifier = [Identifier(system=ODS_ORGANISATION_CODE_SYSTEM, value=dha_code)]

    if referrer_org:
        organization.name = referrer_org
    else:
        # Fallback to lookup table for health board name
        name = dha_code_name(dha_code) if dha_code else None
        if name:
            organization.name = name

    return organization
