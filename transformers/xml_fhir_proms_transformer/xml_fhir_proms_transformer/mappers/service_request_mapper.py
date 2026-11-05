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
    SERVICE_REQUEST_INTENT,
    SERVICE_REQUEST_STATUS,
    WPAS_IG_PATHWAY_SYSTEM,
    WPAS_IG_SERVICE_REQUEST_IDENTIFIER_SYSTEM,
    WPAS_IG_SERVICE_REQUEST_PROFILE,
)
from ..proms_parser import PromsMessage
from .mapping_utils import profile_meta, to_fhir_date


def map_service_request(
    message: PromsMessage,
    service_request_uuid: str,
    patient_uuid: str,
    requester_uuid: Optional[str] = None,
    performer_uuid: Optional[str] = None,
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
        meta=profile_meta(WPAS_IG_SERVICE_REQUEST_PROFILE),
        status=SERVICE_REQUEST_STATUS,
        intent=SERVICE_REQUEST_INTENT,
        doNotPerform=False,
        subject=Reference(reference=f"urn:uuid:{patient_uuid}", type="Patient"),
    )

    if identifier_value:
        service_request.identifier = [
            Identifier(
                system=WPAS_IG_SERVICE_REQUEST_IDENTIFIER_SYSTEM,
                value=identifier_value,
            )
        ]

    # code - the event pathway (national map value, e.g. GENERIC) under the pathway code system.
    # The event type is already carried by MessageHeader.eventCoding (Promptly, 28 Oct 2026).
    event_pathway = message.get("eventPathway", "event_pathway")
    if event_pathway:
        service_request.code = CodeableConcept(coding=[Coding(system=WPAS_IG_PATHWAY_SYSTEM, code=event_pathway)])
    # occurrenceDateTime — eventDate as a plain date; a midnight UTC time would
    # shift by an hour during BST
    event_date_raw = message.get("eventDate", "event_date")
    if event_date_raw:
        parsed_date = to_fhir_date(event_date_raw)
        if parsed_date:
            # fhir.resources accepts a date here at runtime; its annotation only says datetime
            service_request.occurrenceDateTime = parsed_date  # type: ignore[assignment]

    if requester_uuid:
        service_request.requester = Reference(
            reference=f"urn:uuid:{requester_uuid}",
            type="Practitioner",
        )

    if performer_uuid:
        service_request.performer = [
            Reference(reference=f"urn:uuid:{performer_uuid}", type="Practitioner")
        ]

    return service_request
