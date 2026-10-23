"""Rule-based classification of LIMS ADT messages into WRRS mapping types."""

from __future__ import annotations

from typing import Any

from field_utils_lib import get_hl7_field_value
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
      (CX.4/HD.1, or the equivalent component in compacted ER7) of both ``NHS`` and ``328``.
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
        authorities = _pid3_authority_codes(pid)
        if NHS_ASSIGNING_AUTHORITY in authorities and LIMS_ASSIGNING_AUTHORITY in authorities:
            return True
    return False


def _pid3_authority_codes(pid: Any) -> set[str]:
    """Collect the assigning-authority codes of a PID's PID-3 repetitions, for both ER7 layouts.

    The REST server publishes ``xml_to_er7`` output, which drops empty components, so the authority is not
    reliably in CX.4: ``1^^^NHS^NH`` (positioned) arrives as ``1^NHS^NH`` (compacted). We therefore accept an
    exact code as a whole component of a single repetition, at any position after CX.1, and take only the
    first sub-component (HD.1) so ``NHS&x&ISO`` yields ``NHS``.

    False-positive risk: CX.1 is the ID value and is always skipped, so an ID of ``328`` does not count. A
    code that sits in some other CX component (e.g. CX.5 ID type or CX.6 facility) would be accepted; that is
    the accepted trade-off of the compacted layout, and is why matching is exact and confined to one
    repetition rather than a substring search over the whole field.
    """
    codes: set[str] = set()
    for repetition in pid.children:
        if repetition.name != "PID_3":
            continue
        components = repetition.to_er7().split("^")[1:]
        codes.update(component.split("&")[0] for component in components)
    return codes


def _find_pid_segments(element: Any) -> list[Any]:
    # Mirrors XPath //PID: ADT_A39 (A40) nests PID inside a PATIENT group, where ``msg.pid`` is empty.
    found: list[Any] = []
    for child in getattr(element, "children", []):
        if child.name == "PID":
            found.append(child)
        elif isinstance(child, Group):
            found.extend(_find_pid_segments(child))
    return found
