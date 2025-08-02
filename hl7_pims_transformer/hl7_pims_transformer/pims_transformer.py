from hl7apy.core import Message


def transform_pims_message(original_hl7_msg: Message) -> Message:
    new_message = Message(version="2.5")

    return new_message
