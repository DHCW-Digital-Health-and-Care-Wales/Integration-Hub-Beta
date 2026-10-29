"""ServiceRequest mapper - Bundle.entry[2] of a Referral bundle.

Maps the WPAS REFERRAL event to a FHIR R4B ServiceRequest resource.
"""

from __future__ import annotations

from typing import Optional

from fhir.resources.R4B.codeableconcept import CodeableConcept
from fhir.resources.R4B.coding import Coding
from fhir.resources.R4B.identifier import Identifier
from fhir.resources.R4B.reference import Reference
from fhir.resources.R4B.servicerequest import ServiceRequest

from ..fhir_constants import (
    SERVICE_REQUEST_CODE_DISPLAY,
    SERVICE_REQUEST_CODE_SYSTEM,
    SERVICE_REQUEST_IDENTIFIER_SYSTEM,
    SERVICE_REQUEST_INTENT,
    SERVICE_REQUEST_PROFILE,
    SERVICE_REQUEST_REASON_SYSTEM,
    SERVICE_REQUEST_STATUS,
)
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta, to_fhir_datetime


def map_service_request(
    message: PromsMessage,
    service_request_uuid: str,
    patient_uuid: str,
    practitioner_role_uuid: Optional[str] = None,
) -> ServiceRequest:
    """Build the ServiceRequest resource for a Referral bundle.

    SPEC GAP: identifier.value - no WPAS source field specified in the mapping
    spreadsheet. Using the pathway field as the best available unique identifier
    for the referral pathway. Confirm with spec owner.
    """
    # SPEC GAP: which WPAS field to use as the service request identifier?
    identifier_value = message.get("pathway", "unique_code", "uniqueCode", "UNIQUE_ID")

    service_request = ServiceRequest(
        id=service_request_uuid,
        meta=profile_meta(SERVICE_REQUEST_PROFILE),
        status=SERVICE_REQUEST_STATUS,
        intent=SERVICE_REQUEST_INTENT,
        doNotPerform=False,
        subject=Reference(reference=f"urn:uuid:{patient_uuid}", type="Patient"),
    )

    if identifier_value:
        service_request.identifier = [
            Identifier(
                system=SERVICE_REQUEST_IDENTIFIER_SYSTEM,
                value=identifier_value,
            )
        ]

    # code — the WPAS event code (REFERRAL) under the PROMS event code system
    # Same routing aliases as get_message_type(); this mapper only runs for referral bundles,
    # so fall back to REFERRAL when the code was supplied via the root tag instead.
    event_code = (
        message.get("eventCode", "event_code", "EVENT_CODE", "MESSAGE_TYPE", "messageType", "MSG_TYPE", "msgType")
        or ""
    ).strip().upper() or "REFERRAL"
    if event_code:
        service_request.code = CodeableConcept(
            coding=[
                Coding(
                    system=SERVICE_REQUEST_CODE_SYSTEM,
                    code=event_code,
                    display=SERVICE_REQUEST_CODE_DISPLAY,
                )
            ]
        )

    # reasonCode — the WPAS event pathway (display pending WPAS ServicePoint call)
    event_pathway = message.get("eventPathway", "event_pathway")
    if event_pathway:
        service_request.reasonCode = [
            CodeableConcept(coding=[Coding(system=SERVICE_REQUEST_REASON_SYSTEM, code=event_pathway)])
        ]

    # occurrenceDateTime — from eventDate
    event_date_raw = message.get("eventDate", "event_date")
    if event_date_raw:
        parsed_dt = to_fhir_datetime(event_date_raw)
        if parsed_dt:
            service_request.occurrenceDateTime = parsed_dt

    # requester — PractitionerRole
    if practitioner_role_uuid:
        service_request.requester = Reference(
            reference=f"urn:uuid:{practitioner_role_uuid}",
            type="PractitionerRole",
        )

    return service_request
