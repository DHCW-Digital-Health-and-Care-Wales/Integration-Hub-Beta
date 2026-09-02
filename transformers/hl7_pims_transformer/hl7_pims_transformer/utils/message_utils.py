from hl7apy.core import Message


def is_a04_or_a08_trigger_event(hl7_message: Message) -> bool:
    """Check if the HL7 message trigger event is A04 (registration) or A08 (update)."""
    try:
        trigger_event = hl7_message.msh.msh_9.msg_2.value
        return trigger_event in ["A04", "A08"]
    except AttributeError:
        return False
