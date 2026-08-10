"""Small shared helpers used across the PROMS resource mappers."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Callable, Optional

from fhir.resources.R4B.meta import Meta

logger = logging.getLogger(__name__)

UuidFactory = Callable[[], str]

_DATE_ONLY_FORMATS = ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%d-%m-%Y")
_DATE_TIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y%m%d%H%M%S",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)

# Title prefixes seen in the WPAS CONS_NAME field, which arrives as a single
# string such as "Dr James Chess".
_NAME_PREFIXES = frozenset(
    {
        "DR",
        "DR.",
        "MR",
        "MR.",
        "MRS",
        "MRS.",
        "MS",
        "MS.",
        "MISS",
        "PROF",
        "PROF.",
        "PROFESSOR",
        "SIR",
        "DAME",
    }
)


def new_uuid() -> str:
    """Default UUID factory. Injectable so tests can produce stable bundles."""
    return str(uuid.uuid4())


def urn_uuid(resource_uuid: str) -> str:
    """Build the `urn:uuid:` fullUrl form required for bundle entries."""
    return f"urn:uuid:{resource_uuid}"


def profile_meta(profile_url: str) -> Meta:
    """Build a Meta element carrying a single profile canonical URL."""
    return Meta(profile=[profile_url])


def join_display(*parts: Optional[str]) -> Optional[str]:
    """Join the parts of a Reference.display, skipping empty values.

    Several mappings build a display from two WPAS fields (for example
    "FORENAME and SURNAME", "CONS_NAME and CONS_GMC"). Returns None when nothing
    is available, so the element is omitted rather than emitted blank.
    """
    present = [part.strip() for part in parts if part and part.strip()]
    return " ".join(present) if present else None


def to_fhir_date(raw_date: str) -> Optional[date]:
    """Parse a WPAS date into a FHIR date.

    The WPAS date format is not stated in the wiki mapping, so the common
    NHS/ISO representations are all accepted.
    """
    value = (raw_date or "").strip()
    if not value:
        return None

    # An ISO datetime may be supplied where only a date is needed.
    parsed_datetime = to_fhir_datetime(value, warn=False)
    if parsed_datetime is not None:
        return parsed_datetime.date()

    for date_format in _DATE_ONLY_FORMATS:
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    logger.warning("Unparseable WPAS date value %r - leaving element unset", raw_date)
    return None


def to_fhir_datetime(raw_datetime: str, warn: bool = True) -> Optional[datetime]:
    """Parse a WPAS date/time into a timezone-aware FHIR dateTime.

    fhir.resources rejects naive datetimes. WPAS values carry no offset, so UTC
    is assumed; confirm with the spec owner whether local time is intended.
    """
    value = (raw_datetime or "").strip()
    if not value:
        return None

    iso_candidate = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for datetime_format in _DATE_TIME_FORMATS:
        try:
            return datetime.strptime(value, datetime_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # A date-only value is a valid dateTime at midnight.
    for date_format in _DATE_ONLY_FORMATS:
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    if warn:
        logger.warning("Unparseable WPAS date/time value %r - leaving element unset", raw_datetime)
    return None


def split_person_name(person_name: str) -> tuple[list[str], list[str], str]:
    """Split a single WPAS name field into prefix, given names and family name.

    The wiki records that the consultant's name arrives in one field as, for
    example, "Dr James Chess", so the convention is title first, then given
    names, then family name - the opposite of the "surname, given" form used
    elsewhere in HL7. A leading recognised title becomes `name.prefix`, the last
    token becomes `name.family`, and anything between becomes `name.given`.

    A comma is still honoured when present ("Chess, James"), since that form is
    unambiguous.

    Returns (prefixes, given_names, family_name).
    """
    value = (person_name or "").strip()
    if not value:
        return [], [], ""

    if "," in value:
        family, _, remainder = value.partition(",")
        tokens = [part for part in re.split(r"\s+", remainder.strip()) if part]
        comma_prefixes = [token for token in tokens if token.upper() in _NAME_PREFIXES]
        given = [token for token in tokens if token.upper() not in _NAME_PREFIXES]
        return comma_prefixes, given, family.strip()

    tokens = [part for part in re.split(r"\s+", value) if part]

    prefixes: list[str] = []
    while tokens and tokens[0].upper() in _NAME_PREFIXES:
        prefixes.append(tokens.pop(0))

    if not tokens:
        # The value was nothing but a title, which is not a usable name.
        return prefixes, [], ""

    family = tokens.pop()
    return prefixes, tokens, family
