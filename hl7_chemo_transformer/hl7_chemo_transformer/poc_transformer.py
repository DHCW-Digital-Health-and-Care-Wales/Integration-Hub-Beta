import pprint

from hl7apy import load_library
from hl7apy.core import Message
from hl7apy.exceptions import ChildNotFound
from hl7apy.parser import parse_message


def create_new_2_5_message(original_message: Message) -> Message:
    original_msh_segment = hl7_msg.msh
    original_pid_segment = hl7_msg.pid

    new_message_body = Message(version="2.5")
    new_message_body.msh.msh_1 = original_msh_segment.msh_1
    new_message_body.msh.msh_2 = original_msh_segment.msh_2
    new_message_body.msh.msh_3.hd_1 = original_msh_segment.msh_3.hd_1
    # etc
    new_message_body.msh.msh_9.msg_1 = original_msh_segment.msh_9.msg_1
    new_message_body.msh.msh_9.msg_2 = original_msh_segment.msh_9.msg_2
    new_message_body.msh.msh_9.msg_3 = "ADT_A05"
    # pid example
    new_message_body.pid.pid_1 = original_pid_segment.pid_1
    new_message_body.pid.pid_3.cx_1[0] = original_pid_segment.pid_2.cx_1
    new_message_body.pid.pid_3[0].cx_4.hd_1[0] = "NHS"
    new_message_body.pid.pid_3.cx_5[0] = "NH"
    new_message_body.pid.pid_3.cx_1[1] = "APPEND{}".format(original_pid_segment.pid_2.cx_1.value)
    new_message_body.pid.pid_3[0].cx_4.hd_1[1] = original_msh_segment.msh_3.hd_1
    new_message_body.pid.pid_3.cx_5[1] = "PI"
    new_message_body.pid.pid_5.xpn_1.fn_1 = original_pid_segment.pid_5.xpn_1.fn_1.value
    new_message_body.pid.pid_5.xpn_2 = original_pid_segment.pid_5.xpn_2
    # etc
    # pd1 example
    new_message_body.pd1.pd1_1 = "aa"

    return new_message_body


original_message_body = (
    "MSH|^~\\&|245|245|100|100|20250701141950||ADT^A31|596887414401487|P|2.4|||NE|NE EVN||20250701141950\r"
    "PID|1|1000000001^^^^NH|1000000001^^^^NH~00rb00^^^^PI||TEST^TEST||20000101000000|M|||1 Street^Town^Rhondda, cynon, taff^^CF11 9AD||07000000001\r"
    "PV1||U\r"
)

hl7_msg = parse_message(original_message_body, find_groups=False)
print("Original HL7 Message:\n{}".format(hl7_msg.to_er7().replace("\r", "\n")))

transformed_message = create_new_2_5_message(hl7_msg)
print("\nTransformed HL7 Message:")
print(transformed_message.to_er7().replace("\r", "\n"))


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


pprint_hl7_message_as_dict(hl7_msg, version="2.4")
