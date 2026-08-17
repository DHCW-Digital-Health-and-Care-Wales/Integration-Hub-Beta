"""RISP source-system validation for the REST receiver's ``risp`` flow.

RISP is a shared, multi-message-type source system (see the plan's §3a): unlike the other
`hl7_server` flows (single sender, single message type), a single RISP deployment must accept
several message types, each with its own required sending facility (MSH.3) range:

- ``A28``/``A31``/``A40`` must arrive with MSH.3 == ``349``.
- ``ORU_R01``/``OMG_O19`` must arrive with MSH.3 in the ``350``-``358`` range (inclusive).

All RISP messages must be HL7 version ``2.5.1``. Any other message type, or a message whose
MSH.3/version does not match its type's expected range, is rejected.
"""

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

from hl7_rest_server.exceptions.validation_exception import ValidationException

RISP_SENDING_FACILITY = "349"
RISP_HL7_VERSION = "2.5.1"
RISP_ORU_OMG_MSH3_MIN = 350
RISP_ORU_OMG_MSH3_MAX = 358

# ADT triggers routed to risp-hl7-transformer -> MPI. A40 is additionally routed to WRRS.
ADT_TRIGGERS_TO_MPI: frozenset[str] = frozenset({"A28", "A31", "A40"})
WRRS_DIRECT_ADT_TRIGGERS: frozenset[str] = frozenset({"A40"})

# Message structures (MSH.9.3, e.g. "ORU_R01") routed to WRRS after custom XSD validation.
ORU_OMG_STRUCTURES: frozenset[str] = frozenset({"ORU_R01", "OMG_O19"})


def resolve_trigger(message: Message) -> str:
    """MSH.9.2 — the trigger event (e.g. ``A28``, ``R01``, ``O19``)."""
    return get_hl7_field_value(message, "msh.msh_9.msh_9_2")


def resolve_structure(message: Message) -> str:
    """MSH.9.3 — the message structure (e.g. ``ORU_R01``), falling back to
    ``{MSH.9.1}_{MSH.9.2}`` when the structure component is absent (common for ADT messages)."""
    structure = get_hl7_field_value(message, "msh.msh_9.msh_9_3")
    if structure:
        return structure

    message_type = get_hl7_field_value(message, "msh.msh_9.msh_9_1")
    trigger = resolve_trigger(message)
    return f"{message_type}_{trigger}" if message_type and trigger else ""


def validate_risp_message(message: Message) -> None:
    """Validate a RISP-sourced message's HL7 version and sending facility (MSH.3).

    Raises:
        ValidationException: the message's version doesn't match, its message type is not one
            RISP is configured to send, or its MSH.3 is outside the expected range for its type.
    """
    version = get_hl7_field_value(message, "msh.msh_12")
    if version != RISP_HL7_VERSION:
        raise ValidationException(f"Unsupported HL7 version '{version}' for RISP flow; expected '{RISP_HL7_VERSION}'")

    sending_facility = get_hl7_field_value(message, "msh.msh_3")
    trigger = resolve_trigger(message)
    structure = resolve_structure(message)

    if trigger in ADT_TRIGGERS_TO_MPI:
        if sending_facility != RISP_SENDING_FACILITY:
            raise ValidationException(
                f"Message sending facility '{sending_facility}' is not valid for RISP ADT messages "
                f"(trigger '{trigger}'); expected '{RISP_SENDING_FACILITY}'"
            )
        return

    if structure in ORU_OMG_STRUCTURES:
        if not _is_valid_oru_omg_facility(sending_facility):
            raise ValidationException(
                f"Message sending facility '{sending_facility}' is not in the allowed RISP range "
                f"({RISP_ORU_OMG_MSH3_MIN}-{RISP_ORU_OMG_MSH3_MAX}) for '{structure}' messages"
            )
        return

    raise ValidationException(f"Unsupported message type/trigger '{structure or trigger}' for RISP flow")


def _is_valid_oru_omg_facility(sending_facility: str) -> bool:
    if not sending_facility or not sending_facility.isdigit():
        return False
    value = int(sending_facility)
    return RISP_ORU_OMG_MSH3_MIN <= value <= RISP_ORU_OMG_MSH3_MAX

