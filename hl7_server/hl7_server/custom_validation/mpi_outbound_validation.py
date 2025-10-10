from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

from hl7_server.exceptions.validation_exception import ValidationException

ALLOWED_MPI_MESSAGE_TYPES: set[str] = {"A28", "A31", "A40"}


def _validate_mpi_outbound_specific_fields(message: Message) -> None:
    message_type = get_hl7_field_value(message, "msh.msh_9.msh_9_2")

    if not message_type:
        raise ValidationException("MSH.9.2 MessageType is missing from the MPI outbound message")

    if message_type not in ALLOWED_MPI_MESSAGE_TYPES:
        raise ValidationException(f"Unsupported message type '{message_type}' for MPI outbound flow")

    update_source = get_hl7_field_value(message, "pid.pid_2.cx_4.hd_1")
    if not update_source:
        raise ValidationException("PID.2.4.1 UpdateSource is missing from the MPI outbound message")
