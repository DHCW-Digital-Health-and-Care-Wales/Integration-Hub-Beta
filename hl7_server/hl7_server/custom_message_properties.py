import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from field_utils_lib import get_hl7_field_value
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
    pid3_codes = _get_pid3_4_1_codes(msg)
    assigning_authorities = f"|{'|'.join(pid3_codes)}|" if pid3_codes else ""

    pid2_codes = _get_pid2_4_1_codes(msg)
    update_sources = f"|{'|'.join(pid2_codes)}|" if pid2_codes else ""


    return {
        "MessageType": get_hl7_field_value(msg, "msh.msh_9.msh_9_2"),
        "UpdateSource": get_hl7_field_value(msg, "pid.pid_2.cx_4.hd_1"),
        "UpdateSources": update_sources,
        "AssigningAuthority": get_hl7_field_value(msg, "pid.pid_3.cx_4.hd_1"),
        "AssigningAuthorities": assigning_authorities,
        "DateDeath": get_hl7_field_value(msg, "pid.pid_29.ts_1"),
        "ReasonDeath": get_hl7_field_value(msg, "pid.pid_30"),
    }

def _get_pid3_4_1_codes(msg: Message) -> list[str]:
    pid = getattr(msg, "pid", None)
    pid3 = getattr(pid, "pid_3", None) if pid else None

    codes = []

    for code in pid3:
        aa_code = (code.cx_4.hd_1.value.value or "").strip()
        if aa_code not in codes:
            codes.append(aa_code)

    return codes

def _get_pid2_4_1_codes(msg: Message) -> list[str]:
    pid = getattr(msg, "pid", None)
    pid2 = getattr(pid, "pid_2", None) if pid else None

    codes = []

    for code in pid2:
        aa_code = (code.cx_4.hd_1.value.value or "").strip()
        if aa_code not in codes:
            codes.append(aa_code)

    return codes

FLOW_PROPERTY_BUILDERS: dict[str, FlowPropertyBuilder] = {
    "mpi": build_mpi_properties,
}
