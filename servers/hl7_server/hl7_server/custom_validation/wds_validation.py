from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message

from hl7_server.exceptions.validation_exception import ValidationException

ALLOWED_WDS_MESSAGE_TYPES: set[str] = {"A28", "A31"}


def _validate_wds_specific_fields(message: Message) -> None:
    message_type = get_hl7_field_value(message, "msh.msh_9.msh_9_2")

    if not message_type:
        raise ValidationException("MSH.9.2 MessageType is missing from the WDS message")

    if message_type not in ALLOWED_WDS_MESSAGE_TYPES:
        raise ValidationException(f"Unsupported message type '{message_type}' for WDS flow")
