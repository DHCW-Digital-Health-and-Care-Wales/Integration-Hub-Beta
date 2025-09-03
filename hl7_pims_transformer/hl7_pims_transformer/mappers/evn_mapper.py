from hl7apy.core import Message

from ..utils.field_utils import get_hl7_field_value, set_nested_field
from ..utils.remove_timezone_from_datetime import remove_timezone_from_datetime


def map_evn(original_hl7_message: Message, new_message: Message) -> None:
    original_evn = original_hl7_message.evn
    set_nested_field(original_evn, new_message.evn, "evn_1")

    # EVN.2 - remove timezone from timestamp for MPI compatibility
    original_evn2_ts1 = get_hl7_field_value(original_evn, "evn_2.ts_1")
    if original_evn2_ts1:
        new_message.evn.evn_2.ts_1 = remove_timezone_from_datetime(original_evn2_ts1)

    # EVN.6 - remove timezone from timestamp for MPI compatibility
    original_evn6_ts1 = get_hl7_field_value(original_evn, "evn_6.ts_1")
    if original_evn6_ts1:
        new_message.evn.evn_6.ts_1 = remove_timezone_from_datetime(original_evn6_ts1)
