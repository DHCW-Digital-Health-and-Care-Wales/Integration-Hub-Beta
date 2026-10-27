"""PractitionerRole mapper - Bundle.entry[3] of a Referral bundle only.

Referral is the only bundle type that carries PractitionerRole.
"""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.practitionerrole import PractitionerRole
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import (
    PRACTITIONER_ROLE_IDENTIFIER_SYSTEM,
    PRACTITIONER_ROLE_PROFILE,
    PRACTITIONER_ROLE_REFERRAL_IDENTIFIER_SYSTEM,
)
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta


def map_practitioner_role(
    message: PromsMessage,
    practitioner_role_uuid: str,
    practitioner_uuid: Optional[str] = None,
    organization_uuid: Optional[str] = None,
    location_uuid: Optional[str] = None,
    is_referral: bool = True,
) -> PractitionerRole:
    """Build the PractitionerRole resource.

    Referral: identifier is the referrer_code under the GMC system.
    Otherwise: consultant_code under the WPAS practitioner-role system.
    """
    if is_referral:
        identifier_system = PRACTITIONER_ROLE_REFERRAL_IDENTIFIER_SYSTEM
        identifier_value = message.get("referrer_code", "referrerCode")
    else:
        identifier_system = PRACTITIONER_ROLE_IDENTIFIER_SYSTEM
        identifier_value = message.get("consultant_code", "consultantCode")

    practitioner_role = PractitionerRole(
        id=practitioner_role_uuid,
        meta=profile_meta(PRACTITIONER_ROLE_PROFILE),
    )

    if identifier_value:
        practitioner_role.identifier = [Identifier(system=identifier_system, value=identifier_value)]

    if practitioner_uuid:
        practitioner_role.practitioner = Reference(
            reference=f"urn:uuid:{practitioner_uuid}",
            type="Practitioner",
        )

    if organization_uuid:
        practitioner_role.organization = Reference(
            reference=f"urn:uuid:{organization_uuid}",
            type="Organization",
        )

    # specialty — the first 3 characters of consultant_specialty are the specialty code
    specialty_code = (message.get("consultant_specialty", "consultantSpecialty") or "")[:3]
    specialty_name = message.get("specialty_name", "specialtyName", "main_specialty_name")
    if specialty_code or specialty_name:
        practitioner_role.specialty = [
            CodeableConcept(
                coding=[
                    Coding(
                        code=specialty_code or None,
                        display=specialty_name or None,
                    )
                ]
            )
        ]

    if location_uuid:
        practitioner_role.location = [
            Reference(reference=f"urn:uuid:{location_uuid}", type="Location")
        ]

    return practitioner_role
