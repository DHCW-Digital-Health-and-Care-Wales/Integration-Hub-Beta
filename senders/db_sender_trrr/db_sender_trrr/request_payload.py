"""Parse and validate the TRRR request published by ``lims_trrr_mapper``.

The mapper does the HL7 mapping and publishes the stored procedure parameters as a JSON object. One sender per
health board receives every request, so the request type is identified from the body itself: only a merge
carries ``OldIdentifier``. The payload must then have exactly the parameters that type needs; anything else is
rejected rather than half-written.
"""

from __future__ import annotations

import json
from typing import NamedTuple

MAPPING_NHS_ID_UPDATE = "NHS_ID_UPDATE"
MAPPING_MERGE = "MERGE"

# Present only in merge requests. db_client uses the same field to choose the 4-parameter merge call.
MERGE_DISCRIMINATOR_FIELD = "OldIdentifier"

# Parameter order matches the stored procedure signatures used by db_client.execute_identifier_update.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    MAPPING_NHS_ID_UPDATE: ("LIMSIdentifier", "NewIdentifier", "NewIdentifierAssigningAuthority"),
    MAPPING_MERGE: (
        "OldIdentifier",
        "OldIdentifierAssigningAuthority",
        "NewIdentifier",
        "NewIdentifierAssigningAuthority",
    ),
}


class TrrrRequest(NamedTuple):
    """A validated TRRR request: its type and the stored procedure parameters in call order."""

    request_type: str
    parameters: dict[str, str]


def parse_trrr_request(message_body: str) -> TrrrRequest:
    """Return the request type and stored procedure parameters from a mapper payload, or raise ``ValueError``.

    Every parameter for the request type must be present as a string; values may be blank (unmapped).
    Error messages name fields only, never values, because the values include the NHS number.
    """
    try:
        payload = json.loads(message_body)
    except json.JSONDecodeError as exc:
        raise ValueError("Payload is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")

    request_type = MAPPING_MERGE if MERGE_DISCRIMINATOR_FIELD in payload else MAPPING_NHS_ID_UPDATE
    required = REQUIRED_FIELDS[request_type]

    missing = [name for name in required if not isinstance(payload.get(name), str)]
    if missing:
        raise ValueError(f"Missing or invalid {request_type} fields: {', '.join(missing)}")

    unexpected = sorted(set(payload) - set(required))
    if unexpected:
        raise ValueError(f"Unexpected fields for {request_type}: {', '.join(unexpected)}")

    # Individual parameters may be blank when the source message did not map them; spProcessIdUpdate accepts
    # blanks. A request with every parameter blank carries nothing to process, so it is still rejected.
    if not any(payload[name].strip() for name in required):
        raise ValueError(f"All {request_type} fields are blank")

    return TrrrRequest(request_type, {name: payload[name] for name in required})
