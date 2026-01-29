import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

FlowPropertyBuilder = Callable[[Message, str, str], dict[str, str]]


def build_common_properties(workflow_id: str, sending_app: str | None) -> dict[str, str]:
    return {
        "MessageReceivedAt": datetime.now(timezone.utc).isoformat(),
        "EventId": str(uuid.uuid4()),
        "WorkflowID": workflow_id,
        "SourceSystem": sending_app if sending_app else "",
    }


def build_mpi_properties(msg: Message, workflow_id: str, sending_app: str | None) -> dict[str, str]:
    common_props = build_common_properties(workflow_id, sending_app)
    flow_specific_props = {
        "MessageType": get_hl7_field_value(msg, "msh.msh_9.msh_9_2"),
        "UpdateSource": get_hl7_field_value(msg, "pid.pid_2.cx_4.hd_1"),
        "AssigningAuthority": get_hl7_field_value(msg, "pid.pid_3.cx_4.hd_1"),
        "DateDeath": get_hl7_field_value(msg, "pid.pid_29.ts_1"),
        "ReasonDeath": get_hl7_field_value(msg, "pid.pid_30"),
    }
    return {**common_props, **flow_specific_props}


FLOW_PROPERTY_BUILDERS: dict[str, FlowPropertyBuilder] = {
    "mpi": build_mpi_properties,
}
