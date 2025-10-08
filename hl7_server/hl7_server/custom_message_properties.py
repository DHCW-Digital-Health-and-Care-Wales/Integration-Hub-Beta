from collections.abc import Callable

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

FlowPropertyBuilder = Callable[[Message], dict[str, str]]


def build_mpi_properties(msg: Message) -> dict[str, str]:
    return {
        "MessageType": get_hl7_field_value(msg, "msh.msh_9.msh_9_2"),
        "UpdateSource": get_hl7_field_value(msg, "pid.pid_2.cx_4.hd_1"),
    }


FLOW_PROPERTY_BUILDERS: dict[str, FlowPropertyBuilder] = {
    "mpi": build_mpi_properties,
}
