import unittest

from hl7_topic_mock_receiver.generic_handler import GenericHandler

VALID_A28_MESSAGE = (
    "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|202505052323364444|P|2.5|||||GBR||EN\r"
    "PID|1||123456^^^Hospital^MR||Doe^John\r"
)


class TestGenericHandlerNoServiceBus(unittest.TestCase):
    """Standalone mode (sender_client=None) - e.g. run from the tester's Mock Receiver bar
    without a Service Bus emulator - should still produce an ACK instead of erroring."""

    def test_reply_succeeds_without_sender_client(self) -> None:
        handler = GenericHandler(VALID_A28_MESSAGE, None)

        ack = handler.reply()

        self.assertIn("MSA", ack)


if __name__ == "__main__":
    unittest.main()
