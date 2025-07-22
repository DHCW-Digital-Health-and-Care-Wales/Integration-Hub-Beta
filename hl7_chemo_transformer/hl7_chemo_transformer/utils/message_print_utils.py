import pprint
from typing import Optional

from hl7apy import load_library
from hl7apy.core import Message
from hl7apy.exceptions import ChildNotFound


def print_original_msg(msg: Message, key: Optional[str] = None) -> None:
    print("\nORIGINAL {} Message:".format(key if key else ""))
    print("=" * 50)
    original_message = msg.to_er7()
    print(original_message.replace("\r", "\n"))
    print("=" * 50)


def _hl7_message_to_dict(message_part, base_datatypes, use_long_name=True):
    """Convert an HL7 message to a dictionary for easier readibility
    Source: Github and Copilot
    :param message_part: The HL7 message from parse_message
    :param use_long_name: use the long prop names (e.g. "patient_name" instead of "pid_5")
    :returns: A dictionary representation of the HL7 message
    """
    if message_part.children:
        data = {}
        for child in message_part.children:
            name = str(child.name)
            if use_long_name:
                name = str(child.long_name).lower() if child.long_name else name

            try:
                data_type = getattr(child, "datatype")
            except ChildNotFound:
                data_type = None

            if data_type and data_type in base_datatypes:
                dictified = child.value  # basic data types can just be accessed
                dictified = dictified.value if hasattr(dictified, "value") else dictified
            else:
                dictified = _hl7_message_to_dict(child, use_long_name=use_long_name, base_datatypes=base_datatypes)

            if name in data:
                if not isinstance(data[name], list):
                    data[name] = [data[name]]
                data[name].append(dictified)
            else:
                data[name] = dictified
        return data
    else:
        return message_part.to_er7()


def pprint_hl7_message_as_dict(hl7_msg: Message, version="2.4"):
    lib = load_library(version)
    base_datatypes = lib.get_base_datatypes()
    pprint.pprint(_hl7_message_to_dict(hl7_msg, set(base_datatypes), use_long_name=True), indent=4, width=30)
