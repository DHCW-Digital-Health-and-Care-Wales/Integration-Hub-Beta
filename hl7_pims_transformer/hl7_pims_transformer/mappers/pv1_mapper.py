from hl7apy.core import Message

from ..utils.field_utils import is_a04_or_a08_trigger_event


def map_pv1(original_hl7_message: Message, new_message: Message) -> None:
    if is_a04_or_a08_trigger_event(original_hl7_message):
        new_message.pv1.pv1_2.value = "N"
