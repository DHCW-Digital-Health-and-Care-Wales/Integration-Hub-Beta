"""WPAS -> Promptly FHIR message Bundle transformer.

Assembles the FHIR R4B message bundles defined by the WPAS PROMS Mapping
spreadsheet (By Profile v1-0). The entry order is positional:

    REFERRAL:  MessageHeader, Patient, ServiceRequest, PractitionerRole,
               Practitioner, Organization, Location
    SURGERY:   MessageHeader, Patient, Procedure, Practitioner, Organization, Location
    PREOP:     MessageHeader, Patient, Appointment, Practitioner, Organization, Location
    INPATIENT: MessageHeader, Patient, Encounter, Practitioner, Organization, Location
    CANCELLED: MessageHeader, Patient, Appointment(cancelled), Practitioner, Organization, Location
    PREREAD:   MessageHeader, Patient, Encounter(pre-admission), Practitioner, Organization, Location

Resource ids are UUIDs cross-referenced between entries as `urn:uuid:` fullUrls.
Target FHIR version is R4B.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fhir.resources.R4B.bundle import Bundle, BundleEntry
from fhir.resources.R4B.resource import Resource
from transformer_base_lib import BaseTransformer

from .mappers.appointment_mapper import map_appointment
from .mappers.encounter_mapper import map_encounter
from .mappers.location_mapper import map_location
from .mappers.mapping_utils import UuidFactory, new_uuid, urn_uuid
from .mappers.message_header_mapper import map_message_header
from .mappers.participant_mappers import map_organization, map_practitioner
from .mappers.patient_mapper import map_patient
from .mappers.practitioner_role_mapper import map_practitioner_role
from .mappers.procedure_mapper import map_procedure
from .mappers.service_request_mapper import map_service_request
from .message_types import MessageType, resolve_message_type
from .proms_parser import PromsMessage, get_message_type, parse_proms_xml
from .reference_data import DEFAULT_REFERENCE_DATA_RESOLVER, ReferenceDataResolver

logger = logging.getLogger(__name__)


def _entry(resource_uuid: str, resource: Resource) -> BundleEntry:
    """Build a bundle entry with the urn:uuid: fullUrl the mapping requires."""
    return BundleEntry(fullUrl=urn_uuid(resource_uuid), resource=resource)


def _build_referral_bundle(
    message: PromsMessage,
    message_type: MessageType,
    uuid_factory: UuidFactory,
    resolver: ReferenceDataResolver,
) -> Bundle:
    """Assemble the Referral bundle.

    Entry order: MessageHeader, Patient, ServiceRequest, PractitionerRole,
                 Practitioner, Organization, Location
    """
    mh_uuid = uuid_factory()
    patient_uuid = uuid_factory()
    sr_uuid = uuid_factory()
    pr_uuid = uuid_factory()
    practitioner_uuid = uuid_factory()
    org_uuid = uuid_factory()
    location_uuid = uuid_factory()

    practitioner = map_practitioner(message, practitioner_uuid, message_type)
    organization = map_organization(message, org_uuid)
    location = map_location(message, location_uuid)

    linked_practitioner_uuid = practitioner_uuid if practitioner is not None else None
    linked_org_uuid = org_uuid if organization is not None else None
    linked_location_uuid = location_uuid if location is not None else None

    entries = [
        _entry(
            mh_uuid,
            map_message_header(
                message=message,
                message_type=message_type,
                message_header_uuid=mh_uuid,
                patient_uuid=patient_uuid,
                organization_uuid=linked_org_uuid,
                service_request_uuid=sr_uuid,
                practitioner_role_uuid=pr_uuid,
            ),
        ),
        _entry(patient_uuid, map_patient(message, patient_uuid, resolver=resolver)),
        _entry(
            sr_uuid,
            map_service_request(message, sr_uuid, patient_uuid, practitioner_role_uuid=pr_uuid),
        ),
        _entry(
            pr_uuid,
            map_practitioner_role(
                message,
                pr_uuid,
                practitioner_uuid=linked_practitioner_uuid,
                organization_uuid=linked_org_uuid,
                location_uuid=linked_location_uuid,
            ),
        ),
    ]

    if practitioner is not None:
        entries.append(_entry(practitioner_uuid, practitioner))
    else:
        logger.info("REFERRAL message has no practitioner identifier — Practitioner entry omitted")

    if organization is not None:
        entries.append(_entry(org_uuid, organization))
    else:
        logger.info("REFERRAL message has no organization — Organization entry omitted")

    if location is not None:
        entries.append(_entry(location_uuid, location))
    else:
        logger.info("REFERRAL message has no referrer_location — Location entry omitted")

    return Bundle(type="message", entry=entries)


def _build_standard_bundle(
    message: PromsMessage,
    message_type: MessageType,
    uuid_factory: UuidFactory,
    resolver: ReferenceDataResolver,
) -> Bundle:
    """Assemble the non-Referral bundles (Surgery, PreOp, Inpatient, Cancelled, PreRead).

    Entry order: MessageHeader, Patient, <clinical resource>,
                 Practitioner, Organization, Location

    The clinical resource (entry[2]) varies by message_type.name.
    """
    mh_uuid = uuid_factory()
    patient_uuid = uuid_factory()
    clinical_uuid = uuid_factory()
    practitioner_uuid = uuid_factory()
    org_uuid = uuid_factory()
    location_uuid = uuid_factory()

    practitioner = map_practitioner(message, practitioner_uuid, message_type)
    organization = map_organization(message, org_uuid)
    location = map_location(message, location_uuid)

    linked_practitioner_uuid = practitioner_uuid if practitioner is not None else None
    linked_org_uuid = org_uuid if organization is not None else None
    linked_location_uuid = location_uuid if location is not None else None

    # Build the clinical resource (entry[2]) based on bundle type
    type_name = message_type.name
    if type_name == "PROCEDURE_PERFORMED":
        clinical_resource = map_procedure(message, clinical_uuid, patient_uuid)
    elif type_name in ("APPOINTMENT_SCHEDULED", "APPOINTMENT_CANCELLED"):
        clinical_resource = map_appointment(
            message, clinical_uuid, patient_uuid, message_type, linked_practitioner_uuid
        )
    elif type_name in ("INPATIENT_ADMISSION", "PREADMISSION"):
        clinical_resource = map_encounter(message, clinical_uuid, patient_uuid, message_type)
    else:
        # Fallback — log and build an encounter as the safest default
        logger.warning("Unrecognised message type %s — building Encounter as default", type_name)
        clinical_resource = map_encounter(message, clinical_uuid, patient_uuid, message_type)

    entries = [
        _entry(
            mh_uuid,
            map_message_header(
                message=message,
                message_type=message_type,
                message_header_uuid=mh_uuid,
                patient_uuid=patient_uuid,
                organization_uuid=linked_org_uuid,
                procedure_uuid=clinical_uuid if type_name == "PROCEDURE_PERFORMED" else None,
                appointment_uuid=clinical_uuid if "APPOINTMENT" in type_name else None,
                encounter_uuid=clinical_uuid if "ADMISSION" in type_name or "PREADMISSION" in type_name else None,
                practitioner_uuid=linked_practitioner_uuid,
            ),
        ),
        _entry(patient_uuid, map_patient(message, patient_uuid, resolver=resolver)),
        _entry(clinical_uuid, clinical_resource),
    ]

    if practitioner is not None:
        entries.append(_entry(practitioner_uuid, practitioner))
    else:
        logger.info("%s message has no practitioner identifier — Practitioner entry omitted", type_name)

    if organization is not None:
        entries.append(_entry(org_uuid, organization))
    else:
        logger.info("%s message has no organization — Organization entry omitted", type_name)

    if location is not None:
        entries.append(_entry(location_uuid, location))
    else:
        logger.info("%s message has no referrer_location — Location entry omitted", type_name)

    return Bundle(type="message", entry=entries)


def build_fhir_bundle(
    message: PromsMessage,
    uuid_factory: UuidFactory = new_uuid,
    resolver: ReferenceDataResolver = DEFAULT_REFERENCE_DATA_RESOLVER,
) -> Bundle:
    """Convert a parsed WPAS message into a Promptly FHIR message Bundle."""
    message_type = resolve_message_type(
        event_code=get_message_type(message),
        root_tag=message.root_tag,
    )
    logger.debug("Routed WPAS message to %s mapping", message_type.name)

    if message_type.name == "REFERRAL":
        return _build_referral_bundle(message, message_type, uuid_factory, resolver)
    return _build_standard_bundle(message, message_type, uuid_factory, resolver)


def transform_proms_xml_to_fhir_bundle(
    wpas_xml_message: str,
    uuid_factory: UuidFactory = new_uuid,
    resolver: ReferenceDataResolver = DEFAULT_REFERENCE_DATA_RESOLVER,
) -> Bundle:
    """Convert a raw WPAS XML payload into a Promptly FHIR message Bundle.

    Standalone entry point for ad-hoc use and testing.
    """
    return build_fhir_bundle(parse_proms_xml(wpas_xml_message), uuid_factory=uuid_factory, resolver=resolver)


class PromsFhirTransformer(BaseTransformer):
    """Queue-driven transformer for WPAS XML -> Promptly FHIR message Bundle.

    Overrides the two BaseTransformer wire-format hooks:
      * parse_input      - WPAS XML -> PromsMessage
      * serialise_output - FHIR Bundle -> JSON
    """

    def __init__(self, resolver: Optional[ReferenceDataResolver] = None) -> None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
        super().__init__("WPAS_PROMS", config_path)
        self._resolver = resolver or DEFAULT_REFERENCE_DATA_RESOLVER

    def parse_input(self, message_body: str) -> PromsMessage:
        """Parse the inbound WPAS XML payload into a flat field view."""
        return parse_proms_xml(message_body)

    def transform_message(self, hl7_msg: PromsMessage) -> Bundle:
        return build_fhir_bundle(hl7_msg, resolver=self._resolver)

    def serialise_output(self, transformed_message: Bundle) -> str:
        """Serialise the FHIR Bundle to JSON for the egress queue."""
        return transformed_message.model_dump_json()

    def get_processed_audit_text(self, hl7_msg: PromsMessage) -> str:
        """Audit text based on the WPAS message type."""
        message_type = get_message_type(hl7_msg) or hl7_msg.root_tag or "UNKNOWN"
        return f"{self.transformer_name} transformation applied for MESSAGE_TYPE: {message_type}"
