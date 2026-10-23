"""Rule-based classification of LIMS ADT messages into WRRS mapping types."""
from __future__ import annotations

from typing import Any

from field_utils_lib import get_cx_4_hd_1_segment_codes_from_pid_field, get_hl7_field_value
from hl7apy.core import Group, Message

from .app_config import MappingTypeConfig

NHS_ASSIGNING_AUTHORITY = "NHS"
LIMS_ASSIGNING_AUTHORITY = "328"

TRIGGER_A31 = "A31"
TRIGGER_A40 = "A40"
_NHS_ID_UPDATE_TRIGGERS = frozenset({TRIGGER_A31, TRIGGER_A40})


def get_trigger_event(hl7_msg: Message) -> str:
    # Keyed on MSH.9.2 (trigger event), not MSH.9.3 (message structure).
    return get_hl7_field_value(hl7_msg.msh, "msh_9.msg_2").strip()


def classify_message(hl7_msg: Message, mapping_types: MappingTypeConfig) -> list[str]:
    """Return every MappingType whose rule the message satisfies, in a stable order.

    - LIMS/NHS ID Update: A31 or A40 whose PID-3 carries identifiers with assigning authority
      (CX.4/HD.1) of both ``NHS`` and ``328``.
    - ADT_A40: any A40 (the approved rule is MSH.9.2 = 'A40'; MRG is not required here).

    An empty list means the message is unsupported. A message may match several rules, in which
    case the caller fans it out once per returned type.
    """
    trigger_event = get_trigger_event(hl7_msg)
    matches: list[str] = []

    if trigger_event in _NHS_ID_UPDATE_TRIGGERS and _has_nhs_and_lims_identifiers(hl7_msg):
        matches.append(mapping_types.nhs_id_update)

    if trigger_event == TRIGGER_A40:
        matches.append(mapping_types.a40)

    return matches


def _has_nhs_and_lims_identifiers(hl7_msg: Message) -> bool:
    # Both authorities must appear within the same PID: identifiers split across patient groups
    # (e.g. an A40 with one NHS-only and one 328-only patient) do not satisfy the rule.
    for pid in _find_pid_segments(hl7_msg):
        authorities = set(get_cx_4_hd_1_segment_codes_from_pid_field(_PidHolder(pid), "pid_3"))
        if NHS_ASSIGNING_AUTHORITY in authorities and LIMS_ASSIGNING_AUTHORITY in authorities:
            return True
    return False


class _PidHolder:
    """Adapts a PID segment to the ``msg.pid`` access used by field_utils_lib."""

    def __init__(self, pid: Any) -> None:
        self.pid = pid


def _find_pid_segments(element: Any) -> list[Any]:
    # Mirrors XPath //PID: ADT_A39 (A40) nests PID inside a PATIENT group, where ``msg.pid`` is empty.
    found: list[Any] = []
    for child in getattr(element, "children", []):
        if child.name == "PID":
            found.append(child)
        elif isinstance(child, Group):
            found.extend(_find_pid_segments(child))
    return found
