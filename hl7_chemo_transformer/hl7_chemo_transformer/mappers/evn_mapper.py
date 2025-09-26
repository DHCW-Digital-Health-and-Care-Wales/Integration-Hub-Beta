from field_utils_lib import set_nested_field
from hl7apy.core import Message


def map_evn(original_hl7_message: Message, new_message: Message) -> None:
    # EVN
    set_nested_field(original_hl7_message, new_message, "evn")
