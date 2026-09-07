"""Code lookups ported from the INSE wiki's JavaScript functions.

Source: `Integration Services/Software Design Documents/PROMS/WPAS_To_PROMS/Javascript Functions`.

Each function on the wiki returns the *input value unchanged* when the code is
not recognised, and that behaviour is preserved here so this service produces the
same output as the Fiorano workflow it replaces.

Gender and preferred language are a separate concern: the Fiorano workflow calls
an external `CoreReferenceDataLookup_Service` for those two fields. The
Integration Hub has no equivalent service, so `ReferenceDataResolver` defines the
seam. `StaticReferenceDataResolver` is the interim implementation; a
service-backed resolver can be substituted without touching the mappers.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

# --- NHS number verification status (NHSNumberCertification) ------------------
NHS_CERTIFICATION_DISPLAYS: dict[str, str] = {
    "01": "Number present & traced",
    "02": "Number present but not traced",
    "03": "Trace required",
    "04": "Trace attempted - no match or multiple match found",
    "05": "Trace needs to be resolved (NHS number or patient detail conflict)",
    "06": "Trace in progress",
    "07": "Number not present and trace not required",
    "08": "Trace postponed (baby under six weeks old)",
}


def nhs_certification_display(code: Optional[str]) -> Optional[str]:
    """Map an NHS_CERTIFICATION code to its display text.

    Mirrors the wiki's `NHSNumberCertification` function, which returns the code
    itself when unrecognised.
    """
    if not code:
        return None
    return NHS_CERTIFICATION_DISPLAYS.get(code.strip(), code.strip())


# --- Health board organisation names (DHACODE) --------------------------------
DHA_CODE_NAMES: dict[str, str] = {
    "7A1": "BETSI CADWALADR UNIVERSITY LHB",
    "7A2": "HYWEL DDA UNIVERSITY LHB",
    "7A3": "SWANSEA BAY UNIVERSITY LOCAL HEALTH BOARD",
    "7A5": "CWM TAF MORGANNWG UNIVERSITY LOCAL HEALTH BOARD",
    "7A6": "ANEURIN BEVAN UNIVERSITY LHB",
    "7A7": "POWYS TEACHING LOCAL HEALTH BOARD",
}


def dha_code_name(code: Optional[str]) -> Optional[str]:
    """Map a DHA_CODE to its health board name.

    Mirrors the wiki's `DHACODE` function, which returns the code itself when
    unrecognised.
    """
    if not code:
        return None
    return DHA_CODE_NAMES.get(code.strip().upper(), code.strip())


# --- Core Reference Data Lookup seam ------------------------------------------
class ReferenceDataResolver(Protocol):
    """Resolves WPAS codes that the Fiorano workflow obtained from a web service.

    The Fiorano `WebServiceConsumer_CoreReferenceDataLookup` component translated
    WPAS `SEX` and `PREFERRED_LANGUAGE` codes using the source `SYSTEM_ID`. Any
    implementation must return None for codes it cannot resolve, so the mappers
    omit the element rather than emitting an unmapped code.
    """

    def resolve_gender(self, code: Optional[str], system_id: Optional[str]) -> Optional[str]:
        """Return a FHIR AdministrativeGender code, or None."""
        ...

    def resolve_language(self, code: Optional[str], system_id: Optional[str]) -> Optional[str]:
        """Return a UKCore-HumanLanguage code, or None."""
        ...


# WPAS SEX values seen in the source systems, mapped to FHIR AdministrativeGender.
_GENDER_CODES: dict[str, str] = {
    "M": "male",
    "1": "male",
    "F": "female",
    "2": "female",
    "O": "other",
    "9": "other",
    "U": "unknown",
    "0": "unknown",
    "X": "unknown",
}


class StaticReferenceDataResolver:
    """Interim resolver using a local table instead of the reference data service.

    SPEC GAP: the authoritative WPAS SEX and PREFERRED_LANGUAGE code sets live in
    the Core Reference Data service, which the Integration Hub does not yet
    consume. Gender uses the conventional WPAS codes; language cannot be resolved
    locally at all and always returns None, so `Patient.communication` is omitted
    until the service (or an agreed static table) is available.
    """

    def resolve_gender(self, code: Optional[str], system_id: Optional[str] = None) -> Optional[str]:
        """Map a WPAS SEX code to a FHIR AdministrativeGender code."""
        if not code:
            return None

        gender = _GENDER_CODES.get(code.strip().upper())
        if gender is None:
            logger.warning("Unmapped WPAS SEX value received - Patient.gender will be omitted")
        return gender

    def resolve_language(self, code: Optional[str], system_id: Optional[str] = None) -> Optional[str]:
        """Always None - see the class docstring."""
        if code:
            logger.info(
                "PREFERRED_LANGUAGE %r cannot be resolved without the Core Reference Data service - "
                "Patient.communication will be omitted",
                code,
            )
        return None


DEFAULT_REFERENCE_DATA_RESOLVER: ReferenceDataResolver = StaticReferenceDataResolver()
