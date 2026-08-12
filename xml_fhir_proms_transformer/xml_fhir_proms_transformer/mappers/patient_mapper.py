"""Patient mapper for the WPAS -> PROMS FHIR bundle.

Updated for the new WPAS PromsEventRequest payload format which supplies:
  patientTitle, patientFirstname, patientMiddlename, patientSurname
  buildingName, streetRoadName, postTown, postCode
  spoken_language / preferred_spoken_language_code
  dob, gender, nhsNumber, crn/UNIT_NUMBER
  DEATHDATE (for patient death messages)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union

from fhir.resources.R4B.address import Address
from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.patient import Patient, PatientCommunication

from ..fhir_constants import (
    HUMAN_LANGUAGE_SYSTEM,
    NHS_NUMBER_SYSTEM,
    NHS_NUMBER_VERIFICATION_EXTENSION,
    NHS_NUMBER_VERIFICATION_SYSTEM,
    PATIENT_PROFILE,
)
from ..proms_parser import PromsMessage
from ..reference_data import (
    DEFAULT_REFERENCE_DATA_RESOLVER,
    ReferenceDataResolver,
    nhs_certification_display,
)
from ..source_systems import get_pas_identifier_system
from .mapping_utils import profile_meta, to_fhir_date, to_fhir_datetime


def _nhs_number_identifier(message: PromsMessage) -> Optional[Identifier]:
    nhs_number = message.get("nhsNumber", "NHS_NUMBER")
    if not nhs_number:
        return None

    identifier = Identifier(system=NHS_NUMBER_SYSTEM, value=nhs_number)

    certification = message.get("NHS_CERTIFICATION", "nhsCertification")
    if certification:
        identifier.extension = [
            Extension(
                url=NHS_NUMBER_VERIFICATION_EXTENSION,
                valueCodeableConcept=CodeableConcept(
                    coding=[
                        Coding(
                            system=NHS_NUMBER_VERIFICATION_SYSTEM,
                            code=certification,
                            display=nhs_certification_display(certification),
                        )
                    ]
                ),
            )
        ]
    return identifier


def _pas_identifier(message: PromsMessage) -> Optional[Identifier]:
    unit_number = message.get("crn", "UNIT_NUMBER", "unitNumber")
    if not unit_number:
        return None

    system_id = message.get("system_id", "SYSTEM_ID", "systemId") or message.get("hbCode", "hb_code")
    pas_system = get_pas_identifier_system(system_id)
    if not pas_system:
        return None

    return Identifier(system=pas_system, value=unit_number)


def _build_name(message: PromsMessage) -> Optional[HumanName]:
    """Build Patient.name from the WPAS camelCase fields in actual payloads."""
    family = message.get("patientSurname", "SURNAME", "surname")
    given_first = message.get("patientFirstname", "FORENAME", "forename")
    given_middle = message.get("patientMiddlename", "patientMiddleName")
    prefix_raw = message.get("patientTitle", "TITLE", "title")

    if not family and not given_first:
        return None

    given_parts: list[Optional[str]] = []
    if given_first:
        given_parts.append(given_first)
    if given_middle:
        given_parts.append(given_middle)

    name = HumanName(
        use="official",
        family=family or None,
        given=given_parts if given_parts else None,
    )
    if prefix_raw:
        name.prefix = [prefix_raw]

    return name


def _build_address(message: PromsMessage) -> Optional[Address]:
    """Build Patient.address from the new flat address fields."""
    postal_code = message.get("postCode", "POSTCODE", "postalCode")
    building = message.get("buildingName", "ADDRESS_1")
    street = message.get("streetRoadName", "streetroadname")
    city = message.get("postTown", "ADDRESS_2")

    if not any([postal_code, building, street, city]):
        return None

    address = Address()

    # Concatenate building + street for address.line
    line_parts = [p for p in (building, street) if p]
    if line_parts:
        address.line = [", ".join(line_parts)]

    if city:
        address.city = city
    if postal_code:
        address.postalCode = postal_code

    return address


def _communication(
    message: PromsMessage,
    resolver: ReferenceDataResolver,
) -> Optional[list[PatientCommunication]]:
    """Build Patient.communication from WPAS language fields.

    The actual payload carries both a code (preferred_spoken_language_code) and
    a display text (spoken_language). If the resolver cannot map the code, the
    display text is used directly as a fallback so language is not silently lost.

    SPEC GAP: pending Core Reference Data service integration.
    """
    lang_code = message.get("preferred_spoken_language_code", "PREFERRED_LANGUAGE", "preferredLanguage")
    lang_display = message.get("spoken_language", "spokenLanguage")

    system_id = message.get("system_id", "SYSTEM_ID", "systemId")
    resolved = resolver.resolve_language(lang_code, system_id)

    if not resolved and not lang_display:
        return None

    # Build with the resolved code when available, falling back to display-only.
    coding = Coding(system=HUMAN_LANGUAGE_SYSTEM)
    if resolved:
        coding.code = resolved
    if lang_display:
        coding.display = lang_display

    return [
        PatientCommunication(
            language=CodeableConcept(coding=[coding]),
            preferred=True,
        )
    ]


def _deceased(message: PromsMessage) -> Optional[Union[bool, datetime]]:
    """Build Patient.deceasedDateTime from DEATHDATE when present.

    The new mapping uses deceasedDateTime (actual date) rather than
    deceasedBoolean. Falls back to boolean True if the date cannot be parsed,
    so the patient is not incorrectly marked as alive.
    """
    raw = message.get("DEATHDATE", "deathDate")
    if not message.has("DEATHDATE", "deathDate"):
        return None
    if not raw or not raw.strip():
        return False  # empty = not deceased

    # Try to parse as a dateTime for the preferred representation.
    parsed_dt = to_fhir_datetime(raw, warn=False)
    if parsed_dt is not None:
        return parsed_dt

    parsed_d = to_fhir_date(raw)
    if parsed_d is not None:
        # Convert date → datetime at midnight UTC so the type is always datetime
        return datetime(parsed_d.year, parsed_d.month, parsed_d.day, tzinfo=timezone.utc)

    # Non-empty but unparseable: treat as deceased with unknown date.
    return True



def map_patient(
    message: PromsMessage,
    patient_uuid: str,
    resolver: ReferenceDataResolver = DEFAULT_REFERENCE_DATA_RESOLVER,
    include_deceased: bool = False,
) -> Patient:
    """Build the Patient resource from the actual WPAS PromsEventRequest fields."""
    patient = Patient(id=patient_uuid, meta=profile_meta(PATIENT_PROFILE))

    identifiers = [
        i for i in (_nhs_number_identifier(message), _pas_identifier(message)) if i is not None
    ]
    if identifiers:
        patient.identifier = identifiers

    name = _build_name(message)
    if name:
        patient.name = [name]

    gender = resolver.resolve_gender(
        message.get("gender", "SEX", "sex"),
        message.get("system_id", "SYSTEM_ID", "systemId"),
    )
    if gender:
        patient.gender = gender

    birth_date = to_fhir_date(message.get("dob", "BIRTHDATE", "birthDate"))
    if birth_date:
        patient.birthDate = birth_date

    if include_deceased:
        deceased = _deceased(message)
        if deceased is not None:
            if isinstance(deceased, bool):
                patient.deceasedBoolean = deceased
            else:
                patient.deceasedDateTime = deceased

    address = _build_address(message)
    if address:
        patient.address = [address]

    communication = _communication(message, resolver)
    if communication:
        patient.communication = communication

    return patient

