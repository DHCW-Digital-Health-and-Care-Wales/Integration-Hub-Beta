"""PID reference-data field translation — Sex, Title, Language, Marital Status, Religion, Ethnicity.

Confirmed design (see notes/wrds-service-and-core-reference-transformer-report.md):
- Only these six PID fields may change; everything else in the message passes through unchanged.
- A single bulk WRDSService.get_result_set() call is made per message (filtered on FromSystem/
  ToSystem only), and each field is then translated client-side via WRDSService.get_to_code() — no
  further network calls per field.
- An empty/HL7-null source field is left untouched (no lookup performed for it).
- A field that IS looked up, but has no matching row or an empty ToCode, is replaced with an empty
  value (get_to_code() already returns "" for both cases).

Merge-type ADT triggers (A39/A40/A41/A42) all share the ADT_A39 message structure, which nests PID
inside an "ADT_A39_PATIENT" group rather than making it a direct child of the message. hl7apy's
`message.pid`/`message.PID` shortcut only searches direct children plus a traversal index that is
NOT populated for segments nested inside a group, so it silently returns an empty/auto-vivified
proxy (never the real segment, never ``None``) for these trigger events — every field read off it
then comes back as "". `_find_pid_segment` below walks the message tree directly (including one
level into any `Group`) so PID is found reliably regardless of whether hl7apy grouped it.
"""
from __future__ import annotations

from asyncio.log import logger

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Group, Message, Segment
from wrds_service import WRDSService

# field_path (on the PID segment) -> confirmed WRDS "type" attribute value
FIELD_TYPE_MAP: dict[str, str] = {
    "pid_8": "Sex",
    "pid_5.pid_5_5": "Title",
    "pid_15.pid_15_1": "Language",
    "pid_16.pid_16_1": "Marital Status",
    "pid_17.pid_17_1": "Religion",
    "pid_22.pid_22_1": "Ethnicity",
}

# The literal two-character HL7 "null value" indicator — an explicit empty value distinct from
# field absence.
_HL7_NULL_VALUE = '""'


def apply_core_reference_mapping(
    hl7_msg: Message,
    wrds_service: WRDSService,
    lookup_table_name: str,
) -> Message:
    """Translate the six coded PID fields on `hl7_msg` in place, and return the same object.

    Args:
        hl7_msg: The parsed HL7 message. Only PID.8/5.5/15.1/16.1/17.1/22.1 are mutated; every other
            segment/field is left untouched.
        wrds_service: WRDSService instance used to perform the bulk GetResultSet lookup.
        lookup_table_name: WRDS LookupTable name (e.g. "FioranoCodeTranslation").

    Returns:
        The same `hl7_msg` object, mutated in place.
    """
    pid = _find_pid_segment(hl7_msg)
    if pid is None:
        logger.warning("PID segment not found, skipping mapping")
        return hl7_msg

    fields_needing_lookup = {
        field_path: reference_type
        for field_path, reference_type in FIELD_TYPE_MAP.items()
        if not _is_empty_or_hl7_null(get_hl7_field_value(pid, field_path))
    }
    if not fields_needing_lookup:
        return hl7_msg  # nothing populated — skip the WRDS call entirely

    from_system = get_hl7_field_value(hl7_msg.msh, "msh_3.hd_1")
    to_system = get_hl7_field_value(hl7_msg.msh, "msh_5.hd_1")

    logger.info(
        "Requesting WRDS mappings: from_system='%s' to_system='%s' lookup_table='%s'",
        from_system,
        to_system,
        lookup_table_name,
    )

    # Single bulk call per message — filters on FromSystem/ToSystem only, retrieves
    # FromCode/type/ToCode for every row; per-field lookups below are client-side (no further
    # network calls).
    rows = wrds_service.get_result_set(
        lookup_table_name=lookup_table_name,
        attributes=[("FromSystem", from_system), ("ToSystem", to_system)],
        attributes_to_retrieve=["FromCode", "type", "ToCode"],
        exact_match=True,
    )

    for field_path, reference_type in fields_needing_lookup.items():
        raw_value = get_hl7_field_value(pid, field_path)
        to_code = wrds_service.get_to_code(rows, from_code=raw_value, reference_type=reference_type)
        _set_field_value(pid, field_path, to_code)  # "" allowed — no match / empty ToCode

    return hl7_msg


def _find_pid_segment(element: Message | Group) -> Segment | None:
    """Locate the real PID `Segment` within `element`, recursing one level into any `Group`.

    Needed because hl7apy nests PID inside an "ADT_A39_PATIENT" group for merge-type ADT triggers
    (A39/A40/A41/A42 — see module docstring), and the message-level `.pid`/`.PID` shortcut cannot
    see into that group — it returns an empty/auto-vivified proxy instead of the real segment.
    """
    for child in element.children:
        if isinstance(child, Segment) and child.name == "PID":
            return child
        if isinstance(child, Group):
            nested = _find_pid_segment(child)
            if nested is not None:
                return nested
    return None


def _is_empty_or_hl7_null(value: str) -> bool:
    return not value or value == _HL7_NULL_VALUE


def _set_field_value(pid_segment: object, field_path: str, value: str) -> None:
    """Set a (possibly nested) PID field/component to `value`, mutating `pid_segment` in place.

    For a simple field (e.g. "pid_8") the whole field is replaced. For a composite path (e.g.
    "pid_15.ce_1" or "pid_5.xpn_5") only the named sub-component is replaced — the rest of the
    composite field (e.g. CE.2 free text) is left untouched, since we never traverse into it.
    """
    parts = field_path.split(".")
    target = pid_segment
    for part in parts[:-1]:
        target = getattr(target, part)
    setattr(target, parts[-1], value)
