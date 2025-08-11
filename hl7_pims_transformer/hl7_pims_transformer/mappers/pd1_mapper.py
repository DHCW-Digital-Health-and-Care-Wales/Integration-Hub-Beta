from hl7apy.core import Message

from ..utils.field_utils import get_hl7_field_value, is_a04_or_a08_trigger_event, set_nested_field


def map_pd1(original_hl7_message: Message, new_message: Message) -> None:
    original_pd1 = getattr(original_hl7_message, "pd1", None)
    if original_pd1 is None:
        return  # No PD1 segment

    if is_a04_or_a08_trigger_event(original_hl7_message):
        set_nested_field(original_pd1, new_message.pd1, "pd1_4.xcn_1")

        if len(getattr(original_pd1, "pd1_4", [])) > 1:
            new_message.pd1.pd1_3.xon_3 = get_hl7_field_value(original_pd1, "pd1_4[1].xcn_1")
