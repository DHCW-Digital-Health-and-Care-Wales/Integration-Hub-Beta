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

    SPEC GAP: Location.name — the mapping spreadsheet marks the source as
    "??". The referrer_location field holds a full free-text address string
    (e.g. "YSBYTY GWYNEDD, PENRHOSGARNEDD, BANGOR, GWYNEDD, LL57 2PW").
    The first comma-delimited segment is used as the name until the spec
    owner provides a dedicated name field.

    identifier.value — using referrer_location as-is for uniqueness until a
    dedicated code/id field is specified.
    """
    location = Location(
        id=location_uuid,
        meta=profile_meta(LOCATION_PROFILE),
    )

    referrer_location = message.get("referrer_location", "referrerLocation")
    if referrer_location:
        location.identifier = [
            Identifier(
                system=LOCATION_IDENTIFIER_SYSTEM,
                value=referrer_location,
            )
        ]

        # SPEC GAP: use first line of the free-text location as the name
        first_segment = referrer_location.split(",")[0].strip()
        if first_segment:
            location.name = first_segment

    address = _build_address(message)
    if address:
        location.address = address

    return location


def _build_address(message: PromsMessage) -> Optional[Address]:
    """Build Location.address from referrer_postcode."""
    postcode = message.get("referrer_postcode", "referrerPostcode")
    if not postcode:
        return None
    return Address(postalCode=postcode)
