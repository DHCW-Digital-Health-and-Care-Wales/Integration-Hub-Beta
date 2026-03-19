
# Import field utilities from shared_libs
# These provide helper functions for working with HL7 fields
from field_utils_lib import copy_segment_fields_in_range, get_hl7_field_value

from hl7apy.core import Message
from hl7apy.parser import parse_message

_MESSAGE = """MSH|^~\&|169|TRAINING_FAC|RECEIVER|RECEIVER_FAC|20260115120000||ADT^A28|MSG002|P|2.3.1|||
EVN||20260115120000
PID|||98765432^^^TRAINING^PI||JONES^MARY^ANN^^MRS||19900722|F|||456 NEW PATIENT ROAD^^SWANSEA^WALES^SA1 2BB^^H
PV1||O|
"""

def test():
    message = parse_message(_MESSAGE)
    print(message)


if __name__ == "__main__":
    test()
