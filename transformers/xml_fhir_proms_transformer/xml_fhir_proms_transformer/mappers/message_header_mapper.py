"""MessageHeader mapper - always `Bundle.entry[0]`.

Implements the MessageHeader rows of the WPAS PROMS Mapping spreadsheet.
Key changes from previous PSOM model:
 - eventCoding now uses the actual WPAS eventCode from the payload (REFERRAL etc.)
 - destination block added (Promptly Collect endpoint) — required
 - sender added referencing the Organization entry (reviewer requirement)
 - focus references change per bundle type
"""

from __future__ import annotations

import logging
from typing import Optional

from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.messageheader import MessageHeader, MessageHeaderDestination, MessageHeaderSource
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import (
    MESSAGE_HEADER_PROFILE,
    PROMPTLY_COLLECT_DESTINATION_NAME,
    PROMPTLY_COLLECT_ENDPOINT,
    WPAS_EVENT_SYSTEM,
)
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from ..source_systems import get_source_system
from .mapping_utils import join_display, profile_meta, urn_uuid

logger = logging.getLogger(__name__)

UNKNOWN_SOURCE_ENDPOINT_PREFIX = "https://wpas-source.invalid/system-id/"


def _map_source(message: PromsMessage) -> MessageHeaderSource:
    """Build MessageHeader.source from the sending health board.

    Both system_id and hbCode identify the health board; system_id is tried
    first, then hbCode as a fallback.
    """
    system_id = message.get("system_id", "SYSTEM_ID", "systemId")
    if not system_id:
        system_id = message.get("hbCode", "hb_code", "HB_CODE")

    source_system = get_source_system(system_id)

    if source_system is None or not source_system.endpoint:
        endpoint = f"{UNKNOWN_SOURCE_ENDPOINT_PREFIX}{system_id or 'unknown'}"
        logger.warning(
            "No documented PROMS endpoint for system_id/hbCode %r - using placeholder %r",
            system_id,
            endpoint,
        )
        source = MessageHeaderSource(endpoint=endpoint)
    else:
        source = MessageHeaderSource(endpoint=source_system.endpoint)

    if source_system and source_system.name:
        source.name = source_system.name

    return source


def _map_destination() -> MessageHeaderDestination:
    """Build the fixed Promptly Collect destination block."""
    return MessageHeaderDestination(
        name=PROMPTLY_COLLECT_DESTINATION_NAME,
        endpoint=PROMPTLY_COLLECT_ENDPOINT,
    )


def map_message_header(
    message: PromsMessage,
    message_type: MessageType,
    message_header_uuid: str,
    patient_uuid: str,
    organization_uuid: Optional[str] = None,
    service_request_uuid: Optional[str] = None,
    practitioner_role_uuid: Optional[str] = None,
    procedure_uuid: Optional[str] = None,
    encounter_uuid: Optional[str] = None,
    appointment_uuid: Optional[str] = None,
    practitioner_uuid: Optional[str] = None,
) -> MessageHeader:
    """Build the MessageHeader for the given message type."""
    event_code = message.get("eventCode", "event_code", "EVENT_CODE") or message_type.event_code

    message_header = MessageHeader(
        id=message_header_uuid,
        meta=profile_meta(MESSAGE_HEADER_PROFILE),
        eventCoding=Coding(
            system=WPAS_EVENT_SYSTEM,
            code=event_code,
            display=message_type.event_display,
        ),
        source=_map_source(message),
        destination=[_map_destination()],
    )

    if message_type.definition:
        message_header.definition = message_type.definition

    # sender — references the Organization entry to identify the sending HB.
    if organization_uuid:
        message_header.sender = Reference(
            reference=urn_uuid(organization_uuid),
            type="Organization",
            display=message.get("referrer_org", "referrerOrg") or None,
        )

    # focus — contents depend on bundle type
    focus: list[Reference] = []

    # Patient is always in focus
    patient_display = join_display(
        message.get("patientFirstname", "FORENAME", "forename"),
        message.get("patientSurname", "SURNAME", "surname"),
    )
    focus.append(Reference(reference=urn_uuid(patient_uuid), type="Patient", display=patient_display))

    if service_request_uuid:
        focus.append(Reference(reference=urn_uuid(service_request_uuid), type="ServiceRequest"))
    if practitioner_role_uuid:
        focus.append(Reference(reference=urn_uuid(practitioner_role_uuid), type="PractitionerRole"))
    if procedure_uuid:
        focus.append(Reference(reference=urn_uuid(procedure_uuid), type="Procedure"))
    if encounter_uuid:
        focus.append(Reference(reference=urn_uuid(encounter_uuid), type="Encounter"))
    if appointment_uuid:
        focus.append(Reference(reference=urn_uuid(appointment_uuid), type="Appointment"))

    message_header.focus = focus
    return message_header
