import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from field_utils_lib import get_cx_4_hd_1_segment_codes, get_hl7_field_value
from hl7apy.core import Message
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

def _pipe_wrap(values: list[str]) -> str:
    """
    Wrap a list of string values with pipe delimiters.
    Returns an empty string if the input list is empty.
    The leading and trailing pipes ensure SQL LIKE queries of the
    form "column LIKE '%|108|%'" match
    exact tokens and never partially match a code that is a
    substring of another (e.g. "|10|" cannot match inside "|108|").
    Examples:
        >>> _pipe_wrap(["252", "109"])
        "|252|109|"
        >>> _pipe_wrap([])
        ""
    """
    return f"|{'|'.join(values)}|" if values else ""


