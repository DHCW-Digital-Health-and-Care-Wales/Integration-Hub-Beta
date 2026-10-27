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
from fhir.resources.R4B.contactpoint import ContactPoint
from fhir.resources.R4B.extension import Extension
from fhir.resources.R4B.humanname import HumanName
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.patient import Patient, PatientCommunication

from ..fhir_constants import (
    ETHNIC_CATEGORY_EXTENSION,
    ETHNICITY_SYSTEM,
    NHS_NUMBER_SYSTEM,
    NHS_NUMBER_VERIFICATION_EXTENSION,
    NHS_NUMBER_VERIFICATION_SYSTEM,
    PATIENT_PROFILE,
    SPOKEN_LANGUAGE_SYSTEM,
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

    if not family and not given_first:
        return None

    # Per the mapping, first and middle names are a single space-joined given value.
    given = " ".join(p for p in (given_first, given_middle) if p)

    return HumanName(use="official", family=family or None, given=[given] if given else None)


def _build_address(message: PromsMessage) -> Optional[Address]:
    """Build Patient.address from the new flat address fields."""
    postal_code = message.get("postCode", "POSTCODE", "postalCode")
    building = message.get("buildingName", "ADDRESS_1")
    street = message.get("streetRoadName", "streetroadname")
    city = message.get("postTown", "ADDRESS_2")
    district = message.get("postalCounty", "postal_county")

    if not any([postal_code, building, street, city, district]):
        return None

    address = Address()

    # Concatenate building + street for address.line
    line_parts = [p for p in (building, street) if p]
    if line_parts:
        address.line = [", ".join(line_parts)]

    if city:
        address.city = city
    if district:
        address.district = district
    if postal_code:
        address.postalCode = postal_code

    return address


def _communication(message: PromsMessage) -> Optional[list[PatientCommunication]]:
    """Build Patient.communication from the WPAS spoken-language fields.

    Code and display are taken as sent (no reference-data resolution) under the
    WPAS spoken-language code system.
    """
    lang_code = message.get("preferred_spoken_language_code", "preferredSpokenLanguageCode")
    lang_display = message.get("spoken_language", "spokenLanguage")
    if not lang_code and not lang_display:
        return None

    coding = Coding(system=SPOKEN_LANGUAGE_SYSTEM, code=lang_code or None, display=lang_display or None)
    return [PatientCommunication(language=CodeableConcept(coding=[coding]))]


def _ethnic_category_extension(message: PromsMessage) -> Optional[Extension]:
    """Build Patient.extension:ethnicCategory from ethnic_origin_code / ethnic_origin."""
    code = message.get("ethnic_origin_code", "ethnicOriginCode")
    display = message.get("ethnic_origin", "ethnicOrigin")
    if not code and not display:
        return None

    return Extension(
        url=ETHNIC_CATEGORY_EXTENSION,
        valueCodeableConcept=CodeableConcept(
            coding=[Coding(system=ETHNICITY_SYSTEM, code=code or None, display=display or None)],
            text=display or None,
        ),
    )


# (WPAS field names, ContactPoint.system, ContactPoint.use)
_TELECOM_FIELDS: tuple[tuple[tuple[str, ...], str, Optional[str]], ...] = (
    (("home_phone", "homePhone", "TELEPHONE_DAY"), "phone", "home"),
    (("work_phone", "workPhone"), "phone", "work"),
    (("mobile_phone", "mobilePhone"), "phone", "mobile"),
    (("email", "EMAIL"), "email", None),
)


def _build_telecom(message: PromsMessage) -> list[ContactPoint]:
    """Build one ContactPoint per populated WPAS telephone/email field."""
    telecom: list[ContactPoint] = []
    for field_names, system, use in _TELECOM_FIELDS:
        value = message.get(*field_names)
        if value:
            contact_point = ContactPoint(system=system, value=value)
            if use:
                contact_point.use = use
            telecom.append(contact_point)
    return telecom


def _deceased(message: PromsMessage) -> Optional[Union[bool, datetime]]:
    """Build Patient.deceasedDateTime from DOD (or legacy DEATHDATE) when present.

    Falls back to boolean True if the date cannot be parsed, so the patient is
    not incorrectly marked as alive.
    """
    raw = message.get("DOD", "dod", "DEATHDATE", "deathDate")
    if not message.has("DOD", "dod", "DEATHDATE", "deathDate"):
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
    patient = Patient(id=patient_uuid, meta=profile_meta(PATIENT_PROFILE), active=True)

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

    telecom = _build_telecom(message)
    if telecom:
        patient.telecom = telecom

    ethnic_category = _ethnic_category_extension(message)
    if ethnic_category:
        patient.extension = [ethnic_category]

    communication = _communication(message)
    if communication:
        patient.communication = communication

    return patient

