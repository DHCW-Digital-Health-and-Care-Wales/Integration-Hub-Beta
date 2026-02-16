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
    return {
        "MessageType": get_hl7_field_value(msg, "msh.msh_9.msh_9_2"),
        "UpdateSource": get_hl7_field_value(msg, "pid.pid_2.cx_4.hd_1"),
        "AssigningAuthority": get_hl7_field_value(msg, "pid.pid_3.cx_4.hd_1"),
        "DateDeath": get_hl7_field_value(msg, "pid.pid_29.ts_1"),
        "ReasonDeath": get_hl7_field_value(msg, "pid.pid_30"),
    }


FLOW_PROPERTY_BUILDERS: dict[str, FlowPropertyBuilder] = {
    "mpi": build_mpi_properties,
}
