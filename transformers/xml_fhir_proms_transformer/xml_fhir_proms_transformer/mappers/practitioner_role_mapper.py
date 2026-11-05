"""PractitionerRole mapper - Referral bundle only.

A Referral carries one PractitionerRole: the consultant (carries the specialty and organization,
listed in MessageHeader.focus). ServiceRequest.requester and .performer both reference
Practitioners directly: the referrer and the consultant.
"""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.practitionerrole import PractitionerRole
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import (
    PRACTICE_SETTING_CODES,
    PRACTICE_SETTING_SYSTEM,
    WPAS_IG_PRACTITIONER_ROLE_IDENTIFIER_SYSTEM,
    WPAS_IG_PRACTITIONER_ROLE_PROFILE,
)
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta


def _build_role(
    role_uuid: str,
    identifier_system: str,
    identifier_value: Optional[str],
    practitioner_uuid: Optional[str],
    organization_uuid: Optional[str],
) -> PractitionerRole:
    role = PractitionerRole(id=role_uuid, meta=profile_meta(WPAS_IG_PRACTITIONER_ROLE_PROFILE))

    if identifier_value:
        role.identifier = [Identifier(system=identifier_system, value=identifier_value)]
    if practitioner_uuid:
        role.practitioner = Reference(reference=f"urn:uuid:{practitioner_uuid}", type="Practitioner")
    if organization_uuid:
        role.organization = Reference(reference=f"urn:uuid:{organization_uuid}", type="Organization")
    return role


def map_consultant_role(
    message: PromsMessage,
    role_uuid: str,
    practitioner_uuid: Optional[str] = None,
    organization_uuid: Optional[str] = None,
) -> PractitionerRole:
    """Build the consultant's PractitionerRole; its identifier is the consultant_code.

    The specialty is sent only when the 3-digit code at the start of
    consultant_specialty is in the national UKCore practice setting list.
    """
    role = _build_role(
        role_uuid,
        WPAS_IG_PRACTITIONER_ROLE_IDENTIFIER_SYSTEM,
        message.get("consultant_code", "consultantCode"),
        practitioner_uuid,
        organization_uuid,
    )

    specialty_code = (message.get("consultant_specialty", "consultantSpecialty") or "").strip()[:3]
    if specialty_code in PRACTICE_SETTING_CODES:
        specialty_name = message.get("specialty_name", "specialtyName", "main_specialty_name")
        role.specialty = [
            CodeableConcept(
                coding=[
                    Coding(
                        system=PRACTICE_SETTING_SYSTEM,
                        code=specialty_code,
                        display=specialty_name or None,
                    )
                ]
            )
        ]
    return role
