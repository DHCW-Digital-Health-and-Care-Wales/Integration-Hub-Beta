import uuid
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any

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
    pid2_codes = _get_pid_4_1_codes(msg, "pid_2")
    update_sources = _pipe_wrap(pid2_codes)

    pid3_codes = _get_pid_4_1_codes(msg, "pid_3")
    assigning_authorities = _pipe_wrap(pid3_codes)

    return {
        "MessageType": get_hl7_field_value(msg, "msh.msh_9.msh_9_2"),
        "UpdateSources": update_sources,
        "AssigningAuthorities": assigning_authorities,
        "DateDeath": get_hl7_field_value(msg, "pid.pid_29.ts_1"),
        "ReasonDeath": get_hl7_field_value(msg, "pid.pid_30"),
    }

def get_pid_4_1_codes(msg: Message, pid_field: str = "pid_3") -> list[str]:
    return _get_pid_4_1_codes(msg, pid_field)

def _get_pid_4_1_codes(msg: Message, pid_field: str) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()

    single = (get_hl7_field_value(msg, f"pid.{pid_field}.cx_4.hd_1") or "").strip()
    if single:
        seen.add(single)
        codes.append(single)

    try:
        pid = msg.pid
    except Exception:
        pid = None

    if pid is None:
        return codes

    try:
        field_val = getattr(pid, pid_field)
    except Exception:
        field_val = None

    for rep in _normalize_repetitions(field_val):
        aa_code = _extract_cx_4_hd_1(rep)
        if aa_code and aa_code not in seen:
            seen.add(aa_code)
            codes.append(aa_code)

    return codes

def _extract_cx_4_hd_1(rep: Any) -> str:
    try:
        return (rep.cx_4.hd_1.value.value or "").strip()
    except Exception:
        return ""

def _pipe_wrap(values: list[str]) -> str:
    return f"|{'|'.join(values)}|" if values else ""

def _normalize_repetitions(value: object | None) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return [value]

FLOW_PROPERTY_BUILDERS: dict[str, FlowPropertyBuilder] = {
    "mpi": build_mpi_properties,
}
