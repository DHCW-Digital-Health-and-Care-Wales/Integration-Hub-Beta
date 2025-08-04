from hl7apy.core import Message

from ..utils.field_utils import set_nested_field


def map_evn(original_hl7_message: Message, new_message: Message) -> None:
    # EVN
    set_nested_field(original_hl7_message, new_message, "evn")
