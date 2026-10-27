"""Location mapper — used in all bundle types.

Maps the WPAS referrer location fields to a FHIR R4B Location resource.
"""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.address import Address
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.location import Location

from ..fhir_constants import (
    LOCATION_IDENTIFIER_SYSTEM,
    LOCATION_PROFILE,
)
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta


def map_location(
    message: PromsMessage,
    location_uuid: str,
) -> Location:
    """Build the Location resource.

    identifier.value is referrer_prac; there is no Location.name in the mapping.
    address.text is referrer_location + referrer_postcode.
    """
    location = Location(
        id=location_uuid,
        meta=profile_meta(LOCATION_PROFILE),
        status="active",
    )

    referrer_prac = message.get("referrer_prac", "referrerPrac")
    if referrer_prac:
        location.identifier = [Identifier(system=LOCATION_IDENTIFIER_SYSTEM, value=referrer_prac)]

    address = _build_address(message)
    if address:
        location.address = address

    return location


def _build_address(message: PromsMessage) -> Optional[Address]:
    """Build Location.address from referrer_location and referrer_postcode."""
    location_text = message.get("referrer_location", "referrerLocation")
    postcode = message.get("referrer_postcode", "referrerPostcode")
    text = " ".join(p for p in (location_text, postcode) if p)
    if not text:
        return None

    address = Address(text=text)
    if postcode:
        address.postalCode = postcode
    return address
