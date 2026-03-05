import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from event_logger_lib import event_logger
from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.exceptions import ChildNotFound
try:
    from event_logger_lib.event_logger import event_logger  # type: ignore[attr-defined]
except ImportError:
    from event_logger_lib.event_logger import EventLogger
from message_bus_lib.metadata_utils import (
    CORRELATION_ID_KEY,
    MESSAGE_RECEIVED_AT_KEY,
    SOURCE_SYSTEM_KEY,
    WORKFLOW_ID_KEY,
)

FlowPropertyBuilder = Callable[[Message], dict[str, str]]


def build_common_properties(workflow_id: str, msg_sending_app: str | None) -> dict[str, str]:
    return {
        MESSAGE_RECEIVED_AT_KEY: datetime.now(timezone.utc).isoformat(),
        CORRELATION_ID_KEY: str(uuid.uuid4()),
        WORKFLOW_ID_KEY: workflow_id,
        SOURCE_SYSTEM_KEY: msg_sending_app if msg_sending_app else "",
    }

def build_mpi_properties(msg: Message) -> dict[str, str]:
    pid2_codes = get_cx_4_hd_1_segment_codes(msg, "pid_2")
    update_sources = _pipe_wrap(pid2_codes)

    pid3_codes = get_cx_4_hd_1_segment_codes(msg, "pid_3")
    assigning_authorities = _pipe_wrap(pid3_codes)

    return {
        "MessageType": get_hl7_field_value(msg, "msh.msh_9.msh_9_2"),
        "UpdateSources": update_sources,
        "AssigningAuthorities": assigning_authorities,
        "DateDeath": get_hl7_field_value(msg, "pid.pid_29.ts_1"),
        "ReasonDeath": get_hl7_field_value(msg, "pid.pid_30"),
    }

FLOW_PROPERTY_BUILDERS: dict[str, FlowPropertyBuilder] = {
    "mpi": build_mpi_properties,
}


def get_cx_4_hd_1_segment_codes(msg: Message, pid_field: str) -> list[str]:
    """
    Extract and deduplicate assigning authority codes from an HL7 PID segment field.

    This function retrieves a specified field from the HL7 Patient Identification (PID)
    segment and extracts all unique assigning authority codes from its repetitions.

    Args:
        msg: The HL7 message object containing the PID segment.
        pid_field: The name of the PID field to extract codes from.

    Returns:
        A list of unique assigning authority codes found in the specified field.
        Returns an empty list if the PID segment is None.
        Returns None if the PID segment or field cannot be accessed due to missing
        attributes or child segments/fields.

    Raises:
        No exceptions are raised; errors are logged as warnings instead.
        - AttributeError or ChildNotFound when accessing the PID segment
        - AttributeError when accessing the specified PID field attribute
        - ChildNotFound when the PID field child segment/field is not found
    """
    codes: list[str] = []
    seen: set[str] = set()

    try:
        pid = msg.pid
    except (AttributeError, ChildNotFound) as exc:
        event_logger.warning("Missing HL7 segment/field during mapping", extra={"error": str(exc)})
        return None

    if pid is None:
        return codes

    try:
        field_val = getattr(pid, pid_field)
    except AttributeError as exc:
        event_logger.warning(
            "Missing HL7 attribute during mapping",
            extra={"error": str(exc)},
        )
        return None
    except ChildNotFound as exc:
        event_logger.warning(
            "HL7 child segment/field not found during mapping",
            extra={"error": str(exc)},
        )
        return None

    for rep in _normalize_repetitions(field_val):
        authority_code = _extract_cx_4_hd_1(rep)
        if authority_code and authority_code not in seen:
            seen.add(authority_code)
            codes.append(authority_code)

    return codes

def _extract_cx_4_hd_1(rep: Any) -> str:
    try:
        return (rep.cx_4.hd_1.value.value or "").strip()
    except Exception:
        return ""

def _pipe_wrap(values: list[str]) -> str:
    """
    Wrap a list of string values with pipe delimiters.
    Returns an empty string if the input list is empty.
    Args:
        values: A list of strings to be pipe-delimited.
    Returns:
        A pipe-delimited string in the format "|value1|value2|...|", or an empty
        string if the input list is empty.
    Examples:
        >>> _pipe_wrap(["252", "109"])
        "|252|109|"
        >>> _pipe_wrap([])
        ""
    """
    return f"|{'|'.join(values)}|" if values else ""

def _normalize_repetitions(value: Any | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return []


