from hl7apy.parser import parse_message

from tests.chemo_messages import chemo_messages

from .chemocare_transformer import transform_chemocare_message
from .utils.message_print_utils import print_original_msg

for key, message in chemo_messages.items():
    hl7_msg = parse_message(message)
    print_original_msg(hl7_msg, key)
    transformed_msg = transform_chemocare_message(hl7_msg)
    updated_transformed_msg = transformed_msg.to_er7().replace("\r", "\n")
    print("\nTRANSFORMED {} message:".format(key))
    print("=" * 50)
    print(updated_transformed_msg)
