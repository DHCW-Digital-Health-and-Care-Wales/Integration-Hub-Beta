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
import os
from typing import Optional

from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.messageheader import MessageHeader, MessageHeaderDestination, MessageHeaderSource
from fhir.resources.R4B.reference import Reference

from ..fhir_constants import (
    MESSAGE_HEADER_PROFILE,
    PROMPTLY_COLLECT_DESTINATION_NAME,
    PROMPTLY_COLLECT_ENDPOINT,
    PROMPTLY_DESTINATION_ENDPOINT_ENV_VAR,
    WPAS_EVENT_SYSTEM,
    WPAS_SOURCE_ENDPOINT_BASE,
)
from ..message_types import MessageType
from ..proms_parser import PromsMessage
from ..source_systems import get_source_system
from .mapping_utils import join_display, profile_meta, urn_uuid
from .participant_mappers import health_board_name

logger = logging.getLogger(__name__)


def _map_source(message: PromsMessage) -> MessageHeaderSource:
    """Build MessageHeader.source from the sending health board.

    Both system_id and hbCode identify the health board; system_id is tried
    first, then hbCode as a fallback. The endpoint is always the WPAS source
    base URL plus the system_id, even for a health board without a known name.
    """
    system_id = message.get("system_id", "SYSTEM_ID", "systemId")
    if not system_id:
        system_id = message.get("hbCode", "hb_code", "HB_CODE")

    source_system = get_source_system(system_id)

    if source_system is not None and source_system.endpoint:
        source = MessageHeaderSource(endpoint=source_system.endpoint)
        source.name = source_system.name
        return source

    endpoint = f"{WPAS_SOURCE_ENDPOINT_BASE}/{(system_id or 'unknown').strip()}"
    logger.warning("No known health board for system_id/hbCode %r - using endpoint %r", system_id, endpoint)
    return MessageHeaderSource(endpoint=endpoint)


def _map_destination() -> MessageHeaderDestination:
    """Build the fixed Promptly destination block; the endpoint varies by environment."""
    return MessageHeaderDestination(
        name=PROMPTLY_COLLECT_DESTINATION_NAME,
        endpoint=os.getenv(PROMPTLY_DESTINATION_ENDPOINT_ENV_VAR) or PROMPTLY_COLLECT_ENDPOINT,
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
    # Same field-name aliases as proms_parser.get_message_type() (the routing
    # lookup), so eventCoding.code preserves whichever raw routing field the
    # payload actually supplied - including the legacy MESSAGE_TYPE/messageType
    # aliases - instead of silently substituting the canonical MessageType
    # code (e.g. SURGERY-PROC) for legacy payloads that never used <eventCode>.
    event_code = message.get(
        "eventCode", "event_code", "EVENT_CODE",
        "MESSAGE_TYPE", "messageType", "MSG_TYPE", "msgType",
    ) or message_type.event_code

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
            display=health_board_name(message),
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
