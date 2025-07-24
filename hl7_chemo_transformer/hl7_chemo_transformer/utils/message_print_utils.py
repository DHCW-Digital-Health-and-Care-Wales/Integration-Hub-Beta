from typing import Optional

from hl7apy.core import Message


def print_original_msg(msg: Message, key: Optional[str] = None) -> None:
    print("\nORIGINAL {} Message:".format(key if key else ""))
    print("=" * 50)
    original_message = msg.to_er7()
    print(original_message.replace("\r", "\n"))
    print("=" * 50)
