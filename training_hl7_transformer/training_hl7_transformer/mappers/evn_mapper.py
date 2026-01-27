from field_utils_lib import get_hl7_field_value, set_nested_field
from hl7apy.core import Message
from field_utils_lib import copy_segment_fields_in_range



def map_evn(original_hl7_message: Message, new_message: Message) -> None:
    original_evn = original_hl7_message.evn
    new_evn = new_message.evn
    copy_segment_fields_in_range(original_evn, new_evn, "evn", start=1, end=6)